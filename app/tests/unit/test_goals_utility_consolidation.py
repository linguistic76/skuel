# mypy: disable-error-code="attr-defined"
"""
Unit Tests: Goals Utility Method Consolidation
===============================================

Validates that the utility method consolidation applied on 2026-02-28 is
correctly wired for the Goals domain.  No database required.

Changes verified:
1. `list_goal_categories()` removed from GoalsCoreService — it was dead code
   that used a raw Cypher query. The live category paths are the
   search sub-service mixin methods `list_user_categories(user_uid)` and
   `list_all_categories()` (used by service introspection).

Note: the facade `list_*_categories` wrapper methods were deleted in the
2026-06 dead-code campaign (zero production callers) — only the sub-service
mixin methods remain.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals_service import GoalsService

# ============================================================================
# HELPERS
# ============================================================================


def _make_mock_backend() -> MagicMock:
    return MagicMock()


def _make_goals_core_service() -> GoalsCoreService:
    """Construct a GoalsCoreService with a mocked backend."""
    mock_backend = _make_mock_backend()
    return GoalsCoreService(backend=mock_backend)


def _make_goals_service() -> GoalsService:
    """Construct a GoalsService facade with mocked dependencies."""
    from unittest.mock import AsyncMock

    mock_backend = _make_mock_backend()
    mock_graph_intel = MagicMock()
    return GoalsService(
        backend=mock_backend,
        graph_intel=mock_graph_intel,
        cross_domain_query=AsyncMock(),
    )


# ============================================================================
# 1. GoalsCoreService — list_goal_categories dead code removed
# ============================================================================


class TestGoalsCoreServiceListCategories:
    """list_goal_categories was dead code on GoalsCoreService — must be gone."""

    def test_list_goal_categories_not_on_core_service(self):
        """GoalsCoreService must NOT define list_goal_categories.

        The method used a raw Cypher query and was never called — the facade
        routes to search.list_user_categories() via BaseService mixin.
        """
        assert "list_goal_categories" not in GoalsCoreService.__dict__, (
            "list_goal_categories still exists directly on GoalsCoreService. "
            "Remove it — the facade delegates to search.list_user_categories()."
        )

    def test_list_all_categories_inherited_from_base(self):
        """list_all_categories must be available via BaseService mixin."""
        core = _make_goals_core_service()
        assert hasattr(core, "list_all_categories"), (
            "list_all_categories is not available on GoalsCoreService. "
            "It should be inherited from BaseService SearchOperationsMixin."
        )

    def test_list_user_categories_inherited_from_base(self):
        """list_user_categories must be available via BaseService mixin."""
        core = _make_goals_core_service()
        assert hasattr(core, "list_user_categories")


# ============================================================================
# 2. GoalsService.cancel_goal — abandonment guard on the facade
# ============================================================================


class TestGoalsServiceAbandonmentGuard:
    """cancel_goal() must enforce the abandonment guard via cross_domain_query."""

    @pytest.mark.asyncio
    async def test_blocks_cancel_when_active_tasks_exist(self):
        """count > 0 → validation error mentioning the count."""
        from core.services.cross_domain import ActiveTaskCount
        from core.utils.result_simplified import Result

        service = _make_goals_service()
        mock_xdq = AsyncMock()
        mock_xdq.count_active_tasks_for_goal.return_value = Result.ok(
            ActiveTaskCount(goal_uid="goal_1", count=2)
        )
        service.cross_domain_query = mock_xdq

        result = await service.cancel_goal("goal_1")

        assert result.is_error
        err = result.expect_error()
        assert "2 active task(s)" in err.message
        mock_xdq.count_active_tasks_for_goal.assert_awaited_once_with("goal_1")

    @pytest.mark.asyncio
    async def test_proceeds_when_zero_active_tasks(self):
        """count == 0 → guard passes, the typed update_goal() path is called."""
        from unittest.mock import patch

        from core.services.cross_domain import ActiveTaskCount
        from core.utils.result_simplified import Result

        service = _make_goals_service()
        mock_xdq = AsyncMock()
        mock_xdq.count_active_tasks_for_goal.return_value = Result.ok(
            ActiveTaskCount(goal_uid="goal_1", count=0)
        )
        service.cross_domain_query = mock_xdq

        sentinel_goal = MagicMock(uid="goal_1", user_uid="u", status="cancelled", created_at=None)
        with patch.object(
            service.core, "update_goal", new=AsyncMock(return_value=Result.ok(sentinel_goal))
        ):
            result = await service.cancel_goal("goal_1")

        assert result.is_ok
        mock_xdq.count_active_tasks_for_goal.assert_awaited_once_with("goal_1")

    @pytest.mark.asyncio
    async def test_proceeds_when_query_fails(self):
        """Query failure → log warning and continue."""
        from unittest.mock import patch

        from core.utils.result_simplified import Errors, Result

        service = _make_goals_service()
        mock_xdq = AsyncMock()
        mock_xdq.count_active_tasks_for_goal.return_value = Result.fail(
            Errors.database(operation="count_active_tasks_for_goal", message="neo4j down")
        )
        service.cross_domain_query = mock_xdq

        sentinel_goal = MagicMock(uid="goal_1", user_uid="u", status="cancelled", created_at=None)
        with patch.object(
            service.core, "update_goal", new=AsyncMock(return_value=Result.ok(sentinel_goal))
        ):
            result = await service.cancel_goal("goal_1")

        assert result.is_ok
        mock_xdq.count_active_tasks_for_goal.assert_awaited_once_with("goal_1")
