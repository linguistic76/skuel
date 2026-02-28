"""
Unit Tests: Principles Utility Method Consolidation
====================================================

Validates that the utility method consolidation applied on 2026-02-28 is
correctly wired.  These are fast, pure-Python tests — no database needed.

Changes verified:
1. `get_principle_categories` → renamed to `list_principle_categories` on
   PrinciplesService, matching the list_*_categories naming used by Goals,
   Habits, and Choices.
2. Custom `list_categories()` removed from PrinciplesSearchService — the
   method returned hardcoded enum values instead of querying the database.
   The correct paths are `list_user_categories(user_uid)` and
   `list_all_categories()` inherited from SearchOperationsMixin.
3. `strength_filter` parameter removed from `get_user_principles()` —
   no callers used it and it mismatched the PrinciplesOperations protocol.
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.principles.principles_core_service import PrinciplesCoreService
from core.services.principles.principles_search_service import PrinciplesSearchService
from core.services.principles_service import PrinciplesService


# ============================================================================
# HELPERS
# ============================================================================


def _make_mock_graph_intel() -> MagicMock:
    return MagicMock()


def _make_mock_backend() -> AsyncMock:
    mock = AsyncMock()
    mock.find_by = AsyncMock(return_value=AsyncMock(is_ok=True, value=[]))
    return mock


def _make_principles_service() -> PrinciplesService:
    """Construct a PrinciplesService with all mocked dependencies."""
    from unittest.mock import AsyncMock, MagicMock

    mock_backend = MagicMock()
    mock_graph_intel = _make_mock_graph_intel()
    return PrinciplesService(
        backend=mock_backend,
        graph_intelligence_service=mock_graph_intel,
    )


def _make_principles_search_service() -> PrinciplesSearchService:
    """Construct PrinciplesSearchService with mocked backend."""
    mock_backend = MagicMock()
    return PrinciplesSearchService(backend=mock_backend)


def _make_principles_core_service() -> PrinciplesCoreService:
    """Construct PrinciplesCoreService with mocked backend."""
    mock_backend = MagicMock()
    return PrinciplesCoreService(backend=mock_backend)


# ============================================================================
# 1. PrinciplesService — method rename
# ============================================================================


class TestPrinciplesServiceMethodRename:
    """Verify the get_principle_categories → list_principle_categories rename."""

    def test_list_principle_categories_exists(self):
        """list_principle_categories must be present on PrinciplesService."""
        service = _make_principles_service()
        assert hasattr(service, "list_principle_categories"), (
            "PrinciplesService is missing list_principle_categories — "
            "was it accidentally removed instead of renamed?"
        )

    def test_list_principle_categories_is_callable(self):
        service = _make_principles_service()
        assert callable(service.list_principle_categories)

    def test_get_principle_categories_no_longer_exists(self):
        """Old name must be gone — callers should be updated to list_principle_categories."""
        service = _make_principles_service()
        assert not hasattr(service, "get_principle_categories"), (
            "get_principle_categories still exists on PrinciplesService. "
            "Remove it or ensure it was renamed to list_principle_categories."
        )

    @pytest.mark.asyncio
    async def test_list_principle_categories_delegates_to_search(self):
        """list_principle_categories must delegate to search.list_user_categories."""
        service = _make_principles_service()
        expected_categories = ["intellectual", "personal"]

        # Mock the search sub-service's list_user_categories
        from core.utils.result_simplified import Result

        service.search.list_user_categories = AsyncMock(return_value=Result.ok(expected_categories))

        result = await service.list_principle_categories("user_test")

        service.search.list_user_categories.assert_called_once_with("user_test")
        assert result.is_ok
        assert result.value == expected_categories

    def test_list_all_principle_categories_exists(self):
        """list_all_principle_categories should also be present on the facade."""
        service = _make_principles_service()
        assert hasattr(service, "list_all_principle_categories"), (
            "list_all_principle_categories is missing from PrinciplesService"
        )

    @pytest.mark.asyncio
    async def test_list_all_principle_categories_delegates_to_search(self):
        """list_all_principle_categories must delegate to search.list_all_categories."""
        service = _make_principles_service()

        from core.utils.result_simplified import Result

        service.search.list_all_categories = AsyncMock(
            return_value=Result.ok(["intellectual", "ethical", "personal"])
        )

        result = await service.list_all_principle_categories()

        service.search.list_all_categories.assert_called_once()
        assert result.is_ok


# ============================================================================
# 2. PrinciplesSearchService — dead list_categories() removed
# ============================================================================


class TestPrinciplesSearchServiceListCategories:
    """Verify the custom list_categories() override was removed."""

    def test_list_categories_does_not_exist(self):
        """PrinciplesSearchService must NOT define list_categories().

        The old override returned hardcoded enum values instead of querying
        the database.  BaseService.list_all_categories() is the correct path.
        """
        assert not hasattr(PrinciplesSearchService, "list_categories") or (
            # The name must not be DEFINED directly on this class (could be inherited)
            "list_categories" not in PrinciplesSearchService.__dict__
        ), (
            "PrinciplesSearchService still defines list_categories(). "
            "This override returned hardcoded enum values — delete it and use "
            "list_all_categories() from SearchOperationsMixin instead."
        )

    def test_list_user_categories_is_available(self):
        """list_user_categories (from BaseService mixin) must be accessible."""
        search = _make_principles_search_service()
        assert hasattr(search, "list_user_categories"), (
            "list_user_categories is missing from PrinciplesSearchService — "
            "check that BaseService SearchOperationsMixin is properly inherited."
        )

    def test_list_all_categories_is_available(self):
        """list_all_categories (from BaseService mixin) must be accessible."""
        search = _make_principles_search_service()
        assert hasattr(search, "list_all_categories"), (
            "list_all_categories is missing from PrinciplesSearchService"
        )

    @pytest.mark.asyncio
    async def test_list_user_categories_is_async(self):
        """list_user_categories must be an async method."""
        search = _make_principles_search_service()
        assert inspect.iscoroutinefunction(search.list_user_categories)

    @pytest.mark.asyncio
    async def test_list_all_categories_is_async(self):
        """list_all_categories must be an async method."""
        search = _make_principles_search_service()
        assert inspect.iscoroutinefunction(search.list_all_categories)


# ============================================================================
# 3. PrinciplesCoreService — strength_filter removed from get_user_principles
# ============================================================================


class TestGetUserPrinciplesSignature:
    """Verify get_user_principles no longer accepts strength_filter."""

    def test_get_user_principles_exists(self):
        core = _make_principles_core_service()
        assert hasattr(core, "get_user_principles")

    def test_get_user_principles_no_strength_filter_param(self):
        """strength_filter was removed to match the PrinciplesOperations protocol.

        No caller ever passed this parameter, and it silently diverged from the
        protocol signature.
        """
        sig = inspect.signature(PrinciplesCoreService.get_user_principles)
        param_names = list(sig.parameters)
        assert "strength_filter" not in param_names, (
            "strength_filter is still present on get_user_principles. "
            "Remove it — no callers use it and it diverges from the protocol."
        )

    def test_get_user_principles_accepts_user_uid(self):
        """The only parameter (beyond self) must be user_uid."""
        sig = inspect.signature(PrinciplesCoreService.get_user_principles)
        params = sig.parameters
        # Remove 'self'
        non_self = {k: v for k, v in params.items() if k != "self"}
        assert "user_uid" in non_self, "user_uid parameter is missing from get_user_principles"

    def test_get_user_principles_only_user_uid_param(self):
        """Exactly one non-self parameter: user_uid."""
        sig = inspect.signature(PrinciplesCoreService.get_user_principles)
        non_self = [k for k in sig.parameters if k != "self"]
        assert non_self == ["user_uid"], (
            f"Unexpected parameters on get_user_principles: {non_self}. "
            "Expected exactly ['user_uid']."
        )

    @pytest.mark.asyncio
    async def test_get_user_principles_returns_result(self):
        """get_user_principles must return a Result without extra arguments."""
        from core.utils.result_simplified import Result

        core = _make_principles_core_service()

        # Simulate a backend that returns an empty list
        from core.models.principle.principle import Principle

        core.backend.find_by = AsyncMock(return_value=Result.ok([]))

        # Must succeed with only user_uid — no strength_filter
        result = await core.get_user_principles(user_uid="user_test")
        assert result.is_ok
        assert result.value == []


# ============================================================================
# 4. Naming consistency across facades — sanity check
# ============================================================================


class TestNamingConsistencyAcrossDomains:
    """All four facade services must follow the same list_*_categories pattern."""

    @pytest.mark.parametrize(
        ("service_module", "service_class", "method_name"),
        [
            (
                "core.services.goals_service",
                "GoalsService",
                "list_goal_categories",
            ),
            (
                "core.services.habits_service",
                "HabitsService",
                "list_habit_categories",
            ),
            (
                "core.services.choices_service",
                "ChoicesService",
                "list_choice_categories",
            ),
            (
                "core.services.principles_service",
                "PrinciplesService",
                "list_principle_categories",
            ),
        ],
    )
    def test_user_category_method_exists(self, service_module, service_class, method_name):
        """Each facade must expose a list_{domain}_categories method."""
        import importlib

        module = importlib.import_module(service_module)
        cls = getattr(module, service_class)
        assert hasattr(cls, method_name), (
            f"{service_class}.{method_name} is missing. "
            "All four facades (Goals, Habits, Choices, Principles) must follow "
            "the list_{domain}_categories naming pattern."
        )

    @pytest.mark.parametrize(
        ("service_module", "service_class", "bad_method"),
        [
            (
                "core.services.principles_service",
                "PrinciplesService",
                "get_principle_categories",
            ),
        ],
    )
    def test_old_method_name_gone(self, service_module, service_class, bad_method):
        """Renamed methods must not linger under the old name."""
        import importlib

        module = importlib.import_module(service_module)
        cls = getattr(module, service_class)
        assert not hasattr(cls, bad_method), (
            f"{service_class}.{bad_method} still exists. "
            "It was renamed — remove the old name entirely."
        )
