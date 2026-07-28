"""
Tests for Calendar Converters
==============================

Tests pure helper functions and domain-specific converters.
Uses SimpleNamespace for mock entities.
"""

from datetime import date, time, timedelta
from types import SimpleNamespace

from core.models.enums import Priority
from ui.calendar.converters import (
    _make_calendar_uid,
    _normalize_priority,
    event_to_calendar_item,
    get_priority_calendar_color,
    goal_to_calendar_item,
    habit_to_calendar_items,
    task_to_calendar_item,
)
from ui.palette import EventTypeColor, FrequencyColor

# ============================================================================
# _normalize_priority
# ============================================================================


class TestNormalizePriority:
    def test_none_returns_default(self) -> None:
        assert _normalize_priority(None) == Priority.MEDIUM

    def test_none_returns_custom_default(self) -> None:
        assert _normalize_priority(None, Priority.HIGH) == Priority.HIGH

    def test_enum_passthrough(self) -> None:
        assert _normalize_priority(Priority.HIGH) == Priority.HIGH

    def test_valid_string(self) -> None:
        assert _normalize_priority("high") == Priority.HIGH

    def test_invalid_string_returns_default(self) -> None:
        assert _normalize_priority("super_urgent") == Priority.MEDIUM


# ============================================================================
# get_priority_calendar_color
# ============================================================================


class TestGetPriorityCalendarColor:
    def test_enum_input(self) -> None:
        result = get_priority_calendar_color(Priority.HIGH)
        assert isinstance(result, str)
        assert result.startswith("#")

    def test_string_input(self) -> None:
        result = get_priority_calendar_color("low")
        assert isinstance(result, str)
        assert result.startswith("#")

    def test_none_input(self) -> None:
        result = get_priority_calendar_color(None)
        assert isinstance(result, str)
        assert result.startswith("#")


# ============================================================================
# _make_calendar_uid
# ============================================================================


class TestMakeCalendarUid:
    def test_without_suffix(self) -> None:
        result = _make_calendar_uid("task", "task_abc_123")
        assert result == "task-task_abc_123"

    def test_with_suffix(self) -> None:
        result = _make_calendar_uid("habit", "habit_xyz", "2026-03-19")
        assert result == "habit-habit_xyz-2026-03-19"

    def test_none_suffix(self) -> None:
        result = _make_calendar_uid("event", "event_1", None)
        assert result == "event-event_1"


# ============================================================================
# task_to_calendar_item
# ============================================================================


class TestTaskToCalendarItem:
    def test_with_due_date(self) -> None:
        task = SimpleNamespace(
            uid="task_test_1",
            title="Fix bug",
            due_date=date(2026, 3, 20),
            scheduled_date=None,
            duration_minutes=90,
            priority=Priority.HIGH,
            description="Fix the bug",
            tags=["urgent"],
            project="backend",
            status="active",
            assignee=None,
        )
        item = task_to_calendar_item(task)
        assert item.source_uid == "task_test_1"
        assert item.title == "Fix bug"
        assert item.all_day is True
        assert "task" in item.uid

    def test_without_due_date(self) -> None:
        task = SimpleNamespace(
            uid="task_test_2",
            title="Plan sprint",
            duration_minutes=60,
            priority="medium",
            description="",
            tags=[],
            status="active",
        )
        item = task_to_calendar_item(task)
        assert item.source_uid == "task_test_2"
        # Should default to today when no due_date

    def test_default_duration(self) -> None:
        task = SimpleNamespace(
            uid="task_test_3",
            title="Quick task",
            due_date=date(2026, 3, 20),
            duration_minutes=None,
            priority=None,
            description=None,
            tags=None,
            status=None,
            assignee=None,
        )
        item = task_to_calendar_item(task)
        # Default duration should be 60 minutes
        diff = item.end_time - item.start_time
        assert diff == timedelta(minutes=60)


# ============================================================================
# goal_to_calendar_item
# ============================================================================


class TestGoalToCalendarItem:
    def test_with_target_date(self) -> None:
        goal = SimpleNamespace(
            uid="goal_test_1",
            title="Learn Neo4j",
            target_date=date(2026, 6, 1),
            priority=Priority.HIGH,
            description="Master graph databases",
            tags=["learning"],
            domain=None,
            status="active",
            timeframe="quarterly",
            progress_percentage=0.0,
        )
        item = goal_to_calendar_item(goal)
        assert item is not None
        assert item.source_uid == "goal_test_1"
        assert item.all_day is True
        assert item.metadata["progress"] == 0.0

    def test_with_string_target_date(self) -> None:
        goal = SimpleNamespace(
            uid="goal_test_2",
            title="Ship feature",
            target_date="2026-04-01",
            priority="medium",
            description="",
            tags=[],
            domain=None,
            status="active",
            timeframe="monthly",
            progress_percentage=50.0,
        )
        item = goal_to_calendar_item(goal)
        assert item is not None
        # The percent, not current_value — that field holds domain units.
        assert item.metadata["progress"] == 50.0

    def test_without_target_date_returns_none(self) -> None:
        goal = SimpleNamespace(
            uid="goal_test_3",
            title="Vague goal",
            target_date=None,
            priority="low",
        )
        item = goal_to_calendar_item(goal)
        assert item is None

    def test_invalid_date_string_returns_none(self) -> None:
        goal = SimpleNamespace(
            uid="goal_test_4",
            title="Bad date",
            target_date="not-a-date",
            priority="low",
        )
        item = goal_to_calendar_item(goal)
        assert item is None


# ============================================================================
# event_to_calendar_item
# ============================================================================


class TestEventToCalendarItem:
    def test_known_event_type(self) -> None:
        event = SimpleNamespace(
            uid="event_test_1",
            title="Team meeting",
            event_date=date(2026, 3, 20),
            start_time=time(14, 0),
            end_time=time(15, 0),
            event_type="meeting",
            description="Weekly sync",
            priority="medium",
            tags=["work"],
            location="Room 101",
            status="active",
        )
        item = event_to_calendar_item(event)
        assert item.source_uid == "event_test_1"
        assert item.all_day is False
        assert item.color == EventTypeColor.MEETING

    def test_unknown_event_type(self) -> None:
        event = SimpleNamespace(
            uid="event_test_2",
            title="Random event",
            event_date=date(2026, 3, 20),
            start_time=time(10, 0),
            end_time=time(11, 0),
            event_type="unknown_type",
            description="",
            priority="low",
            tags=[],
            location="",
            status="active",
        )
        item = event_to_calendar_item(event)
        assert item.color == "#3b82f6"  # Default blue


# ============================================================================
# habit_to_calendar_items
# ============================================================================


class TestHabitToCalendarItems:
    def test_daily_frequency(self) -> None:
        habit = SimpleNamespace(
            uid="habit_test_1",
            name="Morning run",
            recurrence_pattern="daily",
            duration_minutes=30,
            description="Run 5k",
            tags=["fitness"],
            habit_category=None,
            current_streak=5,
        )
        current = date(2026, 3, 15)
        items = habit_to_calendar_items(habit, current)
        # Should generate one item per day of the month
        assert len(items) == 31  # March has 31 days
        assert all(i.source_uid == "habit_test_1" for i in items)
        assert items[0].color == FrequencyColor.DAILY

    def test_weekly_frequency(self) -> None:
        habit = SimpleNamespace(
            uid="habit_test_2",
            name="Weekly review",
            recurrence_pattern="weekly",
            duration_minutes=60,
            description="",
            tags=[],
            habit_category=None,
            current_streak=0,
        )
        current = date(2026, 3, 15)
        items = habit_to_calendar_items(habit, current)
        # Mondays in March 2026: 2, 9, 16, 23, 30
        assert len(items) == 5
        assert items[0].color == FrequencyColor.WEEKLY

    def test_monthly_frequency(self) -> None:
        habit = SimpleNamespace(
            uid="habit_test_3",
            name="Monthly budget",
            recurrence_pattern="monthly",
            duration_minutes=45,
            description="Review budget",
            tags=["finance"],
            habit_category=None,
            current_streak=12,
        )
        current = date(2026, 3, 15)
        items = habit_to_calendar_items(habit, current)
        assert len(items) == 1  # Only 1st of month

    def test_default_frequency(self) -> None:
        habit = SimpleNamespace(
            uid="habit_test_4",
            name="Default habit",
            recurrence_pattern=None,
            duration_minutes=15,
            description="",
            tags=None,
            habit_category=None,
            current_streak=0,
        )
        current = date(2026, 3, 15)
        items = habit_to_calendar_items(habit, current)
        # Default is daily
        assert len(items) == 31

    def test_duration_default(self) -> None:
        habit = SimpleNamespace(
            uid="habit_test_5",
            name="Quick habit",
            recurrence_pattern="monthly",
            duration_minutes=None,
            description="",
            tags=None,
            habit_category=None,
            current_streak=0,
        )
        current = date(2026, 3, 15)
        items = habit_to_calendar_items(habit, current)
        assert len(items) == 1
        diff = items[0].end_time - items[0].start_time
        assert diff == timedelta(minutes=15)  # Default 15 minutes
