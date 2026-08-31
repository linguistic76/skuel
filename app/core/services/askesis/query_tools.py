"""
Askesis Query Tools — LLM tool-selection over vetted, user-scoped aggregations
==============================================================================

The safe alternative to text2cypher (docs/roadmap/askesis-tool-selection-queries.md,
ruled 2026-08-31): the LLM never sees or emits a query — it picks a tool name
from a fixed catalog and fills typed parameters. Server-side code owns the
query and the ``user_uid``.

Safety contract, held in code the model cannot route around:

- **Fixed catalog** — an unknown or absent tool name is a ``Declined``
  delivered to the learner, never a fall-through to generic generation.
- **Typed args** — pydantic-validated (``extra="forbid"``); the provider tool
  schema is generated from the same model (``model_json_schema()``), so spec
  and validation gate cannot drift apart.
- **Server-side ``user_uid`` injection** — the executor always passes the
  authenticated user's uid; a model-supplied ``user_uid`` is discarded.
- **Server-resolved time** — relative periods are an enum
  (``AggregationPeriod``) resolved against the server's date; the model never
  emits a date, so it can never volunteer a stale or hallucinated "today".
- **Three deterministic outcomes** — ``AggregationAnswered`` (states the exact
  bounds it filtered on), ``AggregationDeclined`` (coverage gap, learner-visible
  reason), ``AggregationUnavailable`` (selection/tool failure — never an
  invented number). Each renders its own answer text; no LLM generation runs
  on any of them.

First slice (2026-08-31): ONE tool — ``count_goals_achieved`` — covering the
time-windowed achieved-goals shape and nothing else. Every other count question
declines by ruling; widening the catalog is a separate decision.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from core.models.enums import AggregationPeriod
from core.ports.llm_protocols import ToolSelection, ToolSpec
from core.prompts import PROMPT_REGISTRY
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.query_types import GoalsAchievedCount

logger = get_logger("skuel.services.askesis.query_tools")


# ============================================================================
# ARGS MODELS — narrow, enum-bound, per-domain
# ============================================================================


class CountGoalsAchievedArgs(BaseModel):
    """Args for ``count_goals_achieved`` — a required period, nothing else.

    ``extra="forbid"``: any argument outside the schema (including a smuggled
    ``user_uid`` — though the executor discards that one before validation)
    fails the gate and takes the deterministic unavailable path rather than
    silently shaping the query. No free-form dates: the model cannot express a
    bound the server did not resolve.
    """

    model_config = ConfigDict(extra="forbid")

    period: AggregationPeriod


# ============================================================================
# NORMALIZED PAYLOAD + OUTCOMES
# ============================================================================


@dataclass(frozen=True)
class AggregationCount:
    """The one common payload every catalog handler normalizes into.

    Normalizing at the registration boundary is what lets the catalog stay a
    single homogeneous ``dict[str, QueryTool]`` when a second domain's tool is
    registered — the erasure-boundary requirement from the design doc, solved
    at tool #1 so tool #2 cannot break the type gate.

    ``since``/``until`` are the APPLIED ISO date bounds (never ``None`` for
    period-resolved tools): the answer must state the scope it actually
    filtered on, in code, not by prompt instruction.
    """

    subject: str
    total: int
    since: str | None
    until: str | None


@dataclass(frozen=True)
class AggregationAnswered:
    """A tool ran and produced a real count — the answer states its scope."""

    payload: AggregationCount

    def answer_text(self) -> str:
        """Deterministic learner-facing answer, applied bounds included.

        Count-first phrasing so it stays grammatical for every total, and the
        window states the EXACT bounds the query filtered on — if the question
        carried a constraint the tool could not express, the mismatch is
        visible to the learner instead of disappearing.
        """
        if self.payload.since and self.payload.until:
            window = f" between {self.payload.since} and {self.payload.until}"
        elif self.payload.since:
            window = f" since {self.payload.since}"
        elif self.payload.until:
            window = f" up to {self.payload.until}"
        else:
            window = " in total"
        return f"{self.payload.subject.capitalize()}{window}: {self.payload.total}."

    def to_context(self) -> dict[str, object]:
        """JSON-safe projection for ``context_used`` / suggested actions."""
        return {
            "outcome": "answered",
            "subject": self.payload.subject,
            "total": self.payload.total,
            "since": self.payload.since,
            "until": self.payload.until,
        }


@dataclass(frozen=True)
class AggregationDeclined:
    """No catalog tool covers the question — an explicit, learner-visible no.

    A decline is NOT an error and NOT a hint dropped into prompt context: the
    pipeline short-circuits generation and delivers this text, so the model
    cannot answer around it (the design doc's OPEN PROBLEM 2, closed for this
    slice by construction).
    """

    reason: str

    def answer_text(self) -> str:
        """Deterministic learner-facing decline."""
        return f"I can't answer that count yet — {self.reason}"

    def to_context(self) -> dict[str, object]:
        """JSON-safe projection for ``context_used`` / suggested actions."""
        return {"outcome": "declined", "reason": self.reason}


@dataclass(frozen=True)
class AggregationUnavailable:
    """Selection or execution FAILED — deterministic "unavailable", same shape
    as a decline.

    A provider outage on a reachable AGGREGATION question must not let the
    ordinary generator produce a plausible invented count — the failure mode
    this whole design exists to avoid, arriving through the error path instead
    of the selection path.
    """

    reason: str

    def answer_text(self) -> str:
        """Deterministic learner-facing unavailability notice."""
        return (
            "I couldn't compute that count right now — please try again shortly. "
            "I'd rather tell you that than guess at a number."
        )

    def to_context(self) -> dict[str, object]:
        """JSON-safe projection for ``context_used`` / suggested actions."""
        return {"outcome": "unavailable", "reason": self.reason}


AggregationOutcome = AggregationAnswered | AggregationDeclined | AggregationUnavailable

_OUT_OF_COVERAGE_REASON = (
    "none of my count tools covers this question. Right now I can count goals "
    'achieved within a time period (for example: "How many goals did I achieve '
    'last quarter?").'
)


# ============================================================================
# THE CATALOG
# ============================================================================


@dataclass(frozen=True)
class QueryTool:
    """One vetted, user-scoped aggregation the LLM may select.

    ``handler`` is bound at registration to a domain SERVICE method (never a
    backend — the executor must not bypass domain-service orchestration) and
    normalized to return ``Result[AggregationCount]``, keeping the catalog
    homogeneous as domains are added.
    """

    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[..., Awaitable[Result[AggregationCount]]]


class GoalsAchievedCounter(Protocol):
    """The one-method slice of GoalsService the goals tool binds against."""

    async def count_goals_achieved(
        self,
        *,
        user_uid: str,
        since: date | None = None,
        until: date | None = None,
    ) -> Result[GoalsAchievedCount]:
        """Count achieved goals in optional bounds; ownership enforced in-query."""
        ...


class ToolSelector(Protocol):
    """The one-method slice of LLMService the aggregation branch uses."""

    async def select_tool(
        self,
        question: str,
        tools: list[ToolSpec],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> Result[ToolSelection]:
        """Ask the model to pick a catalog tool (or none) for the question."""
        ...


def resolve_period(period: AggregationPeriod, today: date) -> tuple[date, date]:
    """Resolve a relative period to a CLOSED calendar date range, server-side.

    The only place relative time becomes concrete bounds — the model never
    emits dates. Weeks start Monday (the app-wide calendar convention);
    quarters are calendar quarters.
    """
    if period is AggregationPeriod.THIS_WEEK:
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if period is AggregationPeriod.LAST_WEEK:
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6)
    if period is AggregationPeriod.THIS_MONTH:
        start = today.replace(day=1)
        return start, _month_end(start)
    if period is AggregationPeriod.LAST_MONTH:
        start = _month_start_back(today.replace(day=1), months=1)
        return start, _month_end(start)
    if period is AggregationPeriod.THIS_QUARTER:
        start = today.replace(month=3 * ((today.month - 1) // 3) + 1, day=1)
        return start, _month_end(_month_start_back(start, months=-2))
    if period is AggregationPeriod.LAST_QUARTER:
        this_q_start = today.replace(month=3 * ((today.month - 1) // 3) + 1, day=1)
        start = _month_start_back(this_q_start, months=3)
        return start, _month_end(_month_start_back(start, months=-2))
    if period is AggregationPeriod.THIS_YEAR:
        return today.replace(month=1, day=1), today.replace(month=12, day=31)
    # LAST_YEAR — the exhaustive tail; a new member fails loudly in tests.
    return today.replace(year=today.year - 1, month=1, day=1), today.replace(
        year=today.year - 1, month=12, day=31
    )


def _month_start_back(month_start: date, months: int) -> date:
    """First day of the month ``months`` before (negative = after) ``month_start``."""
    index = month_start.year * 12 + (month_start.month - 1) - months
    return date(index // 12, index % 12 + 1, 1)


def _month_end(month_start: date) -> date:
    """Last day of the month that ``month_start`` opens."""
    return _month_start_back(month_start, months=-1) - timedelta(days=1)


def build_aggregation_catalog(
    goals_service: GoalsAchievedCounter,
    today: Callable[[], date] = date.today,
) -> dict[str, QueryTool]:
    """Build the aggregation tool catalog — one entry per vetted question shape.

    ``today`` is the injectable clock the period resolver reads; production
    uses the server's date (never one the model volunteered).

    First slice: exactly one tool. Growth is deliberate and reviewed — adding
    an entry means adding the domain's own backend method (per-domain
    completion field, per-domain bound normalisation) and its own tests.
    """

    async def _count_goals_achieved(
        *, user_uid: str, period: AggregationPeriod
    ) -> Result[AggregationCount]:
        since, until = resolve_period(period, today())
        result = await goals_service.count_goals_achieved(
            user_uid=user_uid, since=since, until=until
        )
        if result.is_error:
            return Result.fail(result)
        payload = result.value
        return Result.ok(
            AggregationCount(
                subject="goals achieved",
                total=payload["total"],
                since=payload["since"],
                until=payload["until"],
            )
        )

    return {
        "count_goals_achieved": QueryTool(
            name="count_goals_achieved",
            description=(
                "Count how many goals the user achieved (completed) within a stated "
                "time period. Use ONLY when the question asks for a count of the "
                "user's own achieved/completed goals AND names a time period this "
                "tool's period parameter can express. It cannot filter by anything "
                "else (no categories, no linked habits or tasks, no other entity "
                "kinds) — if the question carries any such constraint, or no time "
                "period, do not use this tool."
            ),
            args_model=CountGoalsAchievedArgs,
            handler=_count_goals_achieved,
        )
    }


def tool_specs(catalog: Mapping[str, QueryTool]) -> list[ToolSpec]:
    """Provider tool specs generated from the SAME pydantic models the executor
    validates with — spec and gate cannot drift apart."""
    return [
        ToolSpec(
            name=tool.name,
            description=tool.description,
            input_schema=tool.args_model.model_json_schema(),
        )
        for tool in catalog.values()
    ]


# ============================================================================
# THE EXECUTOR
# ============================================================================


async def run_tool(
    selection: ToolSelection,
    catalog: Mapping[str, QueryTool],
    *,
    user_uid: str,
) -> Result[AggregationAnswered | AggregationDeclined]:
    """Validate a model's selection and execute it for the AUTHENTICATED user.

    ``user_uid`` comes from the authenticated context, NEVER from the LLM: a
    model-supplied ``user_uid`` argument is discarded before validation and the
    executor injects its own — the cross-tenant invariant this slice exists to
    hold. No tool selected / unknown tool → ``Declined`` (a coverage gap, not a
    failure). Args failing the pydantic gate, or the handler failing →
    ``Result.fail`` (a real failure the caller renders as unavailable — a
    malformed selection must never be presented as a real answer).
    """
    if selection.tool_name is None:
        return Result.ok(AggregationDeclined(reason=_OUT_OF_COVERAGE_REASON))
    tool = catalog.get(selection.tool_name)
    if tool is None:
        logger.warning("Tool selection named unknown tool %r — declining", selection.tool_name)
        return Result.ok(AggregationDeclined(reason=_OUT_OF_COVERAGE_REASON))

    arguments = dict(selection.arguments)
    if "user_uid" in arguments:
        # The one argument we discard by name: identity is server-injected below,
        # and a model that emitted one must not be able to steer it (or trip the
        # extra="forbid" gate into an unavailable for an otherwise-valid call).
        logger.warning("Tool selection smuggled a user_uid argument — discarded")
        arguments.pop("user_uid")

    try:
        args = tool.args_model.model_validate(arguments)
    except ValidationError as exc:
        return Result.fail(
            Errors.validation(f"Tool '{tool.name}' arguments failed validation: {exc}")
        )

    result = await tool.handler(user_uid=user_uid, **args.model_dump())
    if result.is_error:
        return Result.fail(result)
    return Result.ok(AggregationAnswered(payload=result.value))


async def select_and_run(  # skuel-lint: disable=SKUEL005 -- deterministic total outcome: failures fold into AggregationUnavailable, never propagate
    question: str,
    catalog: Mapping[str, QueryTool],
    llm_service: ToolSelector,
    *,
    user_uid: str,
) -> AggregationOutcome:
    """Selection → validation → execution, folded into one deterministic outcome.

    Total by design: a provider or tool failure becomes ``AggregationUnavailable``
    here, so every caller delivers one of the three outcomes and nothing ever
    falls through to generic generation on an AGGREGATION question.
    """
    selection_result = await llm_service.select_tool(
        question,
        tool_specs(catalog),
        system_prompt=PROMPT_REGISTRY.render("askesis_tool_selection"),
    )
    if selection_result.is_error:
        logger.warning(
            "Aggregation tool selection failed: %s", selection_result.expect_error().message
        )
        return AggregationUnavailable(reason="tool selection failed")

    outcome_result = await run_tool(selection_result.value, catalog, user_uid=user_uid)
    if outcome_result.is_error:
        logger.warning(
            "Aggregation tool execution failed: %s", outcome_result.expect_error().message
        )
        return AggregationUnavailable(reason="tool execution failed")
    return outcome_result.value


__all__ = [
    "AggregationAnswered",
    "AggregationCount",
    "AggregationDeclined",
    "AggregationOutcome",
    "AggregationUnavailable",
    "CountGoalsAchievedArgs",
    "GoalsAchievedCounter",
    "QueryTool",
    "ToolSelector",
    "build_aggregation_catalog",
    "resolve_period",
    "run_tool",
    "select_and_run",
    "tool_specs",
]
