"""Tests for journal activity suggestions (bridge → paste-ready DSL).

Covers the pure builder/renderer (`core/services/journal/suggestion.py`) and
`JournalService.suggest_activities` (bridge orchestration + tier/error handling).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.dsl.activity_dsl_parser import ActivityDSLParser
from core.services.dsl.llm_dsl_bridge import DSLTransformResult
from core.services.journal.journal_service import JournalService
from core.services.journal.suggestion import (
    build_suggestions,
    render_canonical_dsl,
)
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Pure builder / renderer
# ---------------------------------------------------------------------------


class TestBuildSuggestions:
    def test_renders_canonical_checkbox_form(self):
        # Bridge emits tag-first, no checkbox; builder must canonicalise.
        lines = ["- @context(task) Email landlord @when(2026-07-02T09:00) @priority(1)"]
        result = build_suggestions(lines)
        assert len(result) == 1
        item = result[0]
        assert item.domain == "task"
        assert item.dsl_line.startswith("- [ ] Email landlord")
        assert "@context(task)" in item.dsl_line
        assert "@when(2026-07-02T09:00)" in item.dsl_line
        assert "@priority(1)" in item.dsl_line
        assert item.description == "Email landlord"

    def test_drops_lines_without_context(self):
        result = build_suggestions(["just some prose with no tag"])
        assert result == []

    def test_drops_lines_with_empty_description(self):
        # @context present but nothing to describe → not a usable suggestion.
        result = build_suggestions(["- @context(task)"])
        assert result == []

    def test_groups_multiple_domains(self):
        lines = [
            "- @context(task) Ship the site",
            "- @context(habit) Meditate @repeat(daily)",
            "- @context(choice) Pick a CRM",
        ]
        result = build_suggestions(lines)
        assert [i.domain for i in result] == ["task", "habit", "choice"]

    def test_empty_input(self):
        assert build_suggestions([]) == []

    def test_renders_repeat_and_duration(self):
        result = build_suggestions(["- @context(habit) Meditate @repeat(daily) @duration(20m)"])
        assert len(result) == 1
        assert "@repeat(daily)" in result[0].dsl_line
        assert "@duration(20m)" in result[0].dsl_line


class TestRenderCanonicalDsl:
    def test_weekly_repeat_roundtrips(self):
        parsed = ActivityDSLParser().parse_line("- @context(habit) Gym @repeat(weekly:Mon,Wed,Fri)")
        assert parsed.is_ok
        line = render_canonical_dsl(parsed.value)
        assert line == "- [ ] Gym @context(habit) @repeat(weekly:Mon,Wed,Fri)"

    def test_bare_line_has_checkbox_and_context(self):
        parsed = ActivityDSLParser().parse_line("- @context(goal) Launch")
        assert parsed.is_ok
        assert render_canonical_dsl(parsed.value) == "- [ ] Launch @context(goal)"


# ---------------------------------------------------------------------------
# JournalService.suggest_activities
# ---------------------------------------------------------------------------


def _make_service(dsl_bridge=None, goals_service=None):
    return JournalService(
        llm_caller=MagicMock(),
        user_entry_service=MagicMock(),
        goals_service=goals_service,
        dsl_bridge=dsl_bridge,
    )


class TestSuggestActivities:
    @pytest.mark.asyncio
    async def test_no_bridge_returns_empty_not_error(self):
        service = _make_service(dsl_bridge=None)
        result = await service.suggest_activities("write the report by friday", "user_mike")
        assert result.is_ok
        assert result.value == []

    @pytest.mark.asyncio
    async def test_blank_content_returns_empty(self):
        bridge = MagicMock()
        bridge.transform_with_context = AsyncMock()
        service = _make_service(dsl_bridge=bridge)
        result = await service.suggest_activities("   ", "user_mike")
        assert result.is_ok
        assert result.value == []
        bridge.transform_with_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_happy_path_builds_suggestions(self):
        transform = DSLTransformResult(
            original_text="x",
            transformed_text="y",
            activity_lines=["- @context(task) Email landlord @when(2026-07-02T09:00)"],
        )
        bridge = MagicMock()
        bridge.transform_with_context = AsyncMock(return_value=Result.ok(transform))
        service = _make_service(dsl_bridge=bridge)

        result = await service.suggest_activities("email the landlord friday", "user_mike")

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0].domain == "task"
        assert result.value[0].dsl_line.startswith("- [ ] Email landlord")

    @pytest.mark.asyncio
    async def test_bridge_error_propagates(self):
        bridge = MagicMock()
        bridge.transform_with_context = AsyncMock(
            return_value=Result.fail(Errors.integration("OpenAI", "boom"))
        )
        service = _make_service(dsl_bridge=bridge)
        result = await service.suggest_activities("something", "user_mike")
        assert result.is_error

    @pytest.mark.asyncio
    async def test_grounds_in_active_goals(self):
        transform = DSLTransformResult(original_text="x", transformed_text="", activity_lines=[])
        bridge = MagicMock()
        bridge.transform_with_context = AsyncMock(return_value=Result.ok(transform))
        goal = MagicMock()
        goal.title = "Run a marathon"
        goals_service = MagicMock()
        # get_active (not get_user_goals) so terminal goals don't leak in.
        goals_service.get_active = AsyncMock(return_value=Result.ok([goal]))
        service = _make_service(dsl_bridge=bridge, goals_service=goals_service)

        await service.suggest_activities("training thoughts", "user_mike")

        _, kwargs = bridge.transform_with_context.call_args
        assert kwargs["active_goals"] == [{"title": "Run a marathon"}]
        goals_service.get_active.assert_awaited_once_with("user_mike", limit=10)
