"""
Unit Tests: Goals Utility Method Consolidation
===============================================

Validates that the utility method consolidation applied on 2026-02-28 is
correctly wired for the Goals domain.  No database required.

Changes verified:
1. `list_goal_categories()` removed from GoalsCoreService — it was dead code
   that used a raw Cypher query, never called by the facade (which correctly
   delegates to search.list_user_categories).
2. GoalsService facade correctly delegates:
   - list_goal_categories     → search.list_user_categories(user_uid)
   - list_all_goal_categories → search.list_all_categories()
"""

from __future__ import annotations

import inspect
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
    mock_backend = _make_mock_backend()
    mock_graph_intel = MagicMock()
    return GoalsService(
        backend=mock_backend,
        graph_intelligence_service=mock_graph_intel,
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
# 2. GoalsService facade — delegation routing
# ============================================================================


class TestGoalsServiceCategoryDelegation:
    """GoalsService facade must delegate category queries to the search sub-service."""

    def test_list_goal_categories_exists_on_facade(self):
        """list_goal_categories must be present on GoalsService."""
        service = _make_goals_service()
        assert hasattr(service, "list_goal_categories")

    def test_list_all_goal_categories_exists_on_facade(self):
        """list_all_goal_categories must be present on GoalsService."""
        service = _make_goals_service()
        assert hasattr(service, "list_all_goal_categories")

    @pytest.mark.asyncio
    async def test_list_goal_categories_delegates_to_search_list_user_categories(self):
        """list_goal_categories must call search.list_user_categories, not core."""
        from core.utils.result_simplified import Result

        service = _make_goals_service()
        service.search.list_user_categories = AsyncMock(
            return_value=Result.ok(["health", "career"])
        )

        result = await service.list_goal_categories("user_test_123")

        service.search.list_user_categories.assert_called_once_with("user_test_123")
        assert result.is_ok
        assert result.value == ["health", "career"]

    @pytest.mark.asyncio
    async def test_list_all_goal_categories_delegates_to_search_list_all_categories(self):
        """list_all_goal_categories must call search.list_all_categories (no user filter)."""
        from core.utils.result_simplified import Result

        service = _make_goals_service()
        service.search.list_all_categories = AsyncMock(
            return_value=Result.ok(["health", "career", "learning", "personal"])
        )

        result = await service.list_all_goal_categories()

        service.search.list_all_categories.assert_called_once()
        assert result.is_ok

    @pytest.mark.asyncio
    async def test_list_goal_categories_does_not_call_core(self):
        """list_goal_categories must not touch core sub-service at all."""
        from core.utils.result_simplified import Result

        service = _make_goals_service()
        # Mock search to succeed
        service.search.list_user_categories = AsyncMock(return_value=Result.ok([]))
        # Spy on core — it must not be called
        service.core.list_goal_categories = AsyncMock()

        await service.list_goal_categories("user_test_123")

        service.core.list_goal_categories.assert_not_called()


# ============================================================================
# 3. Naming consistency — all four domains follow the same pattern
# ============================================================================


class TestAllDomainsHaveListCategoriesMethods:
    """Goals, Habits, Choices, and Principles facades must expose consistent names."""

    @pytest.mark.parametrize(
        ("service_module", "service_class", "user_method", "all_method"),
        [
            (
                "core.services.goals_service",
                "GoalsService",
                "list_goal_categories",
                "list_all_goal_categories",
            ),
            (
                "core.services.habits_service",
                "HabitsService",
                "list_habit_categories",
                "list_all_habit_categories",
            ),
            (
                "core.services.choices_service",
                "ChoicesService",
                "list_choice_categories",
                "list_all_choice_categories",
            ),
            (
                "core.services.principles_service",
                "PrinciplesService",
                "list_principle_categories",
                "list_all_principle_categories",
            ),
        ],
    )
    def test_both_category_methods_exist(
        self, service_module, service_class, user_method, all_method
    ):
        """Each facade must have both user-scoped and all-scoped category methods."""
        import importlib

        module = importlib.import_module(service_module)
        cls = getattr(module, service_class)

        assert hasattr(cls, user_method), f"{service_class}.{user_method} is missing"
        assert hasattr(cls, all_method), f"{service_class}.{all_method} is missing"

    def test_no_core_service_defines_list_goal_categories(self):
        """list_goal_categories must not be defined directly on GoalsCoreService."""
        assert "list_goal_categories" not in GoalsCoreService.__dict__
