"""Hydrate the derived ``Habit.success_rate`` and judge a habit at risk — the habit readers' one path.

``Habit.success_rate`` is the habit's adherence now
(``core.models.habit.adherence.habit_adherence``), derived at read time and never
a node property: a reader that needs it hands the habits it read to
:func:`enrich_habits_with_adherence`, which reads every habit's completions in
the trailing window in one backend call
(``HabitsOperations.get_habit_window_completions``, owner-scoped) and returns
new Habit instances carrying the rate. A habit with no rate yet keeps ``None``.

:func:`habit_is_at_risk` applies the one at-risk definition
(``core.models.habit.adherence.habit_at_risk``) to a hydrated Habit.

Design: ``docs/roadmap/habit-completion-persistence-bundle.md``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import tzinfo
from typing import TYPE_CHECKING

from core.models.habit.adherence import (
    adherence_window_days,
    completion_days,
    creation_day,
    habit_adherence,
    habit_at_risk,
    stamp_day,
)
from core.utils.result_simplified import Errors, Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

if TYPE_CHECKING:
    from core.models.habit.habit import Habit
    from core.ports.domain_protocols import HabitsOperations


async def adherence_rates(
    backend: HabitsOperations, habits: list[Habit]
) -> Result[dict[str, float]]:
    """Each habit's adherence now, keyed by uid — the habits that have a rate.

    One read of every habit's window completions, each counted by
    :func:`~core.models.habit.adherence.habit_adherence` against the habit's
    cadence and creation day. A habit with no rate yet is left out — no
    measurement, not 0.0.
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
                operation="adherence_rates",
            )
        )
    rates: dict[str, float] = {}
    for habit in habits:
        rate = habit_adherence(
            habit.recurrence_pattern,
            habit.target_days_per_week,
            completion_days(stamps[habit.uid], zone),
            created_on=creation_day(habit.created_at, zone),
            today=today,
        )
        if rate is not None:
            rates[habit.uid] = rate
    return Result.ok(rates)


async def enrich_habits_with_adherence(
    backend: HabitsOperations, habits: list[Habit]
) -> Result[list[Habit]]:
    """``habits`` with their derived ``success_rate`` set — ``None`` where a habit has no rate yet.

    Every habit is re-derived, so a value carried in on the input never
    survives. A failed read fails the call: a reader judging adherence on
    habits it could not measure would read every one as unmeasured.
    """
    rates_result = await adherence_rates(backend, habits)
    if rates_result.is_error:
        return Result.fail(rates_result)
    rates = rates_result.value
    return Result.ok([replace(habit, success_rate=rates.get(habit.uid)) for habit in habits])


async def enrich_habit_with_adherence(backend: HabitsOperations, habit: Habit) -> Result[Habit]:
    """One habit with its derived ``success_rate`` — :func:`enrich_habits_with_adherence` for one."""
    result = await enrich_habits_with_adherence(backend, [habit])
    if result.is_error:
        return Result.fail(result)
    return Result.ok(result.value[0])


def habit_is_at_risk(habit: Habit, zone: tzinfo) -> bool:
    """Whether a hydrated habit is at risk now in ``zone`` — the one definition, read off the Habit."""
    return habit_at_risk(
        habit.status,
        habit.recurrence_pattern,
        habit.target_days_per_week,
        rate=habit.success_rate,
        last_completed_on=stamp_day(habit.last_completed, zone),
        created_on=creation_day(habit.created_at, zone),
        today=today_in(zone),
    )
