"""SearchRouter._score_results habit enrichment — through the facade's real shape.

Regression guard for the defect the explicit-DI conversion surfaced (SoC arc
PR 13): the old ``getattr(habits_service, "backend", None)`` reach could never
find a backend on the real ``HabitsService`` facade (which exposes ``.core`` /
``.search`` but no ``.backend`` attribute), so goal-link enrichment silently
never ran. The router now goes through the facade's ``.search`` sub-service
(``enrich_with_goal_links``), which owns the backend legitimately.

Proven red against the pre-change ``_score_results`` body (getattr reach on a
facade-shaped double finds no backend → marker never applied).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityType
from core.orchestrator.search_router import SearchResultItem, SearchRouter


def _habit_item(uid: str) -> SearchResultItem:
    entity = SimpleNamespace(uid=uid, title="Morning run", tags=())
    return SearchResultItem(
        entity=entity, entity_type=EntityType.HABIT, uid=uid, title="Morning run"
    )


class TestScoreResultsHabitEnrichment:
    @pytest.mark.anyio
    async def test_enrichment_flows_through_the_facade_search_sub_service(self) -> None:
        """The enriched habit (goal link populated) is what gets scored, and the
        enrichment call goes through habits.search — the shape the real facade has."""
        enriched_habit = SimpleNamespace(uid="habit_1", title="Morning run", tags=())
        habits_facade = SimpleNamespace(
            search=SimpleNamespace(enrich_with_goal_links=AsyncMock(return_value=[enriched_habit])),
        )
        router = SearchRouter(habits=habits_facade)
        user_context = MagicMock(active_goal_uids=["goal_1"])

        scored = await router._score_results([_habit_item("habit_1")], user_context)

        habits_facade.search.enrich_with_goal_links.assert_awaited_once()
        args = habits_facade.search.enrich_with_goal_links.await_args.args
        assert [h.uid for h in args[0]] == ["habit_1"]
        assert args[1] == ["goal_1"]
        assert scored[0].entity is enriched_habit

    @pytest.mark.anyio
    async def test_no_habits_service_fails_soft(self) -> None:
        """Without a habits dependency the scoring path skips enrichment quietly."""
        router = SearchRouter()
        user_context = MagicMock(active_goal_uids=[])

        scored = await router._score_results([_habit_item("habit_1")], user_context)

        assert scored[0].uid == "habit_1"
