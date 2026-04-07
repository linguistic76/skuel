"""Activity domain stats computation.

Pure functions for aggregating statistics from lists of activity domain models
(Goals, Habits, Tasks). No I/O, no service calls.

These are consumed by UI StatsBar components and any other layer that needs
aggregate counts from a loaded list of entities.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.goal.goal import Goal
    from core.models.habit.habit import Habit
    from core.models.task.task import Task


@dataclass(frozen=True)
class GoalStats:
    """Aggregated stats for a list of Goal entities."""

    total: int
    active: int
    on_track: int
    completed: int
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


@dataclass(frozen=True)
class HabitStats:
    """Aggregated stats for a list of Habit entities."""

    total: int
    active: int
    avg_streak: float
    keystone_count: int


@dataclass(frozen=True)
class TaskStats:
    """Aggregated stats for a list of Task entities."""

    total: int
    active: int
    completed: int
    overdue: int


def compute_goal_stats(goals: list["Goal"]) -> GoalStats:
    """Compute aggregate stats from a list of Goal domain models."""
    total = len(goals)
    active = sum(1 for g in goals if g.status and g.status.value in ("active", "in_progress"))
    on_track = sum(1 for g in goals if g.is_on_track() and not g.is_completed)
    completed = sum(1 for g in goals if g.is_completed)
    overdue_count = sum(1 for g in goals if g.is_overdue())
    behind_count = sum(
        1 for g in goals if not g.is_on_track() and not g.is_completed and not g.is_overdue()
    )
    return GoalStats(
        total=total,
        active=active,
        on_track=on_track,
        completed=completed,
        wobbly_count=overdue_count + behind_count,
        overdue_count=overdue_count,
        behind_count=behind_count,
    )


def compute_habit_stats(habits: list["Habit"]) -> HabitStats:
    """Compute aggregate stats from a list of Habit domain models."""
    total = len(habits)
    active = sum(1 for h in habits if h.status and h.status.value in ("active", "in_progress"))
    streaks = [h.current_streak for h in habits if h.current_streak and h.current_streak > 0]
    avg_streak = sum(streaks) / len(streaks) if streaks else 0.0
    keystone_count = sum(1 for h in habits if h.is_keystone)
    return HabitStats(
        total=total,
        active=active,
        avg_streak=avg_streak,
        keystone_count=keystone_count,
    )


def compute_task_stats(tasks: list["Task"]) -> TaskStats:
    """Compute aggregate stats from a list of Task domain models."""
    total = len(tasks)
    active = sum(
        1 for t in tasks if t.status and t.status.value in ("active", "in_progress", "ready")
    )
    completed = sum(1 for t in tasks if t.status and t.status.value == "completed")
    overdue = sum(1 for t in tasks if t.is_overdue())
    return TaskStats(total=total, active=active, completed=completed, overdue=overdue)


__all__ = [
    "GoalStats",
    "HabitStats",
    "TaskStats",
    "compute_goal_stats",
    "compute_habit_stats",
    "compute_task_stats",
]
