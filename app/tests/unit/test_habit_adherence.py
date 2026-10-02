"""Habit adherence — the one definition, and the populator that derives the context's rates from it.

``habit_adherence`` is the ratio ``_calculate_consistency_from_completions`` has
always computed, lifted out so the read-time readers share it: completions in
the trailing window over what the habit's frequency expects there, at most 1.0.
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
from core.models.habit.adherence import adherence_window_bounds, habit_adherence
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


# =============================================================================
# habit_adherence
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
        (RecurrencePattern.WEEKLY, None, 2, 2 / (DAYS // 7)),
        ("weekly", None, DAYS // 7, 1.0),
        (RecurrencePattern.CUSTOM, 3, 6, 6 / ((3 * DAYS) // 7)),
        (RecurrencePattern.CUSTOM, None, 6, 0.0),  # expects nothing
        (RecurrencePattern.CUSTOM, 0, 6, 0.0),
    ],
)
def test_the_ratio_against_the_habits_own_frequency(
    pattern: str | None, target: int | None, count: int, expected: float
) -> None:
    assert habit_adherence(pattern, target, count) == pytest.approx(expected)


def test_a_habit_younger_than_the_window_is_measured_against_all_of_it() -> None:
    """Three days old, kept three of three: 3 / 30 — the window is fixed."""
    assert habit_adherence(RecurrencePattern.DAILY, 7, 3) == pytest.approx(0.1)


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
    )
    service = object.__new__(HabitsProgressService)

    ratio = service._calculate_consistency_from_completions(habit, in_window + outside, today)

    assert ratio == habit_adherence(pattern, target, len(in_window))


# =============================================================================
# The populator derives the rates
# =============================================================================


def _row(uid: str, count: int, pattern: str | None = "daily") -> HabitAdherenceRow:
    return {
        "uid": uid,
        "completions_in_window": count,
        "recurrence_pattern": pattern,
        "target_days_per_week": None,
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
