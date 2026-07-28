#!/usr/bin/env python3
"""
PrinciplesSearchService Test Suite
====================================

Tests for search and discovery operations in PrinciplesSearchService.

Principles override the harmonized time-query surface with semantics
tailored to long-lived values rather than due dates:
- ``get_active`` uses the ``is_active`` flag (not EntityStatus).
- ``get_overdue`` delegates to ``get_needing_review(days_threshold=90)``.
- ``get_upcoming`` expresses "approaching the 90-day review threshold"
  via ``backend.get_principles_due_for_review``.
"""

from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus
from core.models.enums.principle_enums import AlignmentLevel, PrincipleCategory, PrincipleStrength
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.services.principles.principles_search_service import PrinciplesSearchService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_backend() -> Any:
    backend = Mock()
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.get = AsyncMock()
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    backend.get_principles_due_for_review = AsyncMock(return_value=Result.ok([]))
    backend.get_principles_needing_review = AsyncMock(return_value=Result.ok([]))
    backend.get_principles_by_category = AsyncMock(return_value=Result.ok([]))
    backend.get_related_principles_by_traversal = AsyncMock(return_value=Result.ok([]))
    # Temporal raw helpers — present for completeness; principles overrides bypass them
    backend.upcoming_raw = AsyncMock(return_value=Result.ok([]))
    backend.overdue_raw = AsyncMock(return_value=Result.ok([]))
    backend.active_raw = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def search_service(mock_backend) -> PrinciplesSearchService:
    return PrinciplesSearchService(backend=mock_backend)


def _principle(
    uid: str,
    *,
    title: str = "Principle",
    strength: PrincipleStrength = PrincipleStrength.MODERATE,
    category: PrincipleCategory = PrincipleCategory.PERSONAL,
    is_active: bool = True,
    last_review_date: date | None = None,
    current_alignment: AlignmentLevel | None = AlignmentLevel.ALIGNED,
    user_uid: str = "user_demo",
) -> Principle:
    dto = PrincipleDTO(
        uid=uid,
        title=title,
        user_uid=user_uid,
        status=EntityStatus.ACTIVE,
        statement=f"{title}: statement",
        strength=strength,
        principle_category=category,
        is_active=is_active,
        last_review_date=last_review_date,
        current_alignment=current_alignment,
        created_at=datetime.now(),
    )
    return Principle.from_dto(dto)


@pytest.fixture
def user_context() -> UserContext:
    return UserContext(user_uid="user_demo", username="test_user")


# ============================================================================
# INITIALIZATION
# ============================================================================


def test_init_with_backend(mock_backend):
    service = PrinciplesSearchService(backend=mock_backend)
    assert service.backend == mock_backend


def test_init_without_backend():
    with pytest.raises(ValueError, match=r"[Bb]ackend is REQUIRED"):
        PrinciplesSearchService(backend=None)


# ============================================================================
# HARMONIZED TIME-QUERY SURFACE — DOMAIN-SPECIFIC OVERRIDES
# ============================================================================


@pytest.mark.asyncio
async def test_get_active_uses_is_active_flag(search_service, mock_backend):
    """Principles.get_active filters on is_active=True, not EntityStatus."""
    active = _principle("p:core", strength=PrincipleStrength.CORE, is_active=True)
    mock_backend.find_by.return_value = Result.ok([active.to_dto().to_dict()])

    result = await search_service.get_active(user_uid="user_demo", limit=25)

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["is_active"] is True
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["limit"] == 25
    # Does NOT delegate to the temporal active_raw helper
    mock_backend.active_raw.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_active_sorts_by_strength(search_service, mock_backend):
    """get_active returns CORE before STRONG before MODERATE."""
    core = _principle("p:core", strength=PrincipleStrength.CORE)
    moderate = _principle("p:moderate", strength=PrincipleStrength.MODERATE)
    strong = _principle("p:strong", strength=PrincipleStrength.STRONG)
    mock_backend.find_by.return_value = Result.ok(
        [moderate.to_dto().to_dict(), core.to_dto().to_dict(), strong.to_dto().to_dict()]
    )

    result = await search_service.get_active(user_uid="user_demo")

    assert result.is_ok
    uids = [p.uid for p in result.value]
    assert uids[0] == "p:core"
    # STRONG precedes MODERATE
    assert uids.index("p:strong") < uids.index("p:moderate")


@pytest.mark.asyncio
async def test_get_overdue_delegates_to_needing_review_90_days(search_service, mock_backend):
    """get_overdue is thin delegation to get_needing_review(days_threshold=90)."""
    stale = _principle(
        "p:stale",
        last_review_date=date.today() - timedelta(days=120),
    )
    mock_backend.get_principles_needing_review.return_value = Result.ok([stale.to_dto().to_dict()])

    result = await search_service.get_overdue(user_uid="user_demo", limit=10)

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.get_principles_needing_review.call_args.kwargs
    # 90-day cutoff is today - 90 days
    expected_cutoff = (date.today() - timedelta(days=90)).isoformat()
    assert kwargs["cutoff_date"] == expected_cutoff
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["limit"] == 10
    assert kwargs["prioritize_never_reviewed"] is True
    # No use of the temporal overdue_raw helper
    mock_backend.overdue_raw.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_overdue_error_propagates(search_service, mock_backend):
    mock_backend.get_principles_needing_review.return_value = Result.fail(
        Errors.database("get_principles_needing_review", "db down")
    )

    result = await search_service.get_overdue(user_uid="user_demo")

    assert result.is_error


@pytest.mark.asyncio
async def test_get_upcoming_uses_review_threshold_helper(search_service, mock_backend):
    """get_upcoming computes a cutoff relative to the 90-day review window."""
    due_soon = _principle(
        "p:due",
        last_review_date=date.today() - timedelta(days=75),
    )
    mock_backend.get_principles_due_for_review.return_value = Result.ok(
        [due_soon.to_dto().to_dict()]
    )

    result = await search_service.get_upcoming(days_ahead=30, user_uid="user_demo", limit=20)

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.get_principles_due_for_review.call_args.kwargs
    # cutoff = today - (90 - days_ahead) = today - 60
    expected_cutoff = (date.today() - timedelta(days=60)).isoformat()
    assert kwargs["cutoff_date"] == expected_cutoff
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["limit"] == 20
    mock_backend.upcoming_raw.assert_not_awaited()


# ============================================================================
# PRINCIPLE-SPECIFIC METHODS
# ============================================================================


@pytest.mark.asyncio
async def test_get_by_category(search_service, mock_backend):
    health = _principle("p:health", category=PrincipleCategory.HEALTH)
    mock_backend.find_by.return_value = Result.ok([health.to_dto().to_dict()])

    result = await search_service.get_by_category(PrincipleCategory.HEALTH)

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["category"] == PrincipleCategory.HEALTH.value


@pytest.mark.asyncio
async def test_get_by_status_maps_to_is_active(search_service, mock_backend):
    """get_by_status('active') → find_by(is_active=True)."""
    mock_backend.find_by.return_value = Result.ok([])

    await search_service.get_by_status("active", user_uid="user_demo")

    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["is_active"] is True
    assert kwargs["user_uid"] == "user_demo"


@pytest.mark.asyncio
async def test_get_by_status_inactive(search_service, mock_backend):
    """get_by_status('inactive') → find_by(is_active=False)."""
    mock_backend.find_by.return_value = Result.ok([])

    await search_service.get_by_status("inactive")

    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["is_active"] is False


@pytest.mark.asyncio
async def test_get_needing_review_custom_threshold(search_service, mock_backend):
    mock_backend.get_principles_needing_review.return_value = Result.ok([])

    await search_service.get_needing_review(user_uid="user_demo", days_threshold=30, limit=5)

    kwargs = mock_backend.get_principles_needing_review.call_args.kwargs
    expected_cutoff = (date.today() - timedelta(days=30)).isoformat()
    assert kwargs["cutoff_date"] == expected_cutoff
    assert kwargs["limit"] == 5
    assert kwargs["prioritize_never_reviewed"] is True


@pytest.mark.asyncio
async def test_get_prioritized_filters_active(search_service, mock_backend, user_context):
    """get_prioritized fetches only active principles, then scores them."""
    core = _principle("p:core", strength=PrincipleStrength.CORE, is_active=True)
    weak = _principle("p:weak", strength=PrincipleStrength.EXPLORING, is_active=True)
    mock_backend.find_by.return_value = Result.ok(
        [weak.to_dto().to_dict(), core.to_dto().to_dict()]
    )

    result = await search_service.get_prioritized(user_context, limit=5)

    assert result.is_ok
    assert len(result.value) == 2
    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["is_active"] is True


@pytest.mark.asyncio
async def test_get_related_principles_skips_category_fallback_when_category_is_none(
    search_service, mock_backend
):
    """A principle with no category must not send None into the category query.

    ``Principle.category`` is ``principle_category.value`` falling back to
    ``domain.value``. None is reachable through the production path: the row
    below is what a Cypher map projection yields for a node missing both
    properties, and ``PrincipleDTO.from_dict`` propagates the explicit null
    rather than substituting the field default. Cypher's ``= null`` then
    matches zero rows silently, so the old behaviour was an empty result by
    accident; this asserts it is one on purpose.
    """
    row = {
        "uid": "p:bare",
        "title": "Bare",
        "user_uid": "user_demo",
        "status": EntityStatus.ACTIVE.value,
        "domain": None,
        "principle_category": None,
    }
    # Precondition this test exists for — asserted through the same
    # from_dict/from_dto pair the service uses, not by poking the DTO.
    assert Principle.from_dto(PrincipleDTO.from_dict(row)).category is None

    mock_backend.get_related_principles_by_traversal.return_value = Result.ok([])
    mock_backend.get.return_value = Result.ok(row)

    result = await search_service.get_related_principles("p:bare")

    assert result.is_ok
    assert result.value == []
    mock_backend.get_principles_by_category.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
