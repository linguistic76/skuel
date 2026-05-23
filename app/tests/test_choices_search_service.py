#!/usr/bin/env python3
"""
ChoicesSearchService Test Suite
================================

Tests for search and discovery operations in ChoicesSearchService,
covering the harmonized time-query surface (get_upcoming/get_overdue/
get_active via TimeQueryMixin on the decision_deadline field) and
choice-specific methods (pending/by_urgency/needing_decision).
"""

from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.choice.choice import Choice
from core.models.choice.choice_dto import ChoiceDTO
from core.models.enums import Domain, EntityStatus, Priority
from core.services.choices.choices_search_service import ChoicesSearchService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_backend() -> Any:
    backend = Mock()
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.get_pending_choices = AsyncMock(return_value=Result.ok([]))
    backend.get_choices_needing_decision = AsyncMock(return_value=Result.ok([]))
    backend.upcoming_raw = AsyncMock(return_value=Result.ok([]))
    backend.overdue_raw = AsyncMock(return_value=Result.ok([]))
    backend.active_raw = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def search_service(mock_backend) -> ChoicesSearchService:
    return ChoicesSearchService(backend=mock_backend)


@pytest.fixture
def sample_choices() -> list[Choice]:
    now = datetime.now()
    return [
        Choice.from_dto(
            ChoiceDTO(
                uid="choice:1",
                user_uid="user_demo",
                title="Framework selection",
                domain=Domain.TECH,
                status=EntityStatus.DRAFT,
                priority=Priority.HIGH.value,
                decision_deadline=now + timedelta(days=5),
                created_at=now,
            )
        ),
        Choice.from_dto(
            ChoiceDTO(
                uid="choice:2",
                user_uid="user_demo",
                title="Gym membership",
                domain=Domain.HEALTH,
                status=EntityStatus.COMPLETED,
                priority=Priority.MEDIUM.value,
                decision_deadline=now - timedelta(days=1),
                created_at=now,
            )
        ),
    ]


@pytest.fixture
def user_context() -> UserContext:
    return UserContext(user_uid="user_demo", username="test_user")


# ============================================================================
# INITIALIZATION
# ============================================================================


def test_init_with_backend(mock_backend):
    service = ChoicesSearchService(backend=mock_backend)
    assert service.backend == mock_backend


def test_init_without_backend():
    with pytest.raises(ValueError, match=r"choices\.search backend is REQUIRED"):
        ChoicesSearchService(backend=None)


# ============================================================================
# HARMONIZED TIME-QUERY SURFACE
# ============================================================================


@pytest.mark.asyncio
async def test_get_upcoming_uses_decision_deadline(search_service, mock_backend, sample_choices):
    """Choices.get_upcoming forwards decision_deadline as the date_field."""
    mock_backend.upcoming_raw.return_value = Result.ok(
        [c.to_dto().to_dict() for c in sample_choices[:1]]
    )

    result = await search_service.get_upcoming(days_ahead=10, user_uid="user_demo")

    assert result.is_ok
    kwargs = mock_backend.upcoming_raw.call_args.kwargs
    assert kwargs["date_field"] == "decision_deadline"
    assert kwargs["days_ahead"] == 10
    assert kwargs["user_uid"] == "user_demo"


@pytest.mark.asyncio
async def test_get_upcoming_excludes_completed(search_service, mock_backend):
    """Default temporal_exclude_statuses hide COMPLETED decisions."""
    mock_backend.upcoming_raw.return_value = Result.ok([])

    await search_service.get_upcoming()

    kwargs = mock_backend.upcoming_raw.call_args.kwargs
    assert "completed" in kwargs["exclude_statuses"]


@pytest.mark.asyncio
async def test_get_overdue_uses_decision_deadline(search_service, mock_backend):
    mock_backend.overdue_raw.return_value = Result.ok([])

    await search_service.get_overdue(user_uid="user_demo", limit=10)

    kwargs = mock_backend.overdue_raw.call_args.kwargs
    assert kwargs["date_field"] == "decision_deadline"
    assert kwargs["limit"] == 10


@pytest.mark.asyncio
async def test_get_overdue_error_propagates(search_service, mock_backend):
    mock_backend.overdue_raw.return_value = Result.fail(Errors.database("overdue_raw", "down"))

    result = await search_service.get_overdue()

    assert result.is_error


@pytest.mark.asyncio
async def test_get_active_success(search_service, mock_backend, sample_choices):
    mock_backend.active_raw.return_value = Result.ok(
        [c.to_dto().to_dict() for c in sample_choices[:1]]
    )

    result = await search_service.get_active(user_uid="user_demo", limit=25)

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.active_raw.call_args.kwargs
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["limit"] == 25


@pytest.mark.asyncio
async def test_get_active_requires_user_uid(search_service, mock_backend):
    result = await search_service.get_active(user_uid="")

    assert result.is_error
    mock_backend.active_raw.assert_not_awaited()


# ============================================================================
# CHOICE-SPECIFIC METHODS
# ============================================================================


@pytest.mark.asyncio
async def test_get_pending_delegates_to_backend(search_service, mock_backend, sample_choices):
    pending = [c for c in sample_choices if c.status != EntityStatus.COMPLETED]
    mock_backend.get_pending_choices.return_value = Result.ok(
        [c.to_dto().to_dict() for c in pending]
    )

    result = await search_service.get_pending(user_uid="user_demo", limit=50)

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.get_pending_choices.call_args.kwargs
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["limit"] == 50


@pytest.mark.asyncio
async def test_get_by_urgency_with_user(search_service, mock_backend, sample_choices):
    high = [c for c in sample_choices if c.priority == Priority.HIGH]
    mock_backend.find_by.return_value = Result.ok([c.to_dto().to_dict() for c in high])

    result = await search_service.get_by_urgency("high", user_uid="user_demo")

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["urgency"] == "high"
    assert kwargs["user_uid"] == "user_demo"


@pytest.mark.asyncio
async def test_get_needing_decision_forwards_deadline(search_service, mock_backend):
    mock_backend.get_choices_needing_decision.return_value = Result.ok([])

    await search_service.get_needing_decision(user_uid="user_demo", deadline_days=3)

    kwargs = mock_backend.get_choices_needing_decision.call_args.kwargs
    assert kwargs["user_uid"] == "user_demo"
    expected_end = (date.today() + timedelta(days=3)).isoformat()
    assert kwargs["end_date"] == expected_end


@pytest.mark.asyncio
async def test_get_prioritized_filters_terminal(search_service, mock_backend, user_context):
    """get_prioritized fetches user choices and excludes terminal states."""
    now = datetime.now()
    draft = ChoiceDTO(
        uid="choice:draft",
        user_uid="user_demo",
        title="Draft",
        domain=Domain.TECH,
        status=EntityStatus.DRAFT,
        priority=Priority.HIGH.value,
        created_at=now,
    )
    completed = ChoiceDTO(
        uid="choice:done",
        user_uid="user_demo",
        title="Done",
        domain=Domain.HEALTH,
        status=EntityStatus.COMPLETED,
        priority=Priority.MEDIUM.value,
        created_at=now,
    )
    mock_backend.find_by.return_value = Result.ok([draft.to_dict(), completed.to_dict()])

    result = await search_service.get_prioritized(user_context, limit=5)

    assert result.is_ok
    assert len(result.value) == 1
    assert result.value[0].uid == "choice:draft"


# ============================================================================
# INTELLIGENT SEARCH
# ============================================================================


@pytest.mark.asyncio
async def test_intelligent_search_urgent_maps_to_critical(search_service, mock_backend):
    mock_backend.find_by.return_value = Result.ok([])

    await search_service.intelligent_search("urgent choices")

    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["priority"] == Priority.CRITICAL.value


@pytest.mark.asyncio
async def test_intelligent_search_pending_maps_to_draft(search_service, mock_backend):
    """'pending' decision state maps to EntityStatus.DRAFT."""
    mock_backend.find_by.return_value = Result.ok([])

    await search_service.intelligent_search("pending choices")

    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["status"] == EntityStatus.DRAFT.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
