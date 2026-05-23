#!/usr/bin/env python3
"""
HabitsSearchService Test Suite
===============================

Tests for search and discovery operations in HabitsSearchService.

Habits override ``get_upcoming``/``get_overdue``/``get_active`` from
TimeQueryMixin with frequency-window logic: "due" is computed from
``last_completed`` + ``recurrence_pattern`` rather than from a stored
``due_date`` column.
"""

from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import Domain, EntityStatus, RecurrencePattern
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.services.habits.habits_search_service import HabitsSearchService
from core.utils.result_simplified import Result

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_backend() -> Any:
    backend = Mock()
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.get_active_habits_prioritized = AsyncMock(return_value=Result.ok([]))
    backend.upcoming_raw = AsyncMock(return_value=Result.ok([]))
    backend.overdue_raw = AsyncMock(return_value=Result.ok([]))
    backend.active_raw = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def search_service(mock_backend) -> HabitsSearchService:
    return HabitsSearchService(backend=mock_backend)


def _habit(
    uid: str,
    *,
    status: EntityStatus = EntityStatus.ACTIVE,
    recurrence: str = RecurrencePattern.DAILY.value,
    last_completed: datetime | None = None,
    current_streak: int = 0,
    best_streak: int = 0,
    user_uid: str = "user_demo",
) -> Habit:
    dto = HabitDTO(
        uid=uid,
        title=f"Habit {uid}",
        user_uid=user_uid,
        domain=Domain.HEALTH,
        status=status,
        recurrence_pattern=recurrence,
        last_completed=last_completed,
        current_streak=current_streak,
        best_streak=best_streak,
        created_at=datetime.now() - timedelta(days=30),
    )
    return Habit.from_dto(dto)


# ============================================================================
# INITIALIZATION
# ============================================================================


def test_init_with_backend(mock_backend):
    service = HabitsSearchService(backend=mock_backend)
    assert service.backend == mock_backend


def test_init_without_backend():
    with pytest.raises(ValueError, match=r"[Bb]ackend is REQUIRED"):
        HabitsSearchService(backend=None)


# ============================================================================
# HARMONIZED TIME-QUERY SURFACE — DOMAIN-SPECIFIC OVERRIDES
# ============================================================================
#
# Habits override get_upcoming, get_overdue, and get_active so they can
# reason about frequency windows rather than due-date columns. These
# tests exercise the overrides end-to-end via backend.find_by().


@pytest.mark.asyncio
async def test_get_upcoming_never_completed_is_due(search_service, mock_backend):
    """Habits never completed are always upcoming."""
    habit = _habit("habit:new", last_completed=None)
    mock_backend.find_by.return_value = Result.ok([habit.to_dto().to_dict()])

    result = await search_service.get_upcoming(days_ahead=7, user_uid="user_demo")

    assert result.is_ok
    assert len(result.value) == 1
    assert result.value[0].uid == "habit:new"


@pytest.mark.asyncio
async def test_get_upcoming_excludes_paused(search_service, mock_backend):
    """Paused habits are not upcoming (INACTIVE_STATUSES includes PAUSED)."""
    paused = _habit("habit:paused", status=EntityStatus.PAUSED)
    mock_backend.find_by.return_value = Result.ok([paused.to_dto().to_dict()])

    result = await search_service.get_upcoming(user_uid="user_demo")

    assert result.is_ok
    assert result.value == []


@pytest.mark.asyncio
async def test_get_upcoming_recently_completed_is_not_due(search_service, mock_backend):
    """A daily habit completed today isn't due again yet."""
    today_completed = _habit(
        "habit:today",
        recurrence=RecurrencePattern.DAILY.value,
        last_completed=datetime.combine(date.today(), datetime.min.time()),
    )
    mock_backend.find_by.return_value = Result.ok([today_completed.to_dto().to_dict()])

    result = await search_service.get_upcoming(user_uid="user_demo")

    assert result.is_ok
    assert result.value == []


@pytest.mark.asyncio
async def test_get_overdue_weekly_beyond_window(search_service, mock_backend):
    """A weekly habit last completed 10 days ago is overdue."""
    stale = _habit(
        "habit:stale",
        recurrence=RecurrencePattern.WEEKLY.value,
        last_completed=datetime.now() - timedelta(days=10),
    )
    mock_backend.find_by.return_value = Result.ok([stale.to_dto().to_dict()])

    result = await search_service.get_overdue(user_uid="user_demo")

    assert result.is_ok
    assert len(result.value) == 1
    assert result.value[0].uid == "habit:stale"


@pytest.mark.asyncio
async def test_get_overdue_excludes_archived(search_service, mock_backend):
    """Archived habits are never overdue."""
    archived = _habit(
        "habit:archived",
        status=EntityStatus.ARCHIVED,
        last_completed=datetime.now() - timedelta(days=30),
    )
    mock_backend.find_by.return_value = Result.ok([archived.to_dto().to_dict()])

    result = await search_service.get_overdue(user_uid="user_demo")

    assert result.is_ok
    assert result.value == []


@pytest.mark.asyncio
async def test_get_active_includes_paused(search_service, mock_backend):
    """Habits.get_active keeps paused entries (they are still 'alive')."""
    paused = _habit("habit:paused", status=EntityStatus.PAUSED)
    active = _habit("habit:active", status=EntityStatus.ACTIVE)
    archived = _habit("habit:archived", status=EntityStatus.ARCHIVED)
    mock_backend.find_by.return_value = Result.ok(
        [paused.to_dto().to_dict(), active.to_dto().to_dict(), archived.to_dto().to_dict()]
    )

    result = await search_service.get_active(user_uid="user_demo")

    assert result.is_ok
    uids = {h.uid for h in result.value}
    # Paused + active survive, archived is filtered out
    assert uids == {"habit:paused", "habit:active"}


@pytest.mark.asyncio
async def test_get_active_requires_user_uid(search_service, mock_backend):
    """get_active still requires a user_uid — no admin-wide call."""
    # Mock returns empty so the filter step won't raise; we assert via call
    mock_backend.find_by.return_value = Result.ok([])

    result = await search_service.get_active(user_uid="user_demo")

    assert result.is_ok
    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["user_uid"] == "user_demo"


# ============================================================================
# HABIT-SPECIFIC METHODS
# ============================================================================


@pytest.mark.asyncio
async def test_get_by_frequency(search_service, mock_backend):
    habit = _habit("habit:weekly", recurrence=RecurrencePattern.WEEKLY.value)
    mock_backend.find_by.return_value = Result.ok([habit.to_dto().to_dict()])

    result = await search_service.get_by_frequency(RecurrencePattern.WEEKLY)

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["frequency"] == RecurrencePattern.WEEKLY.value


@pytest.mark.asyncio
async def test_get_needing_attention_low_streak(search_service, mock_backend):
    """Habits with low current streak need attention."""
    low = _habit("habit:low", current_streak=1, best_streak=5)
    mock_backend.find_by.return_value = Result.ok([low.to_dto().to_dict()])

    result = await search_service.get_needing_attention(streak_threshold=3)

    assert result.is_ok
    # best_streak (5) >= threshold (3) but current_streak (1) < threshold → lost streak
    assert len(result.value) == 1


@pytest.mark.asyncio
async def test_get_user_due_today(search_service, mock_backend):
    """Daily habit last completed yesterday is due today."""
    yesterday = datetime.combine(date.today() - timedelta(days=1), datetime.min.time())
    habit = _habit(
        "habit:daily",
        recurrence=RecurrencePattern.DAILY.value,
        last_completed=yesterday,
    )
    mock_backend.find_by.return_value = Result.ok([habit.to_dto().to_dict()])

    result = await search_service.get_user_due_today(user_uid="user_demo")

    assert result.is_ok
    assert len(result.value) == 1


@pytest.mark.asyncio
async def test_get_user_due_today_skips_completed_today(search_service, mock_backend):
    """Already completed today → not due."""
    today = datetime.combine(date.today(), datetime.min.time())
    habit = _habit(
        "habit:done-today",
        recurrence=RecurrencePattern.DAILY.value,
        last_completed=today,
    )
    mock_backend.find_by.return_value = Result.ok([habit.to_dto().to_dict()])

    result = await search_service.get_user_due_today(user_uid="user_demo")

    assert result.is_ok
    assert result.value == []


# ============================================================================
# INTELLIGENT SEARCH
# ============================================================================


@pytest.mark.asyncio
async def test_intelligent_search_extracts_frequency(search_service, mock_backend):
    mock_backend.find_by.return_value = Result.ok([])

    await search_service.intelligent_search("daily habits")

    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["recurrence_pattern"] == RecurrencePattern.DAILY.value


@pytest.mark.asyncio
async def test_intelligent_search_broken_streak_postfilter(search_service, mock_backend):
    """'broken' keyword filters to habits with best>0 but current=0."""
    broken = _habit("habit:broken", current_streak=0, best_streak=10)
    strong = _habit("habit:strong", current_streak=5, best_streak=5)
    mock_backend.find_by.return_value = Result.ok(
        [broken.to_dto().to_dict(), strong.to_dto().to_dict()]
    )

    result = await search_service.intelligent_search("broken daily habits")

    assert result.is_ok
    habits, _parsed = result.value
    uids = {h.uid for h in habits}
    assert uids == {"habit:broken"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
