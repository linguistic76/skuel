"""Entity filtering and sorting for Activity Domain views.

Pure functions that filter and sort domain model lists. Extracted from
``ui/activities/*_views.py`` so business rules (status groupings, sort orders,
predicate logic) live in core, not in the UI layer.

Usage:
    from core.utils.entity_filters import filter_tasks, filter_goals
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus

if TYPE_CHECKING:
    from core.models.choice.choice import Choice
    from core.models.event.event import Event
    from core.models.goal.goal import Goal
    from core.models.habit.habit import Habit
    from core.models.principle.principle import Principle
    from core.models.task.task import Task


# -- Shared status groupings --------------------------------------------------
# Entity.status is always a canonical EntityStatus (set in __post_init__), so
# status grouping must compare enum members, never raw strings. The previous code
# compared `status.value` against alias spellings ("in_progress", "ready",
# "not_started") that EntityStatus.from_string normalizes away at ingest — so
# those branches never matched a stored value and were dead.
#
# This migration is behavior-preserving: each set is exactly the canonical members
# the old string list *actually matched*, not the (wider) set the dead aliases
# would have implied. Activating those aliases — e.g. folding SCHEDULED into
# "active" — would desync these tabs from each domain's own "active" semantics
# (compute_habit_stats and Habit.should_do_today gate strictly on ACTIVE), so any
# such widening is a deliberate cross-domain decision, not part of this refactor.

_TASK_ACTIVE_STATUSES = frozenset(
    {
        EntityStatus.ACTIVE,
        EntityStatus.DRAFT,
        EntityStatus.BLOCKED,
    }
)


# -- Shared sort constants ----------------------------------------------------

PRIORITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}

STRENGTH_ORDER: dict[str, int] = {
    "core": 0,
    "strong": 1,
    "moderate": 2,
    "developing": 3,
    "exploring": 4,
}


# =============================================================================
# Tasks
# =============================================================================


def _task_sort_by_priority(task: Task) -> int:
    return PRIORITY_ORDER.get(str(task.priority) if task.priority else "", 4)


def _task_sort_by_due_date(task: Task) -> str:
    return str(task.due_date or "9999-12-31")


def _task_sort_by_title(task: Task) -> str:
    return (task.title or "").lower()


def _task_sort_by_updated(task: Task) -> str:
    return str(task.updated_at or "")


def filter_tasks(
    tasks: list[Task],
    status_filter: str = "active",
    priority_filter: str = "all",
    sort_by: str = "priority",
) -> list[Task]:
    """Apply filters and sorting to a task list."""
    filtered = list(tasks)

    if status_filter == "active":
        filtered = [t for t in filtered if not t.status or t.status in _TASK_ACTIVE_STATUSES]
    elif status_filter == "completed":
        filtered = [t for t in filtered if t.status == EntityStatus.COMPLETED]
    elif status_filter == "overdue":
        filtered = [t for t in filtered if t.is_overdue()]

    if priority_filter != "all":
        filtered = [t for t in filtered if t.priority and str(t.priority) == priority_filter]

    if sort_by == "priority":
        filtered.sort(key=_task_sort_by_priority)
    elif sort_by == "due_date":
        filtered.sort(key=_task_sort_by_due_date)
    elif sort_by == "title":
        filtered.sort(key=_task_sort_by_title)
    elif sort_by == "updated":
        filtered.sort(key=_task_sort_by_updated, reverse=True)

    return filtered


# =============================================================================
# Goals
# =============================================================================


def _goal_sort_by_priority(goal: Goal) -> int:
    return PRIORITY_ORDER.get(str(goal.priority) if goal.priority else "", 4)


def _goal_sort_by_target_date(goal: Goal) -> str:
    return str(goal.target_date or "9999-12-31")


def _goal_sort_by_progress(goal: Goal) -> float:
    return -goal.calculate_progress()


def _goal_sort_by_title(goal: Goal) -> str:
    return (goal.title or "").lower()


def filter_goals(
    goals: list[Goal],
    status_filter: str = "active",
    category_filter: str = "all",
    sort_by: str = "target_date",
) -> list[Goal]:
    """Apply filters and sorting to a goal list.

    Goal "category" is the ``domain`` field (DomainConfig category_field="domain").
    """
    filtered = list(goals)

    if category_filter != "all":
        filtered = [g for g in filtered if g.domain and g.domain.value == category_filter]

    if status_filter == "active":
        # ACTIVE only is correct: GoalsCoreService.create_goal forces status=ACTIVE
        # (overriding the DRAFT default) so new goals land here, and goal stats /
        # tabs treat ACTIVE as the open state. DRAFT/SCHEDULED are not goal states
        # reached in practice, so widening this set would only desync the tab.
        filtered = [g for g in filtered if not g.status or g.status == EntityStatus.ACTIVE]
    elif status_filter == "completed":
        filtered = [g for g in filtered if g.is_completed]
    elif status_filter == "on_track":
        filtered = [g for g in filtered if g.is_on_track() and not g.is_completed]
    elif status_filter == "wobbly":
        filtered = [g for g in filtered if not g.is_on_track() and not g.is_completed]

    if sort_by == "target_date":
        filtered.sort(key=_goal_sort_by_target_date)
    elif sort_by == "priority":
        filtered.sort(key=_goal_sort_by_priority)
    elif sort_by == "progress":
        filtered.sort(key=_goal_sort_by_progress)
    elif sort_by == "title":
        filtered.sort(key=_goal_sort_by_title)

    return filtered


# =============================================================================
# Habits
# =============================================================================


def filter_habits(
    habits: list[Habit],
    status_filter: str = "active",
    category_filter: str = "all",
    sort_by: str = "streak",
) -> list[Habit]:
    """Apply filters and sorting to a habit list."""
    filtered = list(habits)

    if status_filter == "active":
        filtered = [h for h in filtered if not h.status or h.status == EntityStatus.ACTIVE]
    elif status_filter == "paused":
        filtered = [h for h in filtered if h.status == EntityStatus.PAUSED]
    elif status_filter == "completed":
        filtered = [h for h in filtered if h.status == EntityStatus.COMPLETED]
    elif status_filter == "keystone":
        filtered = [h for h in filtered if h.is_keystone]

    if category_filter != "all":
        filtered = [
            h for h in filtered if h.habit_category and h.habit_category.value == category_filter
        ]

    def by_streak(h: Any) -> int:
        return -(h.current_streak or 0)

    def by_name(h: Any) -> str:
        return (h.title or "").lower()

    def by_created(h: Any) -> str:
        return str(h.created_at or "")

    if sort_by == "streak":
        filtered.sort(key=by_streak)
    elif sort_by == "name":
        filtered.sort(key=by_name)
    elif sort_by == "created":
        filtered.sort(key=by_created, reverse=True)

    return filtered


# =============================================================================
# Events
# =============================================================================


def filter_events(
    events: list[Event],
    status_filter: str = "upcoming",
    sort_by: str = "date",
) -> list[Event]:
    """Apply filters and sorting to an event list."""
    filtered = list(events)

    if status_filter == "upcoming":
        filtered = [e for e in filtered if e.is_upcoming()]
    elif status_filter == "today":
        filtered = [e for e in filtered if e.is_today()]
    elif status_filter == "completed":
        filtered = [e for e in filtered if e.status == EntityStatus.COMPLETED]

    def by_date(e: Any) -> str:
        return str(e.event_date or "9999-12-31")

    def by_title(e: Any) -> str:
        return (e.title or "").lower()

    def by_created(e: Any) -> str:
        return str(e.created_at or "")

    if sort_by == "date":
        filtered.sort(key=by_date)
    elif sort_by == "title":
        filtered.sort(key=by_title)
    elif sort_by == "created":
        filtered.sort(key=by_created, reverse=True)

    return filtered


# =============================================================================
# Choices
# =============================================================================


def filter_choices(
    choices: list[Choice],
    status_filter: str = "pending",
    sort_by: str = "deadline",
) -> list[Choice]:
    """Apply filters and sorting to a choice list."""
    filtered = list(choices)

    if status_filter == "pending":
        filtered = [c for c in filtered if not c.decided_at and c.status != EntityStatus.COMPLETED]
    elif status_filter == "decided":
        filtered = [c for c in filtered if c.decided_at or c.status == EntityStatus.COMPLETED]

    def by_deadline(c: Any) -> str:
        return str(c.decision_deadline or "9999-12-31")[:10]

    def by_priority(c: Any) -> int:
        return PRIORITY_ORDER.get(str(c.priority) if c.priority else "", 4)

    def by_title(c: Any) -> str:
        return (c.title or "").lower()

    def by_created(c: Any) -> str:
        return str(c.created_at or "")

    if sort_by == "deadline":
        filtered.sort(key=by_deadline)
    elif sort_by == "priority":
        filtered.sort(key=by_priority)
    elif sort_by == "title":
        filtered.sort(key=by_title)
    elif sort_by == "created":
        filtered.sort(key=by_created, reverse=True)

    return filtered


# =============================================================================
# Principles
# =============================================================================


def filter_principles(
    principles: list[Principle],
    status_filter: str = "active",
    category_filter: str = "all",
    strength_filter: str = "all",
    sort_by: str = "strength",
) -> list[Principle]:
    """Apply filters and sorting to a principle list."""
    filtered = list(principles)

    if status_filter == "active":
        filtered = [p for p in filtered if p.is_active is None or p.is_active]

    if category_filter != "all":
        filtered = [
            p
            for p in filtered
            if p.principle_category and p.principle_category.value == category_filter
        ]

    if strength_filter != "all":
        filtered = [p for p in filtered if p.strength and p.strength.value == strength_filter]

    def by_strength(p: Any) -> int:
        return STRENGTH_ORDER.get(p.strength.value if p.strength else "", 5)

    def by_name(p: Any) -> str:
        return (p.title or "").lower()

    def by_created(p: Any) -> str:
        return str(p.created_at or "")

    if sort_by == "strength":
        filtered.sort(key=by_strength)
    elif sort_by == "name":
        filtered.sort(key=by_name)
    elif sort_by == "created":
        filtered.sort(key=by_created, reverse=True)

    return filtered
