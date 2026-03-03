"""
Unit tests for module-level query helpers in activity domain service files.

These helpers are pure functions (no I/O) extracted from route closures during
the Activity Domain UI Query Layer Refactor (Phase 3). Being module-level means
they are directly testable without mocking any service or database.

Domains covered: habits, tasks, goals, events, choices, principles.
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from core.models.enums import EntityStatus, Priority
from core.models.enums.principle_enums import PrincipleStrength
from core.services.choices_service import (
    _apply_choice_filters,
    _apply_choice_sort,
    _compute_choice_stats,
    _get_choice_enum_value,
)
from core.services.events_service import (
    _apply_event_filters,
    _apply_event_sort,
    _compute_event_stats,
    _get_event_status_value,
)
from core.services.goals_service import (
    _apply_goal_filters,
    _apply_goal_sort,
    _compute_goal_stats,
    _get_goal_priority_str,
    _get_goal_status_str,
    _get_goal_target_date,
)
from core.services.habits_service import (
    _apply_habit_filters,
    _apply_habit_sort,
    _compute_habit_stats,
)
from core.services.principles_service import (
    _apply_principle_filters,
    _apply_principle_sort,
    _compute_principle_stats,
    _get_principle_strength_value,
)
from core.services.tasks_service import (
    _apply_task_filters,
    _apply_task_sort,
    _compute_task_stats,
)


# ============================================================================
# HABITS
# ============================================================================


def make_habit(status: str = "active", current_streak: int = 0, **kwargs) -> Any:
    status_mock = Mock()
    status_mock.value = status
    return SimpleNamespace(
        status=status_mock,
        current_streak=current_streak,
        name=kwargs.get("name", "habit"),
        created_at=kwargs.get("created_at", datetime(2024, 1, 1)),
        recurrence_pattern=kwargs.get("recurrence_pattern", "daily"),
    )


class TestComputeHabitStats:
    def test_empty_list(self):
        stats = _compute_habit_stats([])
        assert stats == {"total": 0, "active": 0, "streaks": 0}

    def test_counts_active(self):
        habits = [make_habit("active"), make_habit("paused"), make_habit("active")]
        stats = _compute_habit_stats(habits)
        assert stats["total"] == 3
        assert stats["active"] == 2

    def test_counts_streaks(self):
        habits = [make_habit(current_streak=5), make_habit(current_streak=0)]
        stats = _compute_habit_stats(habits)
        assert stats["streaks"] == 1

    def test_stats_over_full_list_not_filtered(self):
        """Stats count all habits regardless of any filter that will follow."""
        habits = [make_habit("active"), make_habit("paused"), make_habit("completed")]
        stats = _compute_habit_stats(habits)
        assert stats["total"] == 3
        assert stats["active"] == 1


class TestApplyHabitFilters:
    def test_active_filter(self):
        habits = [make_habit("active"), make_habit("paused"), make_habit("completed")]
        result = _apply_habit_filters(habits, "active")
        assert all(h.status.value == "active" for h in result)
        assert len(result) == 1

    def test_paused_filter(self):
        habits = [make_habit("active"), make_habit("paused")]
        result = _apply_habit_filters(habits, "paused")
        assert len(result) == 1
        assert result[0].status.value == "paused"

    def test_all_filter_returns_everything(self):
        habits = [make_habit("active"), make_habit("paused"), make_habit("completed")]
        result = _apply_habit_filters(habits, "all")
        assert len(result) == 3

    def test_unknown_filter_returns_all(self):
        habits = [make_habit("active"), make_habit("paused")]
        result = _apply_habit_filters(habits, "unknown")
        assert len(result) == 2


class TestApplyHabitSort:
    def test_sort_by_streak_descending(self):
        habits = [make_habit(current_streak=1), make_habit(current_streak=5)]
        result = _apply_habit_sort(habits, "streak")
        assert result[0].current_streak == 5

    def test_sort_by_name(self):
        habits = [make_habit(name="Zebra"), make_habit(name="Alpha")]
        result = _apply_habit_sort(habits, "name")
        assert result[0].name == "Alpha"

    def test_sort_by_created_at_descending(self):
        habits = [
            make_habit(created_at=datetime(2024, 1, 1)),
            make_habit(created_at=datetime(2024, 6, 1)),
        ]
        result = _apply_habit_sort(habits, "created_at")
        assert result[0].created_at == datetime(2024, 6, 1)

    def test_default_sorts_by_streak(self):
        habits = [make_habit(current_streak=1), make_habit(current_streak=10)]
        result = _apply_habit_sort(habits)
        assert result[0].current_streak == 10


# ============================================================================
# TASKS
# ============================================================================


def make_task(
    status: EntityStatus = EntityStatus.ACTIVE,
    due_date: date | None = None,
    project: str = "",
    assignee: str | None = None,
    priority: Priority = Priority.MEDIUM,
    created_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        status=status,
        due_date=due_date,
        project=project,
        assignee=assignee,
        priority=priority,
        created_at=created_at or datetime(2024, 1, 1),
        title="task",
    )


class TestComputeTaskStats:
    def test_empty_list(self):
        stats = _compute_task_stats([])
        assert stats == {"total": 0, "completed": 0, "overdue": 0}

    def test_counts_completed(self):
        tasks = [make_task(EntityStatus.COMPLETED), make_task(EntityStatus.ACTIVE)]
        stats = _compute_task_stats(tasks)
        assert stats["completed"] == 1

    def test_counts_overdue(self):
        yesterday = date.today() - timedelta(days=1)
        tasks = [
            make_task(EntityStatus.ACTIVE, due_date=yesterday),  # overdue
            make_task(EntityStatus.COMPLETED, due_date=yesterday),  # not counted (completed)
            make_task(EntityStatus.ACTIVE),  # no due date
        ]
        stats = _compute_task_stats(tasks)
        assert stats["overdue"] == 1


class TestApplyTaskFilters:
    def test_active_filter_excludes_completed(self):
        tasks = [make_task(EntityStatus.ACTIVE), make_task(EntityStatus.COMPLETED)]
        result = _apply_task_filters(tasks, status_filter="active")
        assert len(result) == 1
        assert result[0].status == EntityStatus.ACTIVE

    def test_completed_filter(self):
        tasks = [make_task(EntityStatus.ACTIVE), make_task(EntityStatus.COMPLETED)]
        result = _apply_task_filters(tasks, status_filter="completed")
        assert len(result) == 1
        assert result[0].status == EntityStatus.COMPLETED

    def test_all_filter(self):
        tasks = [make_task(EntityStatus.ACTIVE), make_task(EntityStatus.COMPLETED)]
        result = _apply_task_filters(tasks, status_filter="all")
        assert len(result) == 2

    def test_project_filter(self):
        tasks = [make_task(project="Alpha"), make_task(project="Beta"), make_task(project="Alpha")]
        result = _apply_task_filters(tasks, project="Alpha")
        assert len(result) == 2

    def test_due_today_filter(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        tasks = [make_task(due_date=today), make_task(due_date=tomorrow)]
        result = _apply_task_filters(tasks, due_filter="today")
        assert len(result) == 1
        assert result[0].due_date == today

    def test_overdue_filter(self):
        yesterday = date.today() - timedelta(days=1)
        tasks = [
            make_task(EntityStatus.ACTIVE, due_date=yesterday),
            make_task(EntityStatus.COMPLETED, due_date=yesterday),
            make_task(EntityStatus.ACTIVE, due_date=date.today()),
        ]
        result = _apply_task_filters(tasks, due_filter="overdue")
        assert len(result) == 1

    def test_combined_project_and_status_filter(self):
        tasks = [
            make_task(EntityStatus.ACTIVE, project="Alpha"),
            make_task(EntityStatus.COMPLETED, project="Alpha"),
            make_task(EntityStatus.ACTIVE, project="Beta"),
        ]
        result = _apply_task_filters(tasks, project="Alpha", status_filter="active")
        assert len(result) == 1
        assert result[0].project == "Alpha"
        assert result[0].status == EntityStatus.ACTIVE


class TestApplyTaskSort:
    def test_sort_by_priority(self):
        tasks = [
            make_task(priority=Priority.LOW),
            make_task(priority=Priority.CRITICAL),
        ]
        result = _apply_task_sort(tasks, "priority")
        assert result[0].priority == Priority.CRITICAL

    def test_sort_by_created_at_descending(self):
        tasks = [
            make_task(created_at=datetime(2024, 1, 1)),
            make_task(created_at=datetime(2024, 12, 1)),
        ]
        result = _apply_task_sort(tasks, "created_at")
        assert result[0].created_at == datetime(2024, 12, 1)

    def test_default_sorts_by_due_date(self):
        tasks = [
            make_task(due_date=date(2024, 12, 31)),
            make_task(due_date=date(2024, 1, 1)),
        ]
        result = _apply_task_sort(tasks)
        assert result[0].due_date == date(2024, 1, 1)


# ============================================================================
# GOALS
# ============================================================================


def make_goal(
    status: str = "active",
    priority: str = "medium",
    target_date: date | None = None,
    current_value: float = 0.0,
    created_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        status=status,
        priority=priority,
        target_date=target_date,
        current_value=current_value,
        category="personal",
        created_at=created_at or datetime(2024, 1, 1),
        title="goal",
    )


class TestGoalAccessors:
    def test_get_status_str_string(self):
        goal = make_goal(status="active")
        assert _get_goal_status_str(goal) == "active"

    def test_get_status_str_enum(self):
        goal = make_goal()
        goal.status = EntityStatus.ACTIVE
        assert _get_goal_status_str(goal) == EntityStatus.ACTIVE.value.lower()

    def test_get_priority_str_string(self):
        goal = make_goal(priority="high")
        assert _get_goal_priority_str(goal) == "high"

    def test_get_target_date_returns_date(self):
        d = date(2025, 6, 1)
        goal = make_goal(target_date=d)
        assert _get_goal_target_date(goal) == d

    def test_get_target_date_none_returns_max(self):
        goal = make_goal(target_date=None)
        assert _get_goal_target_date(goal) == date.max

    def test_get_target_date_iso_string(self):
        goal = make_goal()
        goal.target_date = "2025-06-01"
        assert _get_goal_target_date(goal) == date(2025, 6, 1)


class TestComputeGoalStats:
    def test_empty_list(self):
        stats = _compute_goal_stats([])
        assert stats == {"total": 0, "active": 0, "completed": 0}

    def test_counts_correctly(self):
        goals = [make_goal("active"), make_goal("active"), make_goal("completed")]
        stats = _compute_goal_stats(goals)
        assert stats["total"] == 3
        assert stats["active"] == 2
        assert stats["completed"] == 1


class TestApplyGoalFilters:
    def test_active_filter(self):
        goals = [make_goal("active"), make_goal("completed"), make_goal("paused")]
        result = _apply_goal_filters(goals, "active")
        assert len(result) == 1
        assert result[0].status == "active"

    def test_all_filter(self):
        goals = [make_goal("active"), make_goal("completed")]
        result = _apply_goal_filters(goals, "all")
        assert len(result) == 2


class TestApplyGoalSort:
    def test_sort_by_target_date(self):
        goals = [
            make_goal(target_date=date(2025, 12, 31)),
            make_goal(target_date=date(2025, 1, 1)),
        ]
        result = _apply_goal_sort(goals, "target_date")
        assert result[0].target_date == date(2025, 1, 1)

    def test_none_target_date_sorts_last(self):
        goals = [make_goal(target_date=None), make_goal(target_date=date(2025, 6, 1))]
        result = _apply_goal_sort(goals, "target_date")
        assert result[0].target_date == date(2025, 6, 1)

    def test_sort_by_priority(self):
        goals = [make_goal(priority="low"), make_goal(priority="critical")]
        result = _apply_goal_sort(goals, "priority")
        assert result[0].priority == "critical"


# ============================================================================
# EVENTS
# ============================================================================


def make_event(
    status: str = "scheduled",
    event_date: date | None = None,
    start_time: time | None = None,
    title: str = "event",
    created_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        status=status,
        event_date=event_date,
        start_time=start_time,
        title=title,
        created_at=created_at or datetime(2024, 1, 1),
    )


class TestGetEventStatusValue:
    def test_string_status(self):
        event = make_event("scheduled")
        assert _get_event_status_value(event) == "scheduled"

    def test_none_status_returns_scheduled(self):
        event = make_event()
        event.status = None
        assert _get_event_status_value(event) == "scheduled"

    def test_enum_status(self):
        event = make_event()
        event.status = EntityStatus.ACTIVE
        # Returns lowercase value of the enum
        assert _get_event_status_value(event) == EntityStatus.ACTIVE.value.lower()


class TestComputeEventStats:
    def test_empty_list(self):
        stats = _compute_event_stats([])
        assert stats == {"total": 0, "scheduled": 0, "today": 0}

    def test_counts_scheduled(self):
        events = [make_event("scheduled"), make_event("completed"), make_event("scheduled")]
        stats = _compute_event_stats(events)
        assert stats["scheduled"] == 2

    def test_counts_today(self):
        today = date.today()
        # Use a proper time object (not just a time value - the helper checks .date())
        today_dt = datetime.combine(today, time(10, 0))
        events = [
            make_event(start_time=today_dt),
            make_event(),  # no start_time
        ]
        stats = _compute_event_stats(events)
        assert stats["today"] == 1


class TestApplyEventFilters:
    def test_scheduled_filter(self):
        events = [make_event("scheduled"), make_event("completed"), make_event("cancelled")]
        result = _apply_event_filters(events, "scheduled")
        assert len(result) == 1

    def test_all_filter(self):
        events = [make_event("scheduled"), make_event("completed")]
        result = _apply_event_filters(events, "all")
        assert len(result) == 2

    def test_cancelled_filter(self):
        events = [make_event("scheduled"), make_event("cancelled")]
        result = _apply_event_filters(events, "cancelled")
        assert len(result) == 1


class TestApplyEventSort:
    def test_sort_by_title(self):
        events = [make_event(title="Zephyr"), make_event(title="Alpha")]
        result = _apply_event_sort(events, "title")
        assert result[0].title == "Alpha"

    def test_sort_by_created_at_descending(self):
        events = [
            make_event(created_at=datetime(2024, 1, 1)),
            make_event(created_at=datetime(2024, 12, 1)),
        ]
        result = _apply_event_sort(events, "created_at")
        assert result[0].created_at == datetime(2024, 12, 1)

    def test_sort_by_start_time(self):
        events = [
            make_event(event_date=date(2025, 6, 2)),
            make_event(event_date=date(2025, 6, 1)),
        ]
        result = _apply_event_sort(events, "start_time")
        assert result[0].event_date == date(2025, 6, 1)


# ============================================================================
# CHOICES
# ============================================================================


def make_choice(
    status: str = "pending",
    priority: str = "medium",
    decision_deadline: datetime | None = None,
    created_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        status=status,
        priority=priority,
        decision_deadline=decision_deadline,
        created_at=created_at or datetime(2024, 1, 1),
        title="choice",
    )


class TestGetChoiceEnumValue:
    def test_string_value(self):
        choice = make_choice(status="pending")
        assert _get_choice_enum_value(choice, "status") == "pending"

    def test_none_returns_default(self):
        choice = make_choice()
        choice.status = None
        assert _get_choice_enum_value(choice, "status", "unknown") == "unknown"

    def test_enum_value(self):
        choice = make_choice()
        choice.status = EntityStatus.ACTIVE
        assert _get_choice_enum_value(choice, "status") == EntityStatus.ACTIVE.value.lower()

    def test_missing_attr_returns_default(self):
        choice = SimpleNamespace()  # no 'status' attr
        assert _get_choice_enum_value(choice, "status", "fallback") == "fallback"


class TestComputeChoiceStats:
    def test_empty_list(self):
        stats = _compute_choice_stats([])
        assert stats == {"total": 0, "pending": 0, "decided": 0}

    def test_counts_pending_and_decided(self):
        choices = [
            make_choice("pending"),
            make_choice("pending"),
            make_choice("decided"),
            make_choice("implemented"),
        ]
        stats = _compute_choice_stats(choices)
        assert stats["total"] == 4
        assert stats["pending"] == 2
        assert stats["decided"] == 1


class TestApplyChoiceFilters:
    def test_pending_filter(self):
        choices = [make_choice("pending"), make_choice("decided"), make_choice("implemented")]
        result = _apply_choice_filters(choices, "pending")
        assert len(result) == 1
        assert result[0].status == "pending"

    def test_all_filter(self):
        choices = [make_choice("pending"), make_choice("decided")]
        result = _apply_choice_filters(choices, "all")
        assert len(result) == 2


class TestApplyChoiceSort:
    def test_sort_by_deadline(self):
        choices = [
            make_choice(decision_deadline=datetime(2025, 12, 31)),
            make_choice(decision_deadline=datetime(2025, 1, 1)),
        ]
        result = _apply_choice_sort(choices, "deadline")
        assert result[0].decision_deadline == datetime(2025, 1, 1)

    def test_sort_by_priority(self):
        choices = [make_choice(priority="low"), make_choice(priority="critical")]
        result = _apply_choice_sort(choices, "priority")
        assert result[0].priority == "critical"

    def test_sort_by_created_at_descending(self):
        choices = [
            make_choice(created_at=datetime(2024, 1, 1)),
            make_choice(created_at=datetime(2024, 12, 1)),
        ]
        result = _apply_choice_sort(choices, "created_at")
        assert result[0].created_at == datetime(2024, 12, 1)


# ============================================================================
# PRINCIPLES
# ============================================================================


def make_principle(
    strength: PrincipleStrength = PrincipleStrength.MODERATE,
    category: str = "personal",
    is_active: bool = True,
    title: str = "principle",
    created_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        strength=strength,
        category=category,
        is_active=is_active,
        title=title,
        created_at=created_at or datetime(2024, 1, 1),
    )


class TestGetPrincipleStrengthValue:
    def test_core_returns_5(self):
        p = make_principle(PrincipleStrength.CORE)
        assert _get_principle_strength_value(p) == 5

    def test_strong_returns_4(self):
        p = make_principle(PrincipleStrength.STRONG)
        assert _get_principle_strength_value(p) == 4

    def test_moderate_returns_3(self):
        p = make_principle(PrincipleStrength.MODERATE)
        assert _get_principle_strength_value(p) == 3

    def test_string_value_resolved(self):
        p = make_principle()
        p.strength = PrincipleStrength.CORE.value  # string like "core"
        assert _get_principle_strength_value(p) == 5

    def test_no_strength_defaults_to_3(self):
        p = SimpleNamespace()
        assert _get_principle_strength_value(p) == 3


class TestComputePrincipleStats:
    def test_empty_list(self):
        stats = _compute_principle_stats([])
        assert stats == {"total": 0, "core": 0, "active": 0}

    def test_counts_core_strength(self):
        principles = [
            make_principle(PrincipleStrength.CORE),
            make_principle(PrincipleStrength.MODERATE),
        ]
        stats = _compute_principle_stats(principles)
        assert stats["core"] == 1

    def test_counts_active(self):
        principles = [
            make_principle(is_active=True),
            make_principle(is_active=False),
            make_principle(is_active=True),
        ]
        stats = _compute_principle_stats(principles)
        assert stats["active"] == 2


class TestApplyPrincipleFilters:
    def test_category_filter(self):
        principles = [
            make_principle(category="personal"),
            make_principle(category="professional"),
        ]
        result = _apply_principle_filters(principles, category_filter="personal")
        assert len(result) == 1

    def test_strength_filter_core(self):
        principles = [
            make_principle(PrincipleStrength.CORE),
            make_principle(PrincipleStrength.MODERATE),
        ]
        result = _apply_principle_filters(principles, strength_filter="core")
        assert len(result) == 1
        assert result[0].strength == PrincipleStrength.CORE

    def test_strength_filter_developing(self):
        principles = [
            make_principle(PrincipleStrength.DEVELOPING),
            make_principle(PrincipleStrength.MODERATE),
            make_principle(PrincipleStrength.CORE),
        ]
        result = _apply_principle_filters(principles, strength_filter="developing")
        assert len(result) == 2  # DEVELOPING (2) and MODERATE (3)

    def test_all_filters_return_everything(self):
        principles = [
            make_principle(PrincipleStrength.CORE, "personal"),
            make_principle(PrincipleStrength.MODERATE, "professional"),
        ]
        result = _apply_principle_filters(principles, "all", "all")
        assert len(result) == 2

    def test_combined_category_and_strength_filter(self):
        principles = [
            make_principle(PrincipleStrength.CORE, "personal"),
            make_principle(PrincipleStrength.MODERATE, "personal"),
            make_principle(PrincipleStrength.CORE, "professional"),
        ]
        result = _apply_principle_filters(
            principles, category_filter="personal", strength_filter="core"
        )
        assert len(result) == 1


class TestApplyPrincipleSort:
    def test_sort_by_strength_descending(self):
        principles = [
            make_principle(PrincipleStrength.EXPLORING),
            make_principle(PrincipleStrength.CORE),
        ]
        result = _apply_principle_sort(principles, "strength")
        assert result[0].strength == PrincipleStrength.CORE

    def test_sort_by_title(self):
        principles = [make_principle(title="Zebra"), make_principle(title="Alpha")]
        result = _apply_principle_sort(principles, "title")
        assert result[0].title == "Alpha"

    def test_sort_by_created_at_descending(self):
        principles = [
            make_principle(created_at=datetime(2024, 1, 1)),
            make_principle(created_at=datetime(2024, 12, 1)),
        ]
        result = _apply_principle_sort(principles, "created_at")
        assert result[0].created_at == datetime(2024, 12, 1)

    def test_default_sorts_by_strength_descending(self):
        principles = [
            make_principle(PrincipleStrength.EXPLORING),
            make_principle(PrincipleStrength.STRONG),
        ]
        result = _apply_principle_sort(principles)
        assert result[0].strength == PrincipleStrength.STRONG
