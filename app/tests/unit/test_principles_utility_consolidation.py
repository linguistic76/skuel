"""
Unit Tests: Principles Utility Method Consolidation
====================================================

Validates that the utility method consolidation applied on 2026-02-28 is
correctly wired.  These are fast, pure-Python tests — no database needed.

Changes verified:
1. Custom `list_categories()` removed from PrinciplesSearchService — the
   method returned hardcoded enum values instead of querying the database.
   The correct paths are `list_user_categories(user_uid)` and
   `list_all_categories()` inherited from SearchOperationsMixin.
2. `strength_filter` parameter removed from `get_user_principles()` —
   no callers used it and it mismatched the PrinciplesOperations protocol.

Note: the facade `list_*_categories` wrapper methods (and the old
`get_principle_categories` name) were deleted in the 2026-06 dead-code
campaign (zero production callers) — only the sub-service mixin methods
remain.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.principles.principles_core_service import PrinciplesCoreService
from core.services.principles.principles_search_service import PrinciplesSearchService

# ============================================================================
# HELPERS
# ============================================================================


def _make_principles_search_service() -> PrinciplesSearchService:
    """Construct PrinciplesSearchService with mocked backend."""
    mock_backend = MagicMock()
    return PrinciplesSearchService(backend=mock_backend)


def _make_principles_core_service() -> PrinciplesCoreService:
    """Construct PrinciplesCoreService with mocked backend."""
    mock_backend = MagicMock()
    return PrinciplesCoreService(backend=mock_backend)


# ============================================================================
# 1. PrinciplesSearchService — dead list_categories() removed
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
# 2. PrinciplesCoreService — strength_filter removed from get_user_principles
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

        core.backend.find_by = AsyncMock(return_value=Result.ok([]))

        # Must succeed with only user_uid — no strength_filter
        result = await core.get_user_principles(user_uid="user_test")
        assert result.is_ok
        assert result.value == []
