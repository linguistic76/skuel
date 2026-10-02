"""
Habit adherence — the one definition of "how well is this habit being kept now".

A habit's adherence is the number of its completions inside the trailing
:class:`~core.constants.HabitConsistencyWindow` — cut short at the day the habit
was created — divided by the number its own frequency expects there, clamped to
1.0; a habit with nothing due yet, or a frequency the window cannot hold, has no
rate. It is a **ratio** against the habit's own cadence, not the
completions-per-week *rate* ``CrossDomainAnalyticsService.get_habit_consistency``
reports per user over the same span.

The value is derived at read time, never stored: a rate over "the last thirty
days" changes when a day passes with no completion, so a number written at
completion time stops being true the next day — a habit kept daily and then
dropped would hold 1.0 forever. Every reader therefore counts the window's
completions when it reads and hands the count to :func:`habit_adherence`.
Design and the write-side work it leaves open:
``docs/roadmap/habit-completion-persistence-bundle.md``.

The completions are read inside the window :func:`adherence_window_bounds`
returns — the window's first instant and the first instant after its last day,
on the stored clock — over ``:HabitCompletion`` nodes the habit's owner owns,
and counted here over the span the ratio measures. Only a node counts: a
completion that leaves no node behind is invisible to the rate.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, tzinfo

from core.constants import HabitConsistencyWindow
from core.models.enums import RecurrencePattern
from core.utils.timestamp_helpers import instant_of, stored_day_bounds, today_in

_SATURDAY = 5  # date.weekday(): Monday is 0


def habit_adherence(
    recurrence_pattern: str | None,
    target_days_per_week: int | None,
    completed_on: Iterable[date],
    *,
    created_on: date | None,
    today: date,
) -> float | None:
    """Completions in the measured span over what the habit's frequency expects there, at most 1.0.

    The span is the trailing window, cut short at the day the habit was created
    (``created_on``; ``None`` reads as older than the window): a habit three
    days old is measured over three days, not thirty. Both sides of the ratio
    are counted over that one span — ``completed_on`` holds one day per
    completion (a completion backfilled to before the habit existed, or stamped
    after today, is outside it), and what the span expects is
    :func:`expected_completions`. ``None`` when the habit has no rate yet —
    nothing is due in its span (a weekly habit younger than a week), or its
    pattern cannot be measured in the window at all — an absent measurement,
    never a zero.

    ``recurrence_pattern`` is the stored value — a :class:`RecurrencePattern`
    or the string a statement projects; the two compare equal.
    """
    first_day = HabitConsistencyWindow.start_date(today)
    if created_on is not None and created_on > first_day:
        first_day = created_on
    if first_day > today:
        return None
    expected = expected_completions(recurrence_pattern, target_days_per_week, first_day, today)
    if not expected:
        return None
    kept = sum(1 for day in completed_on if first_day <= day <= today)
    return min(1.0, kept / expected)


def expected_completions(
    recurrence_pattern: str | None,
    target_days_per_week: int | None,
    first_day: date,
    last_day: date,
) -> int | None:
    """How many completions the habit's frequency asks for from ``first_day`` to ``last_day``.

    A daily habit (and one with no pattern) expects every day; weekdays and
    weekends expect the days of their kind the span holds; weekly, biweekly and
    monthly expect the whole periods it holds; custom expects its weekly target
    scaled to the span. Quarterly, yearly and one-time habits have periods the
    window cannot hold: ``None``. Partial periods round down, so a span shorter
    than one period expects nothing (0).
    """
    days = (last_day - first_day).days + 1
    if recurrence_pattern in (None, RecurrencePattern.DAILY):
        return days
    if recurrence_pattern in (RecurrencePattern.WEEKDAYS, RecurrencePattern.WEEKENDS):
        weekend = recurrence_pattern == RecurrencePattern.WEEKENDS
        return sum(
            1
            for n in range(days)
            if ((first_day + timedelta(days=n)).weekday() >= _SATURDAY) == weekend
        )
    if recurrence_pattern == RecurrencePattern.WEEKLY:
        return days // 7
    if recurrence_pattern == RecurrencePattern.BIWEEKLY:
        return days // 14
    if recurrence_pattern == RecurrencePattern.MONTHLY:
        return days // HabitConsistencyWindow.DAYS
    if recurrence_pattern == RecurrencePattern.CUSTOM:
        return ((target_days_per_week or 0) * days) // 7
    return None


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


def creation_day(stamp: object, zone: tzinfo) -> date | None:
    """The day a habit was created in ``zone``, from its stored ``created_at`` in any shape.

    ``None`` when the stamp is absent or unreadable — :func:`habit_adherence`
    then measures the habit over the whole window.
    """
    instant = instant_of(stamp, zone)
    return instant.astimezone(zone).date() if instant is not None else None


def completion_days(stamps: Iterable[object], zone: tzinfo) -> list[date]:
    """The day each completion fell on in ``zone``, from ``completed_at`` stamps in any stored shape.

    One day per stamp, repeats kept (each completion node counts); an
    unreadable stamp is dropped.
    """
    days: list[date] = []
    for stamp in stamps:
        instant = instant_of(stamp, zone)
        if instant is not None:
            days.append(instant.astimezone(zone).date())
    return days
