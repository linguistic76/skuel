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
    SuggestedActivity,
    build_suggestions,
    metadata_with_cached_suggestions,
    read_cached_suggestions,
    render_suggestion_line,
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

    def test_preserves_non_canonical_bridge_metadata(self):
        # The bridge emits loose tags the strict parser can't normalise
        # (@when(Friday), @priority(high)). They must survive verbatim, not be
        # silently dropped — the user refines them when curating.
        result = build_suggestions(["- @context(task) Finish report @when(Friday) @priority(high)"])
        assert len(result) == 1
        line = result[0].dsl_line
        assert line.startswith("- [ ] Finish report @context(task)")
        assert "@when(Friday)" in line
        assert "@priority(high)" in line


class TestRenderSuggestionLine:
    def test_preserves_tag_order_and_values(self):
        parsed = ActivityDSLParser().parse_line("- @context(habit) Gym @repeat(weekly:Mon,Wed,Fri)")
        assert parsed.is_ok
        assert render_suggestion_line(parsed.value) == (
            "- [ ] Gym @context(habit) @repeat(weekly:Mon,Wed,Fri)"
        )

    def test_bare_line_has_checkbox_and_context(self):
        parsed = ActivityDSLParser().parse_line("- @context(goal) Launch")
        assert parsed.is_ok
        assert render_suggestion_line(parsed.value) == "- [ ] Launch @context(goal)"

    def test_canonicalises_context_alias(self):
        # @context value is rebuilt from the parsed EntityType (alias → canonical).
        parsed = ActivityDSLParser().parse_line("- @context(ps) Read chapter @duration(30m)")
        assert parsed.is_ok
        line = render_suggestion_line(parsed.value)
        assert "@context(path_step)" in line
        assert "@duration(30m)" in line


# ---------------------------------------------------------------------------
# Memoisation (UserEntry.metadata cache)
# ---------------------------------------------------------------------------


class TestSuggestionCache:
    def _items(self):
        return [
            SuggestedActivity(
                domain="task", dsl_line="- [ ] Ship @context(task)", description="Ship"
            )
        ]

    def test_round_trip_returns_same_items(self):
        content = "ship the site by friday"
        meta = metadata_with_cached_suggestions({}, self._items(), content)
        cached = read_cached_suggestions(meta, content)
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].domain == "task"
        assert cached[0].dsl_line == "- [ ] Ship @context(task)"
        assert cached[0].description == "Ship"

    def test_preserves_existing_metadata_keys(self):
        meta = metadata_with_cached_suggestions({"entry_kind": "daily"}, self._items(), "content")
        assert meta["entry_kind"] == "daily"
        assert "suggested_activities" in meta

    def test_absent_cache_returns_none(self):
        assert read_cached_suggestions({}, "anything") is None

    def test_stale_fingerprint_returns_none(self):
        meta = metadata_with_cached_suggestions({}, self._items(), "original text")
        # Source text changed since the cache was written → recompute.
        assert read_cached_suggestions(meta, "edited text") is None

    def test_grounding_change_invalidates_cache(self):
        # Same entry text, but the active-goal grounding changed (goal added /
        # renamed / completed) → recompute, don't serve goal-stale suggestions.
        content = "thoughts on the marathon"
        meta = metadata_with_cached_suggestions({}, self._items(), content, "Run a marathon")
        assert read_cached_suggestions(meta, content, "Run a marathon") is not None
        assert read_cached_suggestions(meta, content, "Run a 5k") is None
        assert read_cached_suggestions(meta, content, "") is None

    def test_cached_empty_returns_empty_list_not_none(self):
        # A recognised-nothing result is cached; the None vs [] distinction is
        # what lets the route skip the LLM on a prose-only entry.
        content = "just a feeling, nothing actionable"
        meta = metadata_with_cached_suggestions({}, [], content)
        cached = read_cached_suggestions(meta, content)
        assert cached == []

    def test_malformed_cache_payload_returns_none(self):
        assert read_cached_suggestions({"suggested_activities": "corrupt"}, "x") is None
        assert read_cached_suggestions({"suggested_activities": {}}, "x") is None


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


class TestSuggestionGrounding:
    @pytest.mark.asyncio
    async def test_no_bridge_returns_empty(self):
        # CORE tier: no grounding signal, so the cache key carries no goal axis.
        service = _make_service(dsl_bridge=None)
        result = await service.suggestion_grounding("user_mike")
        assert result.is_ok
        assert result.value == ""

    @pytest.mark.asyncio
    async def test_digests_active_goal_titles(self):
        bridge = MagicMock()
        g1, g2 = MagicMock(), MagicMock()
        g1.title, g2.title = "Run a marathon", "Ship SKUEL"
        goals_service = MagicMock()
        goals_service.get_active = AsyncMock(return_value=Result.ok([g1, g2]))
        service = _make_service(dsl_bridge=bridge, goals_service=goals_service)

        result = await service.suggestion_grounding("user_mike")
        assert result.is_ok
        assert result.value == "Run a marathon\nShip SKUEL"

    @pytest.mark.asyncio
    async def test_goals_error_propagates(self):
        # A goals-query failure surfaces so the route can degrade to text-only
        # keying, rather than silently keying on empty grounding.
        bridge = MagicMock()
        goals_service = MagicMock()
        goals_service.get_active = AsyncMock(
            return_value=Result.fail(Errors.database("get_active", "boom"))
        )
        service = _make_service(dsl_bridge=bridge, goals_service=goals_service)

        result = await service.suggestion_grounding("user_mike")
        assert result.is_error

    @pytest.mark.asyncio
    async def test_matches_suggest_activities_grounding_source(self):
        # Both paths must read the same active-goal titles, or the cache key
        # would drift from the context that produced the suggestions.
        bridge = MagicMock()
        bridge.transform_with_context = AsyncMock(
            return_value=Result.ok(
                DSLTransformResult(original_text="x", transformed_text="", activity_lines=[])
            )
        )
        goal = MagicMock()
        goal.title = "Run a marathon"
        goals_service = MagicMock()
        goals_service.get_active = AsyncMock(return_value=Result.ok([goal]))
        service = _make_service(dsl_bridge=bridge, goals_service=goals_service)

        grounding = await service.suggestion_grounding("user_mike")
        await service.suggest_activities("training thoughts", "user_mike")

        _, kwargs = bridge.transform_with_context.call_args
        assert grounding.is_ok
        assert [g["title"] for g in kwargs["active_goals"]] == grounding.value.split("\n")
