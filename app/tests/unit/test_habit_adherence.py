"""Habit adherence — the one definition, and the populator that derives the context's rates from it.

``habit_adherence`` is the habit's completions in the trailing window over what
its frequency expects there, at most 1.0 — lifted out of
``_calculate_consistency_from_completions`` so the read-time readers share it.
The span is cut short at the habit's creation day (a habit three days old is
measured over three days), every ``RecurrencePattern`` expects what the span
holds of its own cadence, and a habit with nothing due yet — or a cadence the
window cannot hold — has no rate (None), never a zero.

The populator turns each statement row (a window count, never a rate) into
``habit_completion_rates``; a row set that is missing is a statement or a fake
out of shape, and raises rather than reading every habit as 0.0.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from core.constants import HabitConsistencyWindow
from core.models.enums import RecurrencePattern
from core.models.enums.entity_enums import EntityType
from core.models.habit.adherence import (
    adherence_window_bounds,
    creation_day,
    expected_completions,
    habit_adherence,
)
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.services.habits.habits_progress_service import HabitsProgressService
from core.services.user import UserContext
from core.services.user.user_context_populator import UserContextPopulator
from core.utils.timestamp_helpers import as_stored_clock, local_day_bounds, today_in
from core.utils.zone_context import current_zone

if TYPE_CHECKING:
    from core.ports.query_types import HabitAdherenceRow

DAYS = HabitConsistencyWindow.DAYS
# A Friday, so the window (2026-09-03 Thu … 2026-10-02 Fri) holds 22 weekdays and 8 weekend days.
TODAY = date(2026, 10, 2)
WINDOW_START = HabitConsistencyWindow.start_date(TODAY)
OLD = TODAY - timedelta(days=90)  # created long before the window


def _rate(
    pattern: str | None, count: int, *, target: int | None = None, created_on: date | None = OLD
) -> float | None:
    return habit_adherence(pattern, target, count, created_on=created_on, today=TODAY)


# =============================================================================
# habit_adherence — a habit older than the window
# =============================================================================


@pytest.mark.parametrize(
    ("pattern", "target", "count", "expected"),
    [
        (RecurrencePattern.DAILY, None, DAYS, 1.0),
        (RecurrencePattern.DAILY, None, 15, 0.5),
        (RecurrencePattern.DAILY, None, 0, 0.0),
        (RecurrencePattern.DAILY, None, DAYS + 5, 1.0),  # clamped
        # The statement projects the stored string, which compares equal.
        ("daily", None, 3, 3 / DAYS),
        (None, None, 3, 3 / DAYS),  # no pattern reads as daily
        (RecurrencePattern.WEEKDAYS, None, 22, 1.0),
        (RecurrencePattern.WEEKDAYS, None, 11, 0.5),
        (RecurrencePattern.WEEKENDS, None, 8, 1.0),
        (RecurrencePattern.WEEKENDS, None, 2, 0.25),
        (RecurrencePattern.WEEKLY, None, 2, 0.5),  # four whole weeks
        ("weekly", None, 4, 1.0),
        (RecurrencePattern.BIWEEKLY, None, 1, 0.5),  # two whole fortnights
        (RecurrencePattern.BIWEEKLY, None, 2, 1.0),
        (RecurrencePattern.MONTHLY, None, 1, 1.0),  # the window is one month
        (RecurrencePattern.MONTHLY, None, 0, 0.0),
        (RecurrencePattern.CUSTOM, 3, 6, 0.5),  # three a week expects twelve
    ],
)
def test_the_ratio_against_the_habits_own_frequency(
    pattern: str | None, target: int | None, count: int, expected: float
) -> None:
    assert _rate(pattern, count, target=target) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("pattern", "target"),
    [
        (RecurrencePattern.QUARTERLY, None),
        (RecurrencePattern.YEARLY, None),
        (RecurrencePattern.NONE, None),  # one-time
        (RecurrencePattern.CUSTOM, None),  # asks for nothing
        (RecurrencePattern.CUSTOM, 0),
    ],
)
def test_a_cadence_the_window_cannot_measure_has_no_rate(
    pattern: RecurrencePattern, target: int | None
) -> None:
    assert _rate(pattern, 1, target=target) is None
    assert _rate(pattern, 0, target=target) is None


def test_the_weekday_and_weekend_days_are_counted_on_the_calendar() -> None:
    assert expected_completions(RecurrencePattern.WEEKDAYS, None, WINDOW_START, TODAY) == 22
    assert expected_completions(RecurrencePattern.WEEKENDS, None, WINDOW_START, TODAY) == 8
    # Saturday 2026-09-26 … Sunday 2026-09-27: two weekend days, no weekday.
    weekend = (date(2026, 9, 26), date(2026, 9, 27))
    assert expected_completions(RecurrencePattern.WEEKDAYS, None, *weekend) == 0
    assert expected_completions(RecurrencePattern.WEEKENDS, None, *weekend) == 2


# =============================================================================
# habit_adherence — a habit younger than the window
# =============================================================================


def test_a_young_habit_kept_every_day_reads_full() -> None:
    """Three days old, kept three of three: 1.0, not 3 / 30."""
    assert _rate(RecurrencePattern.DAILY, 3, created_on=TODAY - timedelta(days=2)) == 1.0


def test_a_young_habit_is_measured_over_the_days_it_has_existed() -> None:
    created = TODAY - timedelta(days=9)  # ten days
    assert _rate(RecurrencePattern.DAILY, 5, created_on=created) == pytest.approx(0.5)


def test_a_habit_created_today_expects_today() -> None:
    assert _rate(RecurrencePattern.DAILY, 0, created_on=TODAY) == 0.0
    assert _rate(RecurrencePattern.DAILY, 1, created_on=TODAY) == 1.0


def test_a_habit_younger_than_its_period_has_no_rate_yet() -> None:
    """A weekly habit five days old has no week behind it; at seven days it has one."""
    assert _rate(RecurrencePattern.WEEKLY, 1, created_on=TODAY - timedelta(days=4)) is None
    assert _rate(RecurrencePattern.WEEKLY, 1, created_on=TODAY - timedelta(days=6)) == 1.0
    assert _rate(RecurrencePattern.MONTHLY, 1, created_on=TODAY - timedelta(days=20)) is None


def test_a_habit_created_in_the_window_on_its_first_day_is_measured_over_all_of_it() -> None:
    assert _rate(RecurrencePattern.DAILY, 15, created_on=WINDOW_START) == pytest.approx(0.5)


def test_an_unknown_creation_day_measures_the_whole_window() -> None:
    assert _rate(RecurrencePattern.DAILY, 15, created_on=None) == pytest.approx(0.5)


def test_a_creation_day_after_today_has_no_rate() -> None:
    assert _rate(RecurrencePattern.DAILY, 1, created_on=TODAY + timedelta(days=1)) is None


@pytest.mark.parametrize(
    ("stamp", "day"),
    [
        ("2026-09-20T12:00:00", date(2026, 9, 20)),  # the ISO string a node holds
        (datetime(2026, 9, 20, 12, 0), date(2026, 9, 20)),
        (None, None),
        ("not a stamp", None),
    ],
)
def test_the_creation_day_reads_every_stored_shape(stamp: object, day: date | None) -> None:
    assert creation_day(stamp, current_zone()) == day


def test_the_window_bounds_are_today_and_the_twenty_nine_days_before_it() -> None:
    zone = current_zone()
    today = today_in(zone)

    start, end = adherence_window_bounds(zone)

    assert start == as_stored_clock(local_day_bounds(today - timedelta(days=DAYS - 1), zone)[0])
    assert end == as_stored_clock(local_day_bounds(today, zone)[1])


def _completion(day: date) -> HabitCompletion:
    at = datetime.combine(day, time(hour=12))
    return HabitCompletion(
        uid=f"hc.{day.isoformat()}",
        habit_uid="habit.x",
        user_uid="user_x",
        completed_at=at,
        created_at=at,
        updated_at=at,
    )


@pytest.mark.parametrize(
    ("pattern", "target"),
    [
        (RecurrencePattern.DAILY, None),
        (RecurrencePattern.WEEKLY, None),
        (RecurrencePattern.CUSTOM, 4),
    ],
)
def test_the_progress_service_computes_the_same_ratio(
    pattern: RecurrencePattern, target: int | None
) -> None:
    """``_calculate_consistency_from_completions`` windows the list it is
    handed and hands the count to the one definition."""
    today = today_in(current_zone())
    in_window = [_completion(today - timedelta(days=n)) for n in range(0, 20, 2)]
    outside = [_completion(today - timedelta(days=DAYS)), _completion(today + timedelta(days=1))]
    habit = Habit(
        uid="habit.x",
        user_uid="user_x",
        entity_type=EntityType.HABIT,
        title="x",
        recurrence_pattern=pattern,
        target_days_per_week=target,
        created_at=datetime.now() - timedelta(days=90),
    )
    service = object.__new__(HabitsProgressService)

    ratio = service._calculate_consistency_from_completions(habit, in_window + outside, today)

    assert ratio == habit_adherence(
        pattern,
        target,
        len(in_window),
        created_on=creation_day(habit.created_at, current_zone()),
        today=today,
    )


# =============================================================================
# The populator derives the rates
# =============================================================================


def _row(
    uid: str, count: int, pattern: str | None = "daily", created_at: object = "2026-01-01T09:00:00"
) -> HabitAdherenceRow:
    return {
        "uid": uid,
        "completions_in_window": count,
        "recurrence_pattern": pattern,
        "target_days_per_week": None,
        "created_at": created_at,
    }


def _rich_habit(uid: str) -> dict[str, Any]:
    return {"entity": {"uid": uid}, "graph_context": {"linked_goals": []}}


def test_the_rich_path_derives_each_active_habits_rate() -> None:
    context = UserContext(user_uid="u")
    uids = {
        "active_habit_uids": ["h.kept", "h.weekly"],
        "habit_metadata": [{"uid": "h.kept", "streak": 12}, {"uid": "h.weekly", "streak": 0}],
        "habit_adherence": [_row("h.kept", 24), _row("h.weekly", 2, "weekly")],
    }

    UserContextPopulator().populate_standard_fields(context, uids)

    assert context.habit_completion_rates == {"h.kept": 0.8, "h.weekly": 0.5}


def test_a_young_habit_reads_its_own_days_and_one_with_no_rate_yet_is_left_out() -> None:
    """Created two days ago and kept both days: 1.0. A weekly habit four days old
    has nothing due yet — it has no rate, so it is neither averaged nor at risk."""
    today = today_in(current_zone())
    two_days_ago = (today - timedelta(days=1)).isoformat() + "T08:00:00"
    four_days_ago = (today - timedelta(days=3)).isoformat() + "T08:00:00"
    context = UserContext(user_uid="u")
    uids = {
        "habit_metadata": [{"uid": "h.new", "streak": 2}, {"uid": "h.weekly", "streak": 0}],
        "habit_adherence": [
            _row("h.new", 2, created_at=two_days_ago),
            _row("h.weekly", 0, "weekly", created_at=four_days_ago),
        ],
    }

    UserContextPopulator().populate_standard_fields(context, uids)
    UserContextPopulator().populate_derived_fields(
        context, tasks_rich=[], habits_rich=[_rich_habit("h.new"), _rich_habit("h.weekly")]
    )

    assert context.habit_completion_rates == {"h.new": 1.0}
    assert context.at_risk_habits == []


def test_the_rich_path_refuses_a_uids_section_without_the_adherence_rows() -> None:
    """A rate that is missing is not a rate of zero — the shape is wrong."""
    context = UserContext(user_uid="u")

    with pytest.raises(KeyError, match="habit_adherence"):
        UserContextPopulator().populate_standard_fields(
            context, {"habit_metadata": [{"uid": "h", "streak": 3, "rate": 0.9}]}
        )


def test_the_unknown_user_sentinel_has_no_rates() -> None:
    context = UserContext(user_uid="u")

    UserContextPopulator().populate_standard_fields(context, {})

    assert context.habit_completion_rates == {}


def test_the_standard_path_derives_each_active_habits_rate() -> None:
    context = UserContext(user_uid="u")
    data = {
        "habits": {"active_uids": ["h"], "habit_streaks": {"h": 4}, "adherence": [_row("h", 6)]}
    }

    UserContextPopulator().populate_from_consolidated_data(context, data)

    assert context.habit_completion_rates == {"h": pytest.approx(0.2)}


def test_the_standard_path_refuses_a_habits_section_without_the_adherence_rows() -> None:
    context = UserContext(user_uid="u")

    with pytest.raises(KeyError, match="adherence"):
        UserContextPopulator().populate_from_consolidated_data(
            context, {"habits": {"completion_rates": {"h": 0.9}}}
        )


def test_at_risk_is_an_active_habit_with_no_streak_or_under_half() -> None:
    """A habit in the window that is not active has no rate and is not at risk."""
    context = UserContext(user_uid="u")
    context.habit_streaks = {"h.kept": 10, "h.broken": 0, "h.lapsing": 4}
    context.habit_completion_rates = {"h.kept": 0.8, "h.broken": 0.9, "h.lapsing": 0.3}

    UserContextPopulator().populate_derived_fields(
        context,
        tasks_rich=[],
        habits_rich=[_rich_habit(uid) for uid in ("h.kept", "h.broken", "h.lapsing", "h.paused")],
    )

    assert context.at_risk_habits == ["h.broken", "h.lapsing"]
