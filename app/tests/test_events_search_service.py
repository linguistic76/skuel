#!/usr/bin/env python3
"""
EventsSearchService Test Suite
===============================

Tests for search and discovery operations in EventsSearchService, with
emphasis on the harmonized time-query surface (get_upcoming/get_overdue/
get_active — delegated to TimeQueryMixin) and event-specific methods
(date-range queries, recurring events, conflicts).
"""

from datetime import date, datetime, time, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import Domain, EntityStatus
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.services.events.events_search_service import EventsSearchService
from core.utils.result_simplified import Errors, Result

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_backend() -> Any:
    backend = Mock()
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.get = AsyncMock()
    backend.get_events_in_range = AsyncMock(return_value=Result.ok([]))
    backend.get_events_on_date = AsyncMock(return_value=Result.ok([]))
    backend.get_recurring_events = AsyncMock(return_value=Result.ok([]))
    backend.get_completed_events_in_range = AsyncMock(return_value=Result.ok([]))
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    # Temporal raw helpers
    backend.upcoming_raw = AsyncMock(return_value=Result.ok([]))
    backend.overdue_raw = AsyncMock(return_value=Result.ok([]))
    backend.active_raw = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def search_service(mock_backend) -> EventsSearchService:
    return EventsSearchService(backend=mock_backend)


@pytest.fixture
def sample_events() -> list[Event]:
    today = date.today()
    return [
        Event.from_dto(
            EventDTO(
                uid="event:1",
                title="Team standup",
                user_uid="user_demo",
                domain=Domain.BUSINESS,
                status=EntityStatus.SCHEDULED,
                event_date=today + timedelta(days=1),
                start_time=time(9, 0),
                end_time=time(9, 30),
                event_type="meeting",
                recurrence_pattern="daily",
                created_at=datetime.now(),
            )
        ),
        Event.from_dto(
            EventDTO(
                uid="event:2",
                title="Doctor appointment",
                user_uid="user_demo",
                domain=Domain.HEALTH,
                status=EntityStatus.SCHEDULED,
                event_date=today + timedelta(days=3),
                start_time=time(14, 0),
                end_time=time(15, 0),
                event_type="appointment",
                created_at=datetime.now(),
            )
        ),
        Event.from_dto(
            EventDTO(
                uid="event:past",
                title="Last week conference",
                user_uid="user_demo",
                domain=Domain.BUSINESS,
                status=EntityStatus.COMPLETED,
                event_date=today - timedelta(days=7),
                event_type="conference",
                created_at=datetime.now(),
            )
        ),
    ]


# ============================================================================
# INITIALIZATION
# ============================================================================


def test_init_with_backend(mock_backend):
    service = EventsSearchService(backend=mock_backend)
    assert service.backend == mock_backend


def test_init_without_backend():
    with pytest.raises(ValueError, match=r"events\.search backend is REQUIRED"):
        EventsSearchService(backend=None)


# ============================================================================
# HARMONIZED TIME-QUERY SURFACE (inherited from TimeQueryMixin)
# ============================================================================


@pytest.mark.asyncio
async def test_get_upcoming_uses_event_date(search_service, mock_backend, sample_events):
    """Events.get_upcoming forwards event_date as the date_field."""
    mock_backend.upcoming_raw.return_value = Result.ok(
        [e.to_dto().to_dict() for e in sample_events[:2]]
    )

    result = await search_service.get_upcoming(days_ahead=14, user_uid="user_demo", limit=20)

    assert result.is_ok
    assert len(result.value) == 2
    kwargs = mock_backend.upcoming_raw.call_args.kwargs
    assert kwargs["date_field"] == "event_date"
    assert kwargs["days_ahead"] == 14
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["limit"] == 20


@pytest.mark.asyncio
async def test_get_upcoming_uses_secondary_sort(search_service, mock_backend):
    """Events configure secondary_sort=start_time via DomainConfig."""
    mock_backend.upcoming_raw.return_value = Result.ok([])

    await search_service.get_upcoming()

    kwargs = mock_backend.upcoming_raw.call_args.kwargs
    assert kwargs["secondary_sort_field"] == "start_time"


@pytest.mark.asyncio
async def test_get_overdue_uses_event_date(search_service, mock_backend):
    mock_backend.overdue_raw.return_value = Result.ok([])

    await search_service.get_overdue(user_uid="user_demo", limit=50)

    kwargs = mock_backend.overdue_raw.call_args.kwargs
    assert kwargs["date_field"] == "event_date"
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["limit"] == 50


@pytest.mark.asyncio
async def test_get_overdue_error_propagates(search_service, mock_backend):
    mock_backend.overdue_raw.return_value = Result.fail(Errors.database("overdue_raw", "fail"))

    result = await search_service.get_overdue()

    assert result.is_error


@pytest.mark.asyncio
async def test_get_active_success(search_service, mock_backend, sample_events):
    mock_backend.active_raw.return_value = Result.ok(
        [e.to_dto().to_dict() for e in sample_events[:2]]
    )

    result = await search_service.get_active(user_uid="user_demo")

    assert result.is_ok
    assert len(result.value) == 2
    kwargs = mock_backend.active_raw.call_args.kwargs
    assert kwargs["user_uid"] == "user_demo"
    assert "completed" in kwargs["exclude_statuses"]


@pytest.mark.asyncio
async def test_get_active_requires_user_uid(search_service, mock_backend):
    result = await search_service.get_active(user_uid="")

    assert result.is_error
    mock_backend.active_raw.assert_not_awaited()


# ============================================================================
# EVENT-SPECIFIC METHODS
# ============================================================================


@pytest.mark.asyncio
async def test_get_in_range(search_service, mock_backend, sample_events):
    today = date.today()
    mock_backend.get_events_in_range.return_value = Result.ok(
        [e.to_dto().to_dict() for e in sample_events[:2]]
    )

    result = await search_service.get_in_range(
        start_date=today, end_date=today + timedelta(days=7), user_uid="user_demo"
    )

    assert result.is_ok
    assert len(result.value) == 2
    kwargs = mock_backend.get_events_in_range.call_args.kwargs
    assert kwargs["start_date"] == today.isoformat()
    assert kwargs["end_date"] == (today + timedelta(days=7)).isoformat()


@pytest.mark.asyncio
async def test_get_recurring(search_service, mock_backend, sample_events):
    recurring = [e for e in sample_events if e.recurrence_pattern is not None]
    mock_backend.get_recurring_events.return_value = Result.ok(
        [e.to_dto().to_dict() for e in recurring]
    )

    result = await search_service.get_recurring(user_uid="user_demo")

    assert result.is_ok
    assert len(result.value) == 1


@pytest.mark.asyncio
async def test_get_by_type(search_service, mock_backend, sample_events):
    meetings = [e for e in sample_events if e.event_type == "meeting"]
    mock_backend.find_by.return_value = Result.ok([e.to_dto().to_dict() for e in meetings])

    result = await search_service.get_by_type("meeting", user_uid="user_demo")

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["event_type"] == "meeting"
    assert kwargs["user_uid"] == "user_demo"


@pytest.mark.asyncio
async def test_get_history_uses_completed_events(search_service, mock_backend):
    mock_backend.get_completed_events_in_range.return_value = Result.ok([])

    await search_service.get_history(user_uid="user_demo", days_back=30)

    kwargs = mock_backend.get_completed_events_in_range.call_args.kwargs
    assert kwargs["user_uid"] == "user_demo"
    today = date.today()
    assert kwargs["end_date"] == today.isoformat()
    assert kwargs["start_date"] == (today - timedelta(days=30)).isoformat()


@pytest.mark.asyncio
async def test_get_conflicting_detects_overlap(search_service, mock_backend, sample_events):
    """Two events on same date with overlapping times are conflicts."""
    target = sample_events[0]  # 9:00-9:30
    overlapper = EventDTO(
        uid="event:overlap",
        title="Other meeting",
        user_uid="user_demo",
        event_date=target.event_date,
        start_time=time(9, 15),  # starts during target
        end_time=time(10, 0),
        created_at=datetime.now(),
    )

    mock_backend.get.return_value = Result.ok(target.to_dto().to_dict())
    mock_backend.get_events_on_date.return_value = Result.ok([overlapper.to_dict()])

    result = await search_service.get_conflicting("event:1")

    assert result.is_ok
    assert len(result.value) == 1
    assert result.value[0].uid == "event:overlap"


@pytest.mark.asyncio
async def test_get_conflicting_no_overlap(search_service, mock_backend, sample_events):
    """Events on same date without time overlap are not conflicts."""
    target = sample_events[0]  # 9:00-9:30
    non_overlapper = EventDTO(
        uid="event:later",
        title="Later meeting",
        user_uid="user_demo",
        event_date=target.event_date,
        start_time=time(10, 0),
        end_time=time(11, 0),
        created_at=datetime.now(),
    )

    mock_backend.get.return_value = Result.ok(target.to_dto().to_dict())
    mock_backend.get_events_on_date.return_value = Result.ok([non_overlapper.to_dict()])

    result = await search_service.get_conflicting("event:1")

    assert result.is_ok
    assert result.value == []


# ============================================================================
# INTELLIGENT SEARCH
# ============================================================================


@pytest.mark.asyncio
async def test_intelligent_search_today_uses_range(search_service, mock_backend):
    """'today' keyword triggers a single-day range query."""
    mock_backend.get_events_in_range.return_value = Result.ok([])

    await search_service.intelligent_search("events today")

    kwargs = mock_backend.get_events_in_range.call_args.kwargs
    today = date.today()
    assert kwargs["start_date"] == today.isoformat()
    assert kwargs["end_date"] == today.isoformat()


@pytest.mark.asyncio
async def test_intelligent_search_recurring_postfilter(search_service, mock_backend, sample_events):
    """'recurring' keyword post-filters to events with a recurrence pattern."""
    mock_backend.get_events_in_range.return_value = Result.ok(
        [
            e.to_dto().to_dict()
            for e in sample_events
            if e.event_date and e.event_date >= date.today()
        ]
    )

    result = await search_service.intelligent_search("upcoming recurring events")

    assert result.is_ok
    events, _parsed = result.value
    assert all(e.recurrence_pattern is not None for e in events)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
