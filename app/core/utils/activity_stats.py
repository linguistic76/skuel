"""Activity domain stats computation.

Pure functions for aggregating statistics from lists of activity domain models
(Tasks, Goals, Habits, Events, Choices, Principles). No I/O, no service calls.

This module is THE single source of truth for activity domain stats. Two views
exist over each computation:

* **Typed dataclass** (`compute_*_stats`) — used by UI view components that want
  attribute access and rich extras (e.g. ``GoalStats.wobbly_count``).
* **Dict projection** — each domain facade exposes a one-line ``_compute_*_stats``
  adapter that calls the dataclass function and returns a ``dict[str, int | float]``.
  The dict shape is the cross-domain contract consumed by
  ``DailyPlanningMixin._query_domain_stats`` via ``ListContext["stats"]``.

Both views share the same field semantics — there is exactly one definition of
each metric.
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus
from core.utils.type_converters import get_enum_attr_str

if TYPE_CHECKING:
    from core.models.choice.choice import Choice
    from core.models.event.event import Event
    from core.models.goal.goal import Goal
    from core.models.habit.habit import Habit
    from core.models.principle.principle import Principle
    from core.models.task.task import Task


# ============================================================================
# Tasks
# ============================================================================


@dataclass(frozen=True)
class TaskStats:
    """Aggregated stats for a list of Task entities."""

    total: int
    active: int
    completed: int
    overdue: int


def compute_task_stats(tasks: list["Task"]) -> TaskStats:
    """Compute aggregate stats from a list of Task domain models.

    Semantics:
        active = total - completed (everything not in COMPLETED state)
        overdue = past due_date and not completed
    """
    today = date.today()
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == EntityStatus.COMPLETED)
    overdue = sum(
        1
        for t in tasks
        if t.due_date and t.due_date < today and t.status != EntityStatus.COMPLETED
    )
    return TaskStats(
        total=total,
        active=total - completed,
        completed=completed,
        overdue=overdue,
    )


# ============================================================================
# Goals
# ============================================================================


@dataclass(frozen=True)
class GoalStats:
    """Aggregated stats for a list of Goal entities.

    Combines the cross-domain dict contract (total/active/completed) with
    UI-only extras for the GoalStatsBar (on_track/wobbly/overdue/behind).
    """

    total: int
    active: int
    completed: int
    on_track: int
    wobbly_count: int
    overdue_count: int
    behind_count: int

    @property
    def wobbly_detail(self) -> str | None:
        """Human-readable breakdown of wobbly goals, or None if none."""
        if not self.wobbly_count:
            return None
        parts = []
        if self.behind_count:
            parts.append(f"{self.behind_count} behind")
        if self.overdue_count:
            parts.append(f"{self.overdue_count} overdue")
        return ", ".join(parts) if parts else None


_GOAL_TERMINAL_STATUSES = (
    EntityStatus.COMPLETED,
    EntityStatus.CANCELLED,
    EntityStatus.ARCHIVED,
)


def compute_goal_stats(goals: list["Goal"]) -> GoalStats:
    """Compute aggregate stats from a list of Goal domain models.

    Semantics:
        active = status not in (COMPLETED, CANCELLED, ARCHIVED)
        completed = status == COMPLETED
        on_track / overdue / behind use the Goal model's own predicates.
    """
    total = len(goals)
    active = sum(
        1 for g in goals if get_enum_attr_str(g, "status", "active") not in _GOAL_TERMINAL_STATUSES
    )
    completed = sum(
        1 for g in goals if get_enum_attr_str(g, "status", "active") == EntityStatus.COMPLETED
    )
    on_track = sum(1 for g in goals if g.is_on_track() and not g.is_completed)
    overdue_count = sum(1 for g in goals if g.is_overdue())
    behind_count = sum(
        1 for g in goals if not g.is_on_track() and not g.is_completed and not g.is_overdue()
    )
    return GoalStats(
        total=total,
        active=active,
        completed=completed,
        on_track=on_track,
        wobbly_count=overdue_count + behind_count,
        overdue_count=overdue_count,
        behind_count=behind_count,
    )


# ============================================================================
# Habits
# ============================================================================


@dataclass(frozen=True)
class HabitStats:
    """Aggregated stats for a list of Habit entities.

    Combines the cross-domain dict contract (total/active/streaks) with
    UI-only extras for the HabitStatsBar (avg_streak/keystone_count).
    """

    total: int
    active: int
    streaks: int
    avg_streak: float
    keystone_count: int


def compute_habit_stats(habits: list["Habit"]) -> HabitStats:
    """Compute aggregate stats from a list of Habit domain models.

    Semantics:
        active = status == ACTIVE (strict)
        streaks = count of habits with current_streak > 0
        avg_streak = mean current_streak across habits with streak > 0
    """
    total = len(habits)
    active = sum(1 for h in habits if h.status == EntityStatus.ACTIVE)
    streak_values = [h.current_streak for h in habits if getattr(h, "current_streak", 0) > 0]
    streaks = len(streak_values)
    avg_streak = sum(streak_values) / streaks if streaks else 0.0
    keystone_count = sum(1 for h in habits if getattr(h, "is_keystone", False))
    return HabitStats(
        total=total,
        active=active,
        streaks=streaks,
        avg_streak=avg_streak,
        keystone_count=keystone_count,
    )


# ============================================================================
# Events
# ============================================================================


@dataclass(frozen=True)
class EventStats:
    """Aggregated stats for a list of Event entities."""

    total: int
    active: int
    scheduled: int
    today: int


_EVENT_TERMINAL_STATUSES = frozenset({"completed", "cancelled", "archived"})


def compute_event_stats(events: list["Event"]) -> EventStats:
    """Compute aggregate stats from a list of Event domain models.

    Semantics:
        active = status not in (completed, cancelled, archived)
        scheduled = status == "scheduled"
        today = event_date == today
    """
    today = date.today()
    total = len(events)
    active = sum(
        1 for e in events if get_enum_attr_str(e, "status", "scheduled") not in _EVENT_TERMINAL_STATUSES
    )
    scheduled = sum(1 for e in events if get_enum_attr_str(e, "status", "scheduled") == "scheduled")
    today_count = sum(1 for e in events if getattr(e, "event_date", None) == today)
    return EventStats(
        total=total,
        active=active,
        scheduled=scheduled,
        today=today_count,
    )


# ============================================================================
# Choices
# ============================================================================


@dataclass(frozen=True)
class ChoiceStats:
    """Aggregated stats for a list of Choice entities."""

    total: int
    active: int
    pending: int
    decided: int


def compute_choice_stats(choices: list["Choice"]) -> ChoiceStats:
    """Compute aggregate stats from a list of Choice domain models.

    Semantics:
        active = pending count (a pending choice is the only "active" state)
        pending = status == "pending"
        decided = status == "decided"
    """
    total = len(choices)
    pending = sum(1 for c in choices if get_enum_attr_str(c, "status") == "pending")
    decided = sum(1 for c in choices if get_enum_attr_str(c, "status") == "decided")
    return ChoiceStats(
        total=total,
        active=pending,
        pending=pending,
        decided=decided,
    )


# ============================================================================
# Principles
# ============================================================================


@dataclass(frozen=True)
class PrincipleStats:
    """Aggregated stats for a list of Principle entities."""

    total: int
    core: int
    active: int


def _principle_strength_rank(p: Any) -> int:
    """Numeric rank for PrincipleStrength values (CORE=5 ... EXPLORING=1).

    Local mirror of the rank table in principles_service so this module stays
    free of service-layer imports. CORE is the only rank with value 5.
    """
    from core.models.enums.principle_enums import PrincipleStrength

    rank = {
        PrincipleStrength.CORE: 5,
        PrincipleStrength.STRONG: 4,
        PrincipleStrength.MODERATE: 3,
        PrincipleStrength.DEVELOPING: 2,
        PrincipleStrength.EXPLORING: 1,
    }
    s = getattr(p, "strength", PrincipleStrength.MODERATE)
    if isinstance(s, PrincipleStrength):
        return rank.get(s, 3)
    if isinstance(s, str):
        s_upper = s.upper()
        for enum_val in PrincipleStrength:
            if enum_val.value == s or enum_val.name == s_upper:
                return rank.get(enum_val, 3)
    return 3


def compute_principle_stats(principles: list["Principle"]) -> PrincipleStats:
    """Compute aggregate stats from a list of Principle domain models.

    Semantics:
        core = strength rank >= 5 (i.e. PrincipleStrength.CORE)
        active = is_active flag (defaults True if missing)
    """
    return PrincipleStats(
        total=len(principles),
        core=sum(1 for p in principles if _principle_strength_rank(p) >= 5),
        active=sum(1 for p in principles if getattr(p, "is_active", True)),
    )


__all__ = [
    "ChoiceStats",
    "EventStats",
    "GoalStats",
    "HabitStats",
    "PrincipleStats",
    "TaskStats",
    "compute_choice_stats",
    "compute_event_stats",
    "compute_goal_stats",
    "compute_habit_stats",
    "compute_principle_stats",
    "compute_task_stats",
]
