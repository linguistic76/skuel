"""
Habit adherence — the one definition of "how well is this habit being kept now".

A habit's adherence is the number of its completions inside the trailing
:class:`~core.constants.HabitConsistencyWindow` divided by the number its own
frequency expects there, clamped to 1.0. It is a **ratio** against the habit's
own cadence, not the completions-per-week *rate*
``CrossDomainAnalyticsService.get_habit_consistency`` reports per user over the
same span.

The value is derived at read time, never stored: a rate over "the last thirty
days" changes when a day passes with no completion, so a number written at
completion time stops being true the next day — a habit kept daily and then
dropped would hold 1.0 forever. Every reader therefore counts the window's
completions when it reads and hands the count to :func:`habit_adherence`.
Design and the write-side work it leaves open:
``docs/roadmap/habit-completion-persistence-bundle.md``.

The count belongs to the window :func:`adherence_window_bounds` returns — the
window's first instant and the first instant after its last day, on the stored
clock — counted over ``:HabitCompletion`` nodes the habit's owner owns. Only a
node counts: a completion that leaves no node behind is invisible to the rate.
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo

from core.constants import HabitConsistencyWindow
from core.models.enums import RecurrencePattern
from core.utils.timestamp_helpers import stored_day_bounds, today_in


def habit_adherence(
    recurrence_pattern: str | None,
    target_days_per_week: int | None,
    completions_in_window: int,
) -> float:
    """Completions in the window over what the habit's frequency expects there, at most 1.0.

    ``expected`` is the window's length in days for a daily habit (and for every
    pattern not named below), its whole weeks for a weekly one, and
    ``target_days_per_week`` scaled to the window for a custom one. A custom
    habit with no target expects nothing and reads 0.0. The window is fixed:
    a habit younger than it is measured against the whole window, not its age.

    ``recurrence_pattern`` is the stored value — a :class:`RecurrencePattern`
    or the string a statement projects; the two compare equal.
    """
    expected = HabitConsistencyWindow.DAYS
    if recurrence_pattern == RecurrencePattern.WEEKLY:
        expected = HabitConsistencyWindow.DAYS // 7
    elif recurrence_pattern == RecurrencePattern.CUSTOM:
        expected = ((target_days_per_week or 0) * HabitConsistencyWindow.DAYS) // 7

    if expected == 0:
        return 0.0
    return min(1.0, completions_in_window / expected)


def adherence_window_days(zone: tzinfo) -> tuple[date, date]:
    """The trailing window as of today in ``zone``: its first and last day, inclusive."""
    today = today_in(zone)
    return HabitConsistencyWindow.start_date(today), HabitConsistencyWindow.end_date(today)


def adherence_window_bounds(zone: tzinfo) -> tuple[datetime, datetime]:
    """The trailing window as of today in ``zone``: ``[start, end)`` on the stored clock.

    ``start`` is the first instant of the window's first day and ``end`` the
    first instant after today, so a completion stamped later today counts and
    one stamped tomorrow does not. A reader compares ``completed_at`` with these
    bounds through ``datetime()`` on both sides.
    """
    first_day, last_day = adherence_window_days(zone)
    return stored_day_bounds(first_day, last_day, zone)
