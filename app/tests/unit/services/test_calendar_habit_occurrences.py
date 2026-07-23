"""Unit tests for CalendarService habit-occurrence projection.

Covers the two behaviours added in the calendar-habits fix (PR #777):

  1. Clamp — an ongoing habit is never projected before its inception
     (``started_at``, else ``created_at``), so it can't backfill earlier days.
  2. Anchor — weekly/biweekly/monthly/quarterly/yearly recurrences are phased
     off the habit's inception, not the view window (Habit has no ``start_date``,
     which the old code silently used as the anchor via getattr).

``_generate_habit_occurrences`` is pure/sync and touches none of the injected
domain services, so we build the service with mocks and call it directly.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import Mock

import pytest

from core.models.enums import RecurrencePattern
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.habit.habit import Habit
from core.services.calendar_service import CalendarService


def _service() -> CalendarService:
    return CalendarService(tasks_service=Mock(), events_service=Mock(), habits_service=Mock())


def _habit(
    pattern: RecurrencePattern,
    *,
    created: datetime,
    started: datetime | None = None,
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
