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

The same module holds the one definition of an **at-risk** habit
(:func:`habit_at_risk`): an active habit that is overdue for its own cadence
(:func:`habit_overdue`, read from its last completion at the moment it is asked)
or whose rate is under the threshold once the measured span holds enough
evidence. Every at-risk reader calls it; none restates it.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, tzinfo

from core.constants import HabitAtRisk, HabitConsistencyWindow
from core.models.enums import EntityStatus, RecurrencePattern
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
    :func:`expected_completions`. A weekdays or weekends habit counts only the
    completions made on the days it expects: a weekday completion of a weekends
    habit keeps no part of its schedule. ``None`` when the habit has no rate yet —
    nothing is due in its span (a weekly habit younger than a week), or its
    pattern cannot be measured in the window at all — an absent measurement,
    never a zero.

    ``recurrence_pattern`` is the stored value — a :class:`RecurrencePattern`
    or the string a statement projects; the two compare equal.
    """
    first_day = _measured_span_start(created_on, today)
    if first_day is None:
        return None
    expected = expected_completions(recurrence_pattern, target_days_per_week, first_day, today)
    if not expected:
        return None
    kept = sum(
        1
        for day in completed_on
        if first_day <= day <= today and _on_cadence(recurrence_pattern, day)
    )
    return min(1.0, kept / expected)


def _on_cadence(recurrence_pattern: str | None, day: date) -> bool:
    """Whether a completion on ``day`` falls on a day the habit's cadence expects."""
    if recurrence_pattern == RecurrencePattern.WEEKDAYS:
        return day.weekday() < _SATURDAY
    if recurrence_pattern == RecurrencePattern.WEEKENDS:
        return day.weekday() >= _SATURDAY
    return True


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


def measured_span_expected(
    recurrence_pattern: str | None,
    target_days_per_week: int | None,
    *,
    created_on: date | None,
    today: date,
) -> int:
    """How many completions the span :func:`habit_adherence` measures asks for — the rate's evidence.

    The same span the ratio is counted over: the trailing window, cut short at
    the creation day. 0 when nothing is due yet or the pattern cannot be measured.
    """
    first_day = _measured_span_start(created_on, today)
    if first_day is None:
        return 0
    return expected_completions(recurrence_pattern, target_days_per_week, first_day, today) or 0


def _measured_span_start(created_on: date | None, today: date) -> date | None:
    """The first day of the span a rate is measured over — None when it has not begun."""
    first_day = HabitConsistencyWindow.start_date(today)
    if created_on is not None and created_on > first_day:
        first_day = created_on
    return first_day if first_day <= today else None


#: The longest a habit of each periodic cadence may go between completions —
#: the longest calendar length of its period, so a short month or quarter never
#: reads a habit kept on time as late.
_PERIOD_DAYS: dict[str, int] = {
    RecurrencePattern.WEEKLY: 7,
    RecurrencePattern.BIWEEKLY: 14,
    RecurrencePattern.MONTHLY: 31,
    RecurrencePattern.QUARTERLY: 92,
    RecurrencePattern.YEARLY: 366,
}


def habit_overdue(
    recurrence_pattern: str | None,
    target_days_per_week: int | None,
    *,
    last_completed_on: date | None,
    created_on: date | None,
    today: date,
) -> bool:
    """Whether an occurrence the habit's cadence asked for has passed with no completion.

    Measured from the last completion — or, for a habit never completed, from
    the day before it was created, so its first period counts. A daily, weekdays
    or weekends habit is overdue once a day it expects has passed undone (today
    is still open); a periodic habit once more than its period has passed since
    the anchor; a custom habit once more than ``7 / target`` days have. A
    one-time habit, a custom habit with no target, and a habit with neither a
    completion nor a readable creation day are never overdue — there is no
    cadence, or no anchor, to be late against.

    Read at the moment it is asked, so a habit dropped weeks ago is overdue now,
    whatever its stored streak says.
    """
    if last_completed_on is not None:
        anchor = last_completed_on
    elif created_on is not None:
        anchor = created_on - timedelta(days=1)
    else:
        return False
    days = (today - anchor).days
    if days <= 1:
        return False
    if recurrence_pattern in (
        None,
        RecurrencePattern.DAILY,
        RecurrencePattern.WEEKDAYS,
        RecurrencePattern.WEEKENDS,
    ):
        # Any seven consecutive days hold a day of every kind.
        return any(
            _on_cadence(recurrence_pattern, anchor + timedelta(days=n))
            for n in range(1, min(days, 8))
        )
    if recurrence_pattern == RecurrencePattern.CUSTOM:
        if not target_days_per_week:
            return False
        return days > -(-7 // target_days_per_week)
    period = _PERIOD_DAYS.get(recurrence_pattern)
    return period is not None and days > period


def habit_at_risk(
    status: str | None,
    recurrence_pattern: str | None,
    target_days_per_week: int | None,
    *,
    rate: float | None,
    last_completed_on: date | None,
    created_on: date | None,
    today: date,
) -> bool:
    """The one definition of an at-risk habit: active, and overdue or measured below the threshold.

    An active habit is at risk when it is :func:`habit_overdue`, or when its
    adherence ``rate`` is under :attr:`HabitAtRisk.RATE_THRESHOLD` and the span
    it was measured over asked for at least :attr:`HabitAtRisk.MIN_EXPECTED`
    completions. A habit with no rate yet is judged on lateness alone — no
    measurement is not a low one. A paused, archived or otherwise inactive habit
    is never at risk.

    ``status`` is the stored value — an :class:`EntityStatus` or its string.
    """
    if status != EntityStatus.ACTIVE:
        return False
    if habit_overdue(
        recurrence_pattern,
        target_days_per_week,
        last_completed_on=last_completed_on,
        created_on=created_on,
        today=today,
    ):
        return True
    if rate is None or rate >= HabitAtRisk.RATE_THRESHOLD:
        return False
    evidence = measured_span_expected(
        recurrence_pattern, target_days_per_week, created_on=created_on, today=today
    )
    return evidence >= HabitAtRisk.MIN_EXPECTED


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
    return stamp_day(stamp, zone)


def stamp_day(stamp: object, zone: tzinfo) -> date | None:
    """The day a stored stamp (``created_at``, ``last_completed``) fell on in ``zone``, any shape.

    ``None`` when the stamp is absent or unreadable.
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
