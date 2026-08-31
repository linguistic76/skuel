"""Askesis aggregation query tools — the selection/validation/execution layer.

Tool-selection first slice (docs/roadmap/askesis-tool-selection-queries.md,
ruled 2026-08-31). The executor's cross-tenant guard (LLM-supplied ``user_uid``
ignored) and the out-of-coverage decline are pinned in
tests/unit/test_askesis_intent_filter_activation_guard.py GUARD 3; delivery
(the outcome reaching the learner) in
tests/unit/test_askesis_aggregation_delivery.py. This module covers the rest of
the layer: server-side period resolution, the args gate, handler normalization,
and the failure→unavailable folds.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from core.models.enums import AggregationPeriod
from core.ports.llm_protocols import ToolSelection, ToolSpec
from core.services.askesis.query_tools import (
    AggregationAnswered,
    AggregationCount,
    AggregationDeclined,
    AggregationUnavailable,
    CountGoalsAchievedArgs,
    build_aggregation_catalog,
    resolve_period,
    run_tool,
    select_and_run,
    tool_specs,
)
from core.utils.result_simplified import Errors, Result

# ============================================================================
# resolve_period — relative time becomes bounds SERVER-SIDE, never in the model
# ============================================================================


class TestResolvePeriod:
    """Every period is a CLOSED calendar range resolved from the server's date.

    The args model carries no free-form dates at all, so these resolutions are
    the ONLY way a relative phrase becomes bounds — a hallucinated or stale
    "today" from the model has no field to land in.
    """

    def test_last_quarter_mid_year(self) -> None:
        since, until = resolve_period(AggregationPeriod.LAST_QUARTER, date(2026, 8, 31))
        assert (since, until) == (date(2026, 4, 1), date(2026, 6, 30))

    def test_last_quarter_crosses_the_year_boundary(self) -> None:
        since, until = resolve_period(AggregationPeriod.LAST_QUARTER, date(2026, 1, 15))
        assert (since, until) == (date(2025, 10, 1), date(2025, 12, 31))

    def test_last_month_crosses_the_year_boundary(self) -> None:
        since, until = resolve_period(AggregationPeriod.LAST_MONTH, date(2026, 1, 15))
        assert (since, until) == (date(2025, 12, 1), date(2025, 12, 31))

    def test_this_month_ends_on_the_real_month_end(self) -> None:
        since, until = resolve_period(AggregationPeriod.THIS_MONTH, date(2026, 2, 10))
        assert (since, until) == (date(2026, 2, 1), date(2026, 2, 28))

    def test_weeks_start_monday(self) -> None:
        # 2026-08-31 is a Monday — this_week starts on the reference day itself.
        assert resolve_period(AggregationPeriod.THIS_WEEK, date(2026, 8, 31)) == (
            date(2026, 8, 31),
            date(2026, 9, 6),
        )
        assert resolve_period(AggregationPeriod.LAST_WEEK, date(2026, 8, 31)) == (
            date(2026, 8, 24),
            date(2026, 8, 30),
        )

    def test_every_member_resolves_to_an_ordered_closed_range(self) -> None:
        """Exhaustive over the enum — a new member must land in the resolver."""
        for period in AggregationPeriod:
            since, until = resolve_period(period, date(2026, 8, 31))
            assert since <= until, f"{period.value} resolved to an empty interval"


# ============================================================================
# The args gate — narrow, enum-bound, extra-forbidden
# ============================================================================


class TestCountGoalsAchievedArgs:
    def test_period_is_required(self) -> None:
        with pytest.raises(ValidationError):
            CountGoalsAchievedArgs.model_validate({})

    def test_unknown_arguments_are_refused(self) -> None:
        """extra="forbid": a stray model-emitted arg cannot silently shape the
        query — it fails the gate and takes the deterministic unavailable path."""
        with pytest.raises(ValidationError):
            CountGoalsAchievedArgs.model_validate({"period": "last_quarter", "limit": 5})

    def test_no_free_form_dates_exist_in_the_schema(self) -> None:
        """The model cannot volunteer a date — there is no field for one."""
        schema = CountGoalsAchievedArgs.model_json_schema()
        assert set(schema["properties"]) == {"period"}

    def test_period_string_coerces_to_the_enum(self) -> None:
        args = CountGoalsAchievedArgs.model_validate({"period": "last_quarter"})
        assert args.period is AggregationPeriod.LAST_QUARTER


# ============================================================================
# The catalog — handler bound to the SERVICE, normalized at registration
# ============================================================================


def _today() -> date:
    return date(2026, 8, 31)


class TestBuildAggregationCatalog:
    async def test_handler_resolves_the_period_against_the_injected_clock(self) -> None:
        service = AsyncMock()
        service.count_goals_achieved = AsyncMock(
            return_value=Result.ok({"total": 4, "since": "2026-04-01", "until": "2026-06-30"})
        )
        catalog = build_aggregation_catalog(service, today=_today)

        result = await catalog["count_goals_achieved"].handler(
            user_uid="user_caller", period=AggregationPeriod.LAST_QUARTER
        )

        assert result.is_ok
        service.count_goals_achieved.assert_awaited_once_with(
            user_uid="user_caller", since=date(2026, 4, 1), until=date(2026, 6, 30)
        )
        payload = result.value
        assert isinstance(payload, AggregationCount)
        assert payload.subject == "goals achieved"
        assert payload.total == 4
        # the APPLIED bounds survive the call — the answer must state its scope
        assert (payload.since, payload.until) == ("2026-04-01", "2026-06-30")

    async def test_service_failure_propagates_as_failure(self) -> None:
        service = AsyncMock()
        service.count_goals_achieved = AsyncMock(
            return_value=Result.fail(Errors.database("count_goals_achieved", "db down"))
        )
        catalog = build_aggregation_catalog(service, today=_today)

        result = await catalog["count_goals_achieved"].handler(
            user_uid="user_caller", period=AggregationPeriod.LAST_QUARTER
        )

        assert result.is_error

    def test_tool_specs_come_from_the_same_pydantic_models(self) -> None:
        """The provider spec and the validation gate cannot drift apart."""
        catalog = build_aggregation_catalog(AsyncMock(), today=_today)
        specs = tool_specs(catalog)
        assert [spec.name for spec in specs] == ["count_goals_achieved"]
        assert specs[0].input_schema == CountGoalsAchievedArgs.model_json_schema()


# ============================================================================
# run_tool — the validation gate's failure mode
# ============================================================================


class TestRunToolValidation:
    async def test_malformed_args_are_a_failure_not_an_answer(self) -> None:
        """A model-emitted arg set that fails the schema takes the unavailable
        path — the backend must not faithfully answer a malformed selection."""

        async def handler(*, user_uid: str, period: AggregationPeriod) -> Result[AggregationCount]:
            raise AssertionError("the handler must not run on malformed args")

        catalog = build_aggregation_catalog(AsyncMock(), today=_today)
        selection = ToolSelection(
            tool_name="count_goals_achieved", arguments={"period": "next_millennium"}
        )

        result = await run_tool(selection, catalog, user_uid="user_caller")

        assert result.is_error


# ============================================================================
# select_and_run — every failure folds into a deterministic Unavailable
# ============================================================================


class TestSelectAndRun:
    async def test_selection_failure_folds_to_unavailable(self) -> None:
        llm = AsyncMock()
        llm.select_tool = AsyncMock(
            return_value=Result.fail(
                Errors.integration(service="Anthropic", operation="select_tool", message="down")
            )
        )
        catalog = build_aggregation_catalog(AsyncMock(), today=_today)

        outcome = await select_and_run("how many?", catalog, llm, user_uid="user_caller")

        assert isinstance(outcome, AggregationUnavailable)

    async def test_tool_failure_folds_to_unavailable(self) -> None:
        llm = AsyncMock()
        llm.select_tool = AsyncMock(
            return_value=Result.ok(
                ToolSelection(tool_name="count_goals_achieved", arguments={"period": "last_week"})
            )
        )
        service = AsyncMock()
        service.count_goals_achieved = AsyncMock(
            return_value=Result.fail(Errors.database("count_goals_achieved", "db down"))
        )
        catalog = build_aggregation_catalog(service, today=_today)

        outcome = await select_and_run("how many?", catalog, llm, user_uid="user_caller")

        assert isinstance(outcome, AggregationUnavailable)

    async def test_happy_path_selects_with_specs_and_a_system_prompt(self) -> None:
        llm = AsyncMock()
        llm.select_tool = AsyncMock(
            return_value=Result.ok(
                ToolSelection(tool_name="count_goals_achieved", arguments={"period": "last_week"})
            )
        )
        service = AsyncMock()
        service.count_goals_achieved = AsyncMock(
            return_value=Result.ok({"total": 1, "since": "2026-08-24", "until": "2026-08-30"})
        )
        catalog = build_aggregation_catalog(service, today=_today)

        outcome = await select_and_run(
            "how many goals did I achieve last week?", catalog, llm, user_uid="user_caller"
        )

        assert isinstance(outcome, AggregationAnswered)
        call = llm.select_tool.await_args
        assert call.args[0] == "how many goals did I achieve last week?"
        assert all(isinstance(spec, ToolSpec) for spec in call.args[1])
        assert call.kwargs["system_prompt"], "selection must carry the selection stance"


# ============================================================================
# Outcome rendering — deterministic, scope-stating, JSON-safe
# ============================================================================


class TestOutcomeRendering:
    def test_answered_states_the_applied_bounds(self) -> None:
        text = AggregationAnswered(
            payload=AggregationCount(
                subject="goals achieved", total=4, since="2026-04-01", until="2026-06-30"
            )
        ).answer_text()
        assert "4" in text
        assert "2026-04-01" in text and "2026-06-30" in text, (
            "the answer must state the scope it actually filtered on — a dropped "
            "question constraint must read as a visible mismatch, not disappear"
        )

    def test_declined_carries_its_reason_and_no_number(self) -> None:
        text = AggregationDeclined(reason="no tool covers streaks yet.").answer_text()
        assert "no tool covers streaks yet." in text
        assert not any(ch.isdigit() for ch in text)

    def test_unavailable_offers_no_number(self) -> None:
        text = AggregationUnavailable(reason="provider outage").answer_text()
        assert not any(ch.isdigit() for ch in text)

    def test_context_projections_are_json_safe(self) -> None:
        outcomes: list[AggregationAnswered | AggregationDeclined | AggregationUnavailable] = [
            AggregationAnswered(
                payload=AggregationCount(
                    subject="goals achieved", total=4, since="2026-04-01", until="2026-06-30"
                )
            ),
            AggregationDeclined(reason="out of coverage"),
            AggregationUnavailable(reason="outage"),
        ]
        for outcome in outcomes:
            json.dumps(outcome.to_context())
