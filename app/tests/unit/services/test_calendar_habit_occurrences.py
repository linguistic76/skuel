"""Unit tests for CalendarService habit-occurrence projection.

Covers the behaviours of the calendar-habits fix (PR #777) and the act-from
arc's completion state (C3):

  1. Clamp — an ongoing habit is never projected before its inception
     (``started_at``, else ``created_at``), so it can't backfill earlier days.
  2. Anchor — weekly/biweekly/monthly/quarterly/yearly recurrences are phased
     off the habit's inception, not the view window (Habit has no ``start_date``,
     which the old code silently used as the anchor via getattr).
  3. Completion state — occurrences on days carrying a recorded completion are
     DONE (fetched per habit by the async caller), the rest PENDING.

``_generate_habit_occurrences`` is pure/sync and touches none of the injected
domain services, so we build the service with mocks and call it directly.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import RecurrencePattern
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.habit_enums import CompletionStatus
from core.models.event.calendar_models import CalendarView
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.services.calendar_service import CalendarService
from core.utils.result_simplified import Errors, Result


def _service() -> CalendarService:
    return CalendarService(
        tasks_service=Mock(), events_service=Mock(), habits_service=Mock(), goals_service=Mock()
    )


def _habit(
    pattern: RecurrencePattern,
    *,
    created: datetime,
    started: datetime | None = None,
    recurrence_end: date | None = None,
) -> Habit:
    return Habit(
        uid="habit.test",
        user_uid="user_test",
        title="Test Habit",
        entity_type=EntityType.HABIT,
        recurrence_pattern=pattern,
        status=EntityStatus.ACTIVE,
        created_at=created,
        updated_at=created,
        started_at=started,
        recurrence_end_date=recurrence_end,
    )


def _dates(service: CalendarService, habit: Habit, start: date, end: date) -> list[date]:
    return [occ.date for occ in service._generate_habit_occurrences(habit, start, end)]


# ---------------------------------------------------------------------------
# Clamp — no projection before inception
# ---------------------------------------------------------------------------


def test_daily_clamped_to_inception_within_view() -> None:
    """A daily habit created mid-window starts on its creation day, not the view start."""
    svc = _service()
    habit = _habit(RecurrencePattern.DAILY, created=datetime(2026, 7, 4, 5, 30))
    assert _dates(svc, habit, date(2026, 7, 1), date(2026, 7, 6)) == [
        date(2026, 7, 4),
        date(2026, 7, 5),
        date(2026, 7, 6),
    ]


def test_daily_fills_view_when_inception_precedes_it() -> None:
    """A daily habit created before the window fills every day of it (the week-view fix)."""
    svc = _service()
    habit = _habit(RecurrencePattern.DAILY, created=datetime(2026, 7, 1))
    got = _dates(svc, habit, date(2026, 7, 20), date(2026, 7, 26))
    assert got == [date(2026, 7, d) for d in range(20, 27)]


def test_habit_created_after_range_yields_nothing() -> None:
    """A habit whose inception is after the whole window produces no occurrences."""
    svc = _service()
    habit = _habit(RecurrencePattern.DAILY, created=datetime(2026, 8, 1))
    assert _dates(svc, habit, date(2026, 7, 1), date(2026, 7, 31)) == []


def test_started_at_takes_precedence_over_created_at() -> None:
    """Inception prefers started_at; a later started_at clamps past created_at."""
    svc = _service()
    habit = _habit(
        RecurrencePattern.DAILY,
        created=datetime(2026, 7, 1),
        started=datetime(2026, 7, 23),
    )
    assert _dates(svc, habit, date(2026, 7, 20), date(2026, 7, 26)) == [
        date(2026, 7, 23),
        date(2026, 7, 24),
        date(2026, 7, 25),
        date(2026, 7, 26),
    ]


def test_recurrence_end_date_clamps_upper_bound() -> None:
    """A finite habit stops projecting after its recurrence_end_date, mid-view."""
    svc = _service()
    habit = _habit(
        RecurrencePattern.DAILY,
        created=datetime(2026, 7, 1),
        recurrence_end=date(2026, 7, 23),
    )
    assert _dates(svc, habit, date(2026, 7, 20), date(2026, 7, 26)) == [
        date(2026, 7, 20),
        date(2026, 7, 21),
        date(2026, 7, 22),
        date(2026, 7, 23),
    ]


def test_recurrence_ended_before_view_yields_nothing() -> None:
    """A habit whose recurrence ended before the window produces no occurrences."""
    svc = _service()
    habit = _habit(
        RecurrencePattern.DAILY,
        created=datetime(2026, 6, 1),
        recurrence_end=date(2026, 7, 10),
    )
    assert _dates(svc, habit, date(2026, 7, 20), date(2026, 7, 26)) == []


# ---------------------------------------------------------------------------
# Anchor — recurrence phase follows the habit, not the view
# ---------------------------------------------------------------------------


def test_weekly_anchors_to_inception_weekday_not_view_start() -> None:
    """A weekly habit begun on a Wednesday lands on Wednesday, not the view's Monday."""
    svc = _service()
    # 2026-07-01 is a Wednesday.
    habit = _habit(RecurrencePattern.WEEKLY, created=datetime(2026, 7, 1))
    # View is Mon 2026-07-20 … Sun 2026-07-26; the only Wednesday is 2026-07-22.
    assert _dates(svc, habit, date(2026, 7, 20), date(2026, 7, 26)) == [date(2026, 7, 22)]


def test_biweekly_parity_is_fixed_to_inception() -> None:
    """Biweekly Wednesdays from Jul 1 are Jul 1/15/29 — Jul 22 is off-cycle."""
    svc = _service()
    habit = _habit(RecurrencePattern.BIWEEKLY, created=datetime(2026, 7, 1))  # Wed
    # Window spans Jul 22 (Wed, off-cycle) and Jul 15 (Wed, on-cycle).
    assert _dates(svc, habit, date(2026, 7, 13), date(2026, 7, 26)) == [date(2026, 7, 15)]


def test_monthly_uses_inception_day_of_month() -> None:
    svc = _service()
    habit = _habit(RecurrencePattern.MONTHLY, created=datetime(2026, 1, 15))
    assert _dates(svc, habit, date(2026, 7, 1), date(2026, 9, 30)) == [
        date(2026, 7, 15),
        date(2026, 8, 15),
        date(2026, 9, 15),
    ]


def test_monthly_day_clamped_to_short_months() -> None:
    """Day 31 collapses to the last day of shorter months."""
    svc = _service()
    habit = _habit(RecurrencePattern.MONTHLY, created=datetime(2026, 1, 31))
    assert _dates(svc, habit, date(2026, 2, 1), date(2026, 4, 30)) == [
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]


def test_quarterly_phase_follows_inception_quarter() -> None:
    """Quarterly from January → Apr/Jul/Oct, not the view's own 3-month phase."""
    svc = _service()
    habit = _habit(RecurrencePattern.QUARTERLY, created=datetime(2026, 1, 10))
    assert _dates(svc, habit, date(2026, 2, 1), date(2026, 12, 31)) == [
        date(2026, 4, 10),
        date(2026, 7, 10),
        date(2026, 10, 10),
    ]


def test_yearly_anchors_to_inception_month_and_day() -> None:
    svc = _service()
    habit = _habit(RecurrencePattern.YEARLY, created=datetime(2025, 3, 20))
    assert _dates(svc, habit, date(2026, 1, 1), date(2026, 12, 31)) == [date(2026, 3, 20)]


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        (RecurrencePattern.WEEKDAYS, [date(2026, 7, 20), date(2026, 7, 21)]),  # Mon, Tue
        (RecurrencePattern.WEEKENDS, [date(2026, 7, 25), date(2026, 7, 26)]),  # Sat, Sun
    ],
)
def test_weekday_weekend_filters(pattern: RecurrencePattern, expected: list[date]) -> None:
    svc = _service()
    habit = _habit(pattern, created=datetime(2026, 7, 1))
    # Restrict the window so the expected set is small and unambiguous.
    lo = date(2026, 7, 20) if pattern is RecurrencePattern.WEEKDAYS else date(2026, 7, 25)
    hi = date(2026, 7, 21) if pattern is RecurrencePattern.WEEKDAYS else date(2026, 7, 26)
    assert _dates(svc, habit, lo, hi) == expected


# ---------------------------------------------------------------------------
# Completion state — occurrences on completed days carry DONE (act-from C3)
# ---------------------------------------------------------------------------


def test_completed_dates_map_to_done_status() -> None:
    """Occurrences on days with a recorded completion are DONE, the rest PENDING."""
    svc = _service()
    habit = _habit(RecurrencePattern.DAILY, created=datetime(2026, 7, 1))
    occurrences = svc._generate_habit_occurrences(
        habit, date(2026, 7, 20), date(2026, 7, 22), completed_dates={date(2026, 7, 21)}
    )
    assert [(occ.date, occ.status) for occ in occurrences] == [
        (date(2026, 7, 20), CompletionStatus.PENDING),
        (date(2026, 7, 21), CompletionStatus.DONE),
        (date(2026, 7, 22), CompletionStatus.PENDING),
    ]


def test_no_completed_dates_leaves_all_pending() -> None:
    svc = _service()
    habit = _habit(RecurrencePattern.DAILY, created=datetime(2026, 7, 1))
    occurrences = svc._generate_habit_occurrences(habit, date(2026, 7, 20), date(2026, 7, 22))
    assert all(occ.status == CompletionStatus.PENDING for occ in occurrences)


@pytest.mark.asyncio
async def test_fetch_completed_dates_maps_completion_days() -> None:
    svc = _service()
    completions = [
        SimpleNamespace(completed_at=datetime(2026, 7, 21, 8, 30)),
        SimpleNamespace(completed_at="2026-07-23T19:00:00"),  # string-writer temporal split
    ]
    svc.habits_service.completions.get_completions_for_habit = AsyncMock(
        return_value=Result.ok(completions)
    )
    got = await svc._fetch_completed_dates("habit.test", date(2026, 7, 20), date(2026, 7, 26))
    assert got == {date(2026, 7, 21), date(2026, 7, 23)}


@pytest.mark.asyncio
async def test_fetch_completed_dates_error_returns_empty_set() -> None:
    """A failed completions read degrades to PENDING chips, not a failed view."""
    svc = _service()
    svc.habits_service.completions.get_completions_for_habit = AsyncMock(
        return_value=Result.fail(Errors.database("habits.completions", "boom"))
    )
    got = await svc._fetch_completed_dates("habit.test", date(2026, 7, 20), date(2026, 7, 26))
    assert got == set()


@pytest.mark.asyncio
async def test_get_calendar_view_marks_completed_days() -> None:
    """End-to-end through get_calendar_view: a recorded completion surfaces as
    a DONE occurrence for that day (both writers, one render truth)."""
    svc = CalendarService(
        tasks_service=AsyncMock(),
        events_service=AsyncMock(),
        habits_service=AsyncMock(),
        goals_service=AsyncMock(),
    )
    svc.tasks_service.get_user_items_in_range = AsyncMock(return_value=Result.ok([]))
    svc.events_service.get_user_items_in_range = AsyncMock(return_value=Result.ok([]))
    svc.goals_service.get_user_items_in_range = AsyncMock(return_value=Result.ok([]))
    habit = _habit(RecurrencePattern.DAILY, created=datetime(2026, 7, 1))
    svc.habits_service.get_active = AsyncMock(return_value=Result.ok([habit]))
    svc.habits_service.completions.get_completions_for_habit = AsyncMock(
        return_value=Result.ok([SimpleNamespace(completed_at=datetime(2026, 7, 21, 8, 0))])
    )

    result = await svc.get_calendar_view(
        "user_test", date(2026, 7, 20), date(2026, 7, 22), CalendarView.WEEK
    )

    assert result.is_ok
    statuses = {occ.date: occ.status for occ in result.value.occurrences[habit.uid]}
    assert statuses[date(2026, 7, 21)] == CompletionStatus.DONE
    assert statuses[date(2026, 7, 20)] == CompletionStatus.PENDING
    assert statuses[date(2026, 7, 22)] == CompletionStatus.PENDING


# ---------------------------------------------------------------------------
# record_habit_occurrence — day-idempotent write; strict actionable reads
# ---------------------------------------------------------------------------


def _owned_habit() -> Habit:
    return _habit(RecurrencePattern.DAILY, created=datetime(2026, 7, 1))


def _completion(completed_at: datetime) -> HabitCompletion:
    return HabitCompletion(
        uid=f"hc.user_test.habit.test.{int(completed_at.timestamp())}",
        habit_uid="habit.test",
        user_uid="user_mike",
        completed_at=completed_at,
        created_at=completed_at,
        updated_at=completed_at,
    )


@pytest.mark.asyncio
async def test_record_habit_occurrence_is_day_idempotent() -> None:
    """A day that already carries a completion returns the existing record and
    writes nothing — a stale modal or double click must not double-count."""
    svc = _service()
    svc.habits_service.get = AsyncMock(return_value=Result.ok(_owned_habit()))
    existing = _completion(datetime(2026, 8, 1, 0, 0))
    svc.habits_service.completions.get_completions_for_habit = AsyncMock(
        return_value=Result.ok([existing])
    )
    svc.habits_service.track_habit = AsyncMock()

    result = await svc.record_habit_occurrence("user_test", "habit.test", "2026-08-01")

    assert result.is_ok
    assert result.value is existing
    svc.habits_service.track_habit.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_habit_occurrence_writes_when_day_clear() -> None:
    svc = _service()
    svc.habits_service.get = AsyncMock(return_value=Result.ok(_owned_habit()))
    svc.habits_service.completions.get_completions_for_habit = AsyncMock(return_value=Result.ok([]))
    written = _completion(datetime(2026, 8, 1, 0, 0))
    svc.habits_service.track_habit = AsyncMock(return_value=Result.ok(written))

    result = await svc.record_habit_occurrence("user_test", "habit.test", "2026-08-01")

    assert result.is_ok and result.value is written
    await_args = svc.habits_service.track_habit.await_args
    assert await_args is not None
    assert await_args.args[0].completion_date == "2026-08-01"


@pytest.mark.asyncio
async def test_record_habit_occurrence_idempotency_read_failure_propagates() -> None:
    """The pre-write read never degrades into a write (double-count risk)."""
    svc = _service()
    svc.habits_service.get = AsyncMock(return_value=Result.ok(_owned_habit()))
    svc.habits_service.completions.get_completions_for_habit = AsyncMock(
        return_value=Result.fail(Errors.database("habits.completions", "boom"))
    )
    svc.habits_service.track_habit = AsyncMock()

    result = await svc.record_habit_occurrence("user_test", "habit.test", "2026-08-01")

    assert result.is_error
    svc.habits_service.track_habit.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_habit_occurrence_rejects_off_schedule_day() -> None:
    """A day the habit never occurs on (off-cadence) is rejected — an
    invisible completion would still inflate the stats."""
    svc = _service()
    # Weekly habit anchored to Wednesday 2026-07-01.
    habit = _habit(RecurrencePattern.WEEKLY, created=datetime(2026, 7, 1))
    svc.habits_service.get = AsyncMock(return_value=Result.ok(habit))
    svc.habits_service.completions.get_completions_for_habit = AsyncMock()
    svc.habits_service.track_habit = AsyncMock()

    # 2026-07-23 is a Thursday — off the Wednesday cadence.
    result = await svc.record_habit_occurrence("user_test", "habit.test", "2026-07-23")

    assert result.is_error
    svc.habits_service.completions.get_completions_for_habit.assert_not_awaited()
    svc.habits_service.track_habit.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_habit_occurrence_rejects_pre_inception_day() -> None:
    svc = _service()
    habit = _habit(RecurrencePattern.DAILY, created=datetime(2026, 7, 10))
    svc.habits_service.get = AsyncMock(return_value=Result.ok(habit))
    svc.habits_service.track_habit = AsyncMock()

    result = await svc.record_habit_occurrence("user_test", "habit.test", "2026-07-05")

    assert result.is_error
    svc.habits_service.track_habit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_item_off_schedule_date_yields_unstamped_item() -> None:
    """An off-schedule ?date= yields the display-only modal — no day stamp,
    hence no Mark Complete."""
    svc = _service()
    habit = _habit(RecurrencePattern.DAILY, created=datetime(2026, 7, 10))
    svc.habits_service.get = AsyncMock(return_value=Result.ok(habit))
    svc.habits_service.completions.get_completions_for_habit = AsyncMock()

    result = await svc.get_item("user_test", "habit-habit.test", on_date=date(2026, 7, 5))

    assert result.is_ok
    assert result.value is not None
    assert result.value.occurrence_data is None
    svc.habits_service.completions.get_completions_for_habit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_item_day_stamp_read_failure_propagates() -> None:
    """The actionable modal must not render an already-done day as PENDING
    when the completion read fails — the error propagates instead."""
    svc = _service()
    svc.habits_service.get = AsyncMock(return_value=Result.ok(_owned_habit()))
    svc.habits_service.completions.get_completions_for_habit = AsyncMock(
        return_value=Result.fail(Errors.database("habits.completions", "boom"))
    )

    result = await svc.get_item("user_test", "habit-habit.test", on_date=date(2026, 8, 1))

    assert result.is_error


# ---------------------------------------------------------------------------
# _fetch_habits honours include_completed (symmetry with tasks/events)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_habits_default_returns_only_alive() -> None:
    """The default path fetches alive habits (active/paused) via get_active."""
    svc = _service()
    alive = [_habit(RecurrencePattern.DAILY, created=datetime(2026, 7, 1))]
    svc.habits_service.get_active = AsyncMock(return_value=Result.ok(alive))
    svc.habits_service.get_user_habits = AsyncMock(return_value=Result.ok([]))

    assert await svc._fetch_habits("user_x") is alive
    svc.habits_service.get_active.assert_awaited_once_with("user_x")
    svc.habits_service.get_user_habits.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_habits_include_completed_returns_all_statuses() -> None:
    """include_completed=True widens to every status via get_user_habits."""
    svc = _service()
    every = [_habit(RecurrencePattern.DAILY, created=datetime(2026, 7, 1))]
    svc.habits_service.get_active = AsyncMock(return_value=Result.ok([]))
    svc.habits_service.get_user_habits = AsyncMock(return_value=Result.ok(every))

    assert await svc._fetch_habits("user_x", include_completed=True) is every
    svc.habits_service.get_user_habits.assert_awaited_once_with("user_x")
    svc.habits_service.get_active.assert_not_awaited()
