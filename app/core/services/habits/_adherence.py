"""Hydrate the derived ``Habit.success_rate`` and judge a habit at risk — the habit readers' one path.

``Habit.success_rate`` is the habit's adherence now
(``core.models.habit.adherence.habit_adherence``), derived at read time and never
a node property: a reader that needs it hands the habits it read to
:func:`enrich_habits_with_adherence`, which reads every habit's completions in
the trailing window in one backend call
(``HabitsOperations.get_habit_window_completions``, owner-scoped) and returns
new Habit instances carrying the rate. A habit with no rate yet keeps ``None``.

The same read yields each habit's :class:`AdherenceReading` — its rate and the
last day it was kept on its own cadence — which is everything
:func:`habit_is_at_risk` needs to apply the one at-risk definition
(``core.models.habit.adherence.habit_at_risk``).

Design: ``docs/roadmap/habit-completion-persistence-bundle.md``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, tzinfo
from typing import TYPE_CHECKING, NamedTuple

from core.models.habit.adherence import (
    adherence_window_days,
    completion_days,
    habit_adherence,
    habit_at_risk,
    inception_day,
    last_kept_day,
    stamp_day,
)
from core.utils.result_simplified import Errors, Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

if TYPE_CHECKING:
    from core.models.habit.habit import Habit
    from core.ports.domain_protocols import HabitsOperations


class AdherenceReading(NamedTuple):
    """One habit's reading now: its adherence (``None`` = no rate yet) and the last day it was kept."""

    rate: float | None
    last_kept_on: date | None


async def adherence_readings(
    backend: HabitsOperations, habits: list[Habit]
) -> Result[dict[str, AdherenceReading]]:
    """Every habit's :class:`AdherenceReading`, keyed by uid, from one read of the window.

    The window's completion days are counted by
    :func:`~core.models.habit.adherence.habit_adherence` against the habit's
    cadence, creation day and schedule end, and give the last day it was kept
    (:func:`~core.models.habit.adherence.last_kept_day`, with the stored
    ``last_completed`` reaching past the window).
    """
    if not habits:
        return Result.ok({})
    zone = current_zone()
    today = today_in(zone)
    first_day, last_day = adherence_window_days(zone)
    stamps_result = await backend.get_habit_window_completions(
        [habit.uid for habit in habits], first_day.isoformat(), last_day.isoformat()
    )
    if stamps_result.is_error:
        return Result.fail(stamps_result)
    stamps = stamps_result.value
    # Every owned habit is answered, empty included: an absent one has no owner
    # to read completions under, and reading it as "no completions" would
    # measure it at 0.0.
    unanswered = [habit.uid for habit in habits if habit.uid not in stamps]
    if unanswered:
        return Result.fail(
            Errors.system(
                message=f"No window completions read for habits {unanswered}",
                operation="adherence_readings",
            )
        )
    readings: dict[str, AdherenceReading] = {}
    for habit in habits:
        days = completion_days(stamps[habit.uid], zone)
        readings[habit.uid] = AdherenceReading(
            rate=habit_adherence(
                habit.recurrence_pattern,
                habit.target_days_per_week,
                days,
                started_on=inception_day(habit.started_at, habit.created_at, zone),
                ends_on=habit.recurrence_end_date,
                today=today,
            ),
            last_kept_on=last_kept_day(
                habit.recurrence_pattern,
                days,
                last_completed_on=stamp_day(habit.last_completed, zone),
                today=today,
            ),
        )
    return Result.ok(readings)


async def adherence_rates(
    backend: HabitsOperations, habits: list[Habit]
) -> Result[dict[str, float]]:
    """Each habit's adherence now, keyed by uid — the habits that have a rate.

    A habit with no rate yet is left out — no measurement, not 0.0.
    """
    readings = await adherence_readings(backend, habits)
    if readings.is_error:
        return Result.fail(readings)
    return Result.ok(
        {uid: reading.rate for uid, reading in readings.value.items() if reading.rate is not None}
    )


def with_readings(habits: list[Habit], readings: dict[str, AdherenceReading]) -> list[Habit]:
    """``habits`` carrying the derived ``success_rate`` their readings hold."""
    return [replace(habit, success_rate=readings[habit.uid].rate) for habit in habits]


async def enrich_habits_with_adherence(
    backend: HabitsOperations, habits: list[Habit]
) -> Result[list[Habit]]:
    """``habits`` with their derived ``success_rate`` set — ``None`` where a habit has no rate yet.

    Every habit is re-derived, so a value carried in on the input never
    survives. A failed read fails the call: a reader judging adherence on
    habits it could not measure would read every one as unmeasured.
    """
    readings = await adherence_readings(backend, habits)
    if readings.is_error:
        return Result.fail(readings)
    return Result.ok(with_readings(habits, readings.value))


async def enrich_habit_with_adherence(backend: HabitsOperations, habit: Habit) -> Result[Habit]:
    """One habit with its derived ``success_rate`` — :func:`enrich_habits_with_adherence` for one."""
    result = await enrich_habits_with_adherence(backend, [habit])
    if result.is_error:
        return Result.fail(result)
    return Result.ok(result.value[0])


def habit_is_at_risk(habit: Habit, reading: AdherenceReading, zone: tzinfo) -> bool:
    """Whether a habit is at risk now in ``zone`` — the one definition, over its reading."""
    return habit_at_risk(
        habit.status,
        habit.recurrence_pattern,
        habit.target_days_per_week,
        rate=reading.rate,
        last_kept_on=reading.last_kept_on,
        started_on=inception_day(habit.started_at, habit.created_at, zone),
        ends_on=habit.recurrence_end_date,
        today=today_in(zone),
    )
