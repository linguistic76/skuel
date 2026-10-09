"""The goal progress dashboard's three derived figures — each one definition, over one read.

``get_goal_progress_dashboard`` reports, beside the contribution tally's percentage
(``contribution_progress``), how a goal's habits and its required knowledge are
carrying it, and whether it needs more tasks. The three are derived here from reads
the backend makes for the one goal, never from the path-aware neighbourhood the
dashboard also lists: the neighbourhood is what the graph reaches at a confidence,
the figures are what the owner has done.

- :func:`needs_more_tasks` — the contribution tally holds fewer counting
  contributions than :attr:`core.constants.GoalDashboard.MIN_COUNTING_CONTRIBUTIONS`.
- :func:`habit_support_contribution` — the essentiality-weighted mean adherence of
  the goal's supporting habits, as a percentage.
- :func:`knowledge_mastery_contribution` — the share of the goal's required
  knowledge its owner has mastered, as a percentage.
"""

from __future__ import annotations

from datetime import tzinfo

from core.constants import GoalDashboard
from core.models.enums.goal_enums import HabitEssentiality
from core.models.habit.adherence import completion_days, habit_adherence, inception_day
from core.ports.query_types import ContributionTally, RequiredKnowledgeTally, SupportingHabitWindow
from core.utils.timestamp_helpers import today_in


def needs_more_tasks(tally: ContributionTally) -> bool:
    """Whether the goal's tally holds fewer counting contributions than the dashboard asks for.

    Counted by the tally's membership rule — a task that opts out of counting, or a
    cancelled one, is not a contribution here however near the goal it sits.
    """
    return tally["total_contributions"] < GoalDashboard.MIN_COUNTING_CONTRIBUTIONS


def habit_support_contribution(rows: list[SupportingHabitWindow], zone: tzinfo) -> float:
    """The essentiality-weighted mean adherence of the goal's supporting habits, 0-100.

    Each habit's adherence is the one definition
    (:func:`~core.models.habit.adherence.habit_adherence`): its window completions
    counted against its own cadence from the day it started, as of today in
    ``zone``. Its weight is its ``SUPPORTS_GOAL`` edge's tier
    (:meth:`HabitEssentiality.get_weight`), so an essential habit kept half the
    time pulls the figure down four times as hard as an optional one does. A habit
    with no rate yet — nothing due in its span, or a cadence the window cannot
    measure — is left out of both sides of the mean: no measurement is not a zero.
    0.0 when no supporting habit has a rate.
    """
    today = today_in(zone)
    weighted = 0.0
    weights = 0.0
    for row in rows:
        habit = row["habit"]
        rate = habit_adherence(
            habit.recurrence_pattern,
            habit.target_days_per_week,
            completion_days(row["completion_stamps"], zone),
            started_on=inception_day(habit.started_at, habit.created_at, zone),
            ends_on=habit.recurrence_end_date,
            today=today,
        )
        if rate is None:
            continue
        weight = HabitEssentiality.from_stored(row["essentiality"]).get_weight()
        weighted += rate * weight
        weights += weight
    if weights == 0.0:
        return 0.0
    return weighted / weights * 100


def knowledge_mastery_contribution(tally: RequiredKnowledgeTally) -> float:
    """The share of the goal's required knowledge its owner has mastered, 0-100.

    The per-goal figure the user context computes as ``goal_completion_from_graph``
    (mastered required Kus over required Kus), read for one goal. 0.0 when the goal
    requires nothing.
    """
    required = tally["required_knowledge"]
    if required == 0:
        return 0.0
    return tally["mastered_knowledge"] / required * 100
