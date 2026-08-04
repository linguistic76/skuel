"""Unit tests for the habit's calendar BLOCK — its time of day and its length.

Habit-rhythm arc S2. A habit is a fuzzy block: a ``TimeOfDay`` slot says where
in the day it belongs, ``duration_minutes`` says how long it runs (M3). Before
this, ``_habit_to_calendar_item`` fabricated both — ``start_time`` was the
moment of the query and every habit was 30 minutes long — so a habit chip
carried no fact the habit itself held.

Two derivations are covered here:

  1. ``_habit_to_calendar_item`` — slot → representative time, duration → length,
     with ANYTIME/unset/non-positive falling back stably.
  2. ``_stamp_habit_occurrence`` — the ``?date=`` modal's stamp RE-DATES that
     block onto the clicked day through the same ``habit_block_on`` the grid's
     occurrence expansion uses, so a chip and its modal cannot disagree.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import Mock

import pytest

from core.constants import HabitBlock
from core.models.enums import RecurrencePattern, TimeOfDay
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.habit_enums import CompletionStatus
from core.models.event.calendar_models import CalendarItem, CalendarItemType
from core.models.habit.habit import Habit
from core.services.calendar_service import CalendarService
from core.utils.result_simplified import Errors, Result


def _service(completions: Result[list] | None = None) -> CalendarService:
    habits = Mock()
    if completions is not None:
        habits.completions.get_completions_for_habit = _returns(completions)
    return CalendarService(
        tasks_service=Mock(), events_service=Mock(), habits_service=habits, goals_service=Mock()
    )


def _returns(value: Result[list]):
    """An async stub returning ``value`` (named — SKUEL012)."""

    async def _stub(*_args: object, **_kwargs: object) -> Result[list]:
        return value

    return _stub


def _habit(
    *,
    slot: TimeOfDay | None,
    duration: int | None,
    uid: str = "habit.test",
) -> Habit:
    created = datetime(2026, 7, 1, 5, 30)
    return Habit(
        uid=uid,
        user_uid="user_test",
        title="Test Habit",
        entity_type=EntityType.HABIT,
        recurrence_pattern=RecurrencePattern.DAILY,
        status=EntityStatus.ACTIVE,
        created_at=created,
        updated_at=created,
        preferred_time=slot,
        duration_minutes=duration,
    )


# ---------------------------------------------------------------------------
# _habit_to_calendar_item — the block comes from the habit's own data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("slot", "expected_hour"),
    [
        (TimeOfDay.EARLY_MORNING, 6),
        (TimeOfDay.MORNING, 9),
        (TimeOfDay.AFTERNOON, 14),
        (TimeOfDay.EVENING, 19),
        (TimeOfDay.NIGHT, 22),
        (TimeOfDay.LATE_NIGHT, 2),
    ],
)
def test_slot_places_the_block_at_its_representative_hour(
    slot: TimeOfDay, expected_hour: int
) -> None:
    """Every declared slot lands on its own hour — not on ``now()``."""
    item = _service()._habit_to_calendar_item(_habit(slot=slot, duration=20))
    assert item.start_time.time() == time(expected_hour, 0)
    assert item.item_type == CalendarItemType.HABIT


def test_duration_minutes_is_the_blocks_real_length() -> None:
    """A 20-minute habit is a 20-minute block — not the old hardcoded 30."""
    item = _service()._habit_to_calendar_item(_habit(slot=TimeOfDay.MORNING, duration=20))
    assert item.end_time - item.start_time == timedelta(minutes=20)


def test_the_block_is_not_an_all_day_marker() -> None:
    item = _service()._habit_to_calendar_item(_habit(slot=TimeOfDay.MORNING, duration=20))
    assert item.all_day is False


@pytest.mark.parametrize("slot", [None, TimeOfDay.ANYTIME])
def test_unstated_and_anytime_slots_share_one_stable_fallback_hour(slot: TimeOfDay | None) -> None:
    """ANYTIME is the fallback, so an unstated habit still lands somewhere honest.

    Two of the five live habits declare no slot, so this is the common path,
    not an edge case.
    """
    item = _service()._habit_to_calendar_item(_habit(slot=slot, duration=20))
    assert item.start_time.time() == TimeOfDay.ANYTIME.get_representative_time()


@pytest.mark.parametrize("duration", [None, 0, -5])
def test_unstated_or_non_positive_duration_falls_back_to_the_default_block(
    duration: int | None,
) -> None:
    """A zero-length block is not a block — the live graph holds a habit with
    ``duration_minutes = 0``, which the create request (``ge=1``) forbids."""
    item = _service()._habit_to_calendar_item(_habit(slot=TimeOfDay.MORNING, duration=duration))
    assert item.end_time - item.start_time == timedelta(minutes=HabitBlock.DEFAULT_DURATION_MINUTES)


@pytest.mark.parametrize("slot", [TimeOfDay.MORNING, TimeOfDay.ANYTIME, None])
def test_the_slot_itself_rides_along_unresolved(slot: TimeOfDay | None) -> None:
    """The chip names the slot, and 09:00 cannot be read back as MORNING vs ANYTIME.

    Passed through UNRESOLVED: the ANYTIME fallback exists to PLACE an unstated
    habit, not to give it a preference. Collapsing null to ANYTIME here would
    have the calendar assert a choice the user never made, and contradict every
    other habit surface — the detail page and Today's ritual spine both read
    null as unstated.
    """
    item = _service()._habit_to_calendar_item(_habit(slot=slot, duration=20))
    assert item.time_of_day is slot


def test_the_block_is_stable_across_calls() -> None:
    """The old stub moved with the clock; the block must not.

    Two conversions of the same habit produce the same block — the property
    that lets a chip, its modal, and a second page load agree.
    """
    svc = _service()
    habit = _habit(slot=TimeOfDay.EVENING, duration=15)
    first = svc._habit_to_calendar_item(habit)
    second = svc._habit_to_calendar_item(habit)
    assert (first.start_time, first.end_time) == (second.start_time, second.end_time)


# ---------------------------------------------------------------------------
# _stamp_habit_occurrence — the ?date= modal's stamp carries the block
# ---------------------------------------------------------------------------


def _stub_item(start: datetime, end: datetime) -> CalendarItem:
    return CalendarItem(
        uid="habit-habit_1",
        source_uid="habit_1",
        item_type=CalendarItemType.HABIT,
        title="Meditate",
        start_time=start,
        end_time=end,
    )


@pytest.mark.asyncio
async def test_day_stamp_re_dates_the_block_instead_of_flattening_it_to_midnight() -> None:
    """The stamp keeps the habit's time of day and length on the clicked day."""
    svc = _service(completions=Result.ok([]))
    item = _stub_item(datetime(2026, 8, 3, 9, 0), datetime(2026, 8, 3, 9, 20))

    stamped = await svc._stamp_habit_occurrence(item, "habit_1", date(2026, 8, 6))

    assert stamped.is_error is False
    assert stamped.value.start_time == datetime(2026, 8, 6, 9, 0)
    assert stamped.value.end_time == datetime(2026, 8, 6, 9, 20)
    assert stamped.value.all_day is False
    assert stamped.value.occurrence_data == {
        "date": "2026-08-06",
        "status": CompletionStatus.PENDING.value,
    }


@pytest.mark.asyncio
async def test_day_stamp_still_reports_a_recorded_completion() -> None:
    """The C3 tick's state survives the block change (the stamp's other half)."""
    completion = Mock(completed_at=datetime(2026, 8, 6, 9, 5))
    svc = _service(completions=Result.ok([completion]))
    item = _stub_item(datetime(2026, 8, 3, 9, 0), datetime(2026, 8, 3, 9, 20))

    stamped = await svc._stamp_habit_occurrence(item, "habit_1", date(2026, 8, 6))

    assert stamped.value.occurrence_data == {
        "date": "2026-08-06",
        "status": CompletionStatus.DONE.value,
    }


@pytest.mark.asyncio
async def test_day_stamp_propagates_a_failed_completions_read() -> None:
    """A failed read must not render an already-done day as PENDING."""
    svc = _service(completions=Result.fail(Errors.database("calendar.read_completions", "boom")))
    item = _stub_item(datetime(2026, 8, 3, 9, 0), datetime(2026, 8, 3, 9, 20))

    stamped = await svc._stamp_habit_occurrence(item, "habit_1", date(2026, 8, 6))

    assert stamped.is_error is True
