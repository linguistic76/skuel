"""
Integration Test: Event-Driven Architecture Flow
==================================================

Tests the complete event flow from publisher to subscriber.

Tests:
1. TasksService publishes TaskCreated/TaskCompleted events
2. GoalsService publishes GoalCreated/GoalAchieved/etc. events
3. HabitsService publishes HabitCreated/HabitCompleted/etc. events
4. Event bus routes events to subscribers
5. Subscribers receive and process events correctly
"""

from datetime import datetime
from typing import Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from core.events import (
    GoalAchieved,
    GoalCreated,
    HabitCompleted,
    HabitCreated,
    TaskCompleted,
    TaskCreated,
)


class TestEventFlowIntegration:
    """Integration tests for event-driven architecture."""

    @pytest.fixture
    def event_bus(self) -> InMemoryEventBus:
        """Create event bus with history capture."""
        return InMemoryEventBus(capture_history=True)

    @pytest.fixture
    def event_counter(self) -> dict[str, Any]:
        """Create event counter for testing subscribers."""
        return {"count": 0, "events": []}

    # ========================================================================
    # TASK EVENTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_task_created_event_flow(self, event_bus, event_counter):
        """Test TaskCreated event publishing and subscription."""

        # Setup subscriber
        async def task_event_handler(event):
            event_counter["count"] += 1
            event_counter["events"].append(event)

        event_bus.subscribe(TaskCreated, task_event_handler)

        # Publish event
        event = TaskCreated(
            task_uid="task-123",
            user_uid="user-456",
            title="Test task",
            priority="high",
            domain="tech",
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        # Verify event was received
        assert event_counter["count"] == 1
        assert len(event_counter["events"]) == 1
        assert isinstance(event_counter["events"][0], TaskCreated)
        assert event_counter["events"][0].task_uid == "task-123"

    @pytest.mark.asyncio
    async def test_task_completed_event_flow(self, event_bus, event_counter):
        """Test TaskCompleted event publishing and subscription."""

        # Setup subscriber
        async def task_event_handler(event):
            event_counter["count"] += 1
            event_counter["events"].append(event)

        event_bus.subscribe(TaskCompleted, task_event_handler)

        # Publish event
        event = TaskCompleted(
            task_uid="task-123",
            user_uid="user-456",
            occurred_at=datetime.now(),
            completion_time_seconds=120,
            was_overdue=False,
        )
        await event_bus.publish_async(event)

        # Verify event was received
        assert event_counter["count"] == 1
        assert len(event_counter["events"]) == 1
        assert isinstance(event_counter["events"][0], TaskCompleted)
        assert event_counter["events"][0].completion_time_seconds == 120

    # ========================================================================
    # GOAL EVENTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_goal_created_event_flow(self, event_bus, event_counter):
        """Test GoalCreated event publishing and subscription."""

        # Setup subscriber
        async def goal_event_handler(event):
            event_counter["count"] += 1
            event_counter["events"].append(event)

        event_bus.subscribe(GoalCreated, goal_event_handler)

        # Publish event
        event = GoalCreated(
            goal_uid="goal-123",
            user_uid="user-456",
            title="Complete Python course",
            domain="tech",
            target_date=datetime(2025, 12, 31, 23, 59),
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        # Verify event was received
        assert event_counter["count"] == 1
        assert len(event_counter["events"]) == 1
        assert isinstance(event_counter["events"][0], GoalCreated)
        assert event_counter["events"][0].title == "Complete Python course"

    @pytest.mark.asyncio
    async def test_goal_achieved_event_flow(self, event_bus, event_counter):
        """Test GoalAchieved event publishing and subscription."""

        # Setup subscriber
        async def goal_event_handler(event):
            event_counter["count"] += 1
            event_counter["events"].append(event)

        event_bus.subscribe(GoalAchieved, goal_event_handler)

        # Publish event
        event = GoalAchieved(
            goal_uid="goal-123",
            user_uid="user-456",
            occurred_at=datetime.now(),
            actual_duration_days=180,
            completed_ahead_of_schedule=True,
        )
        await event_bus.publish_async(event)

        # Verify event was received
        assert event_counter["count"] == 1
        assert len(event_counter["events"]) == 1
        assert isinstance(event_counter["events"][0], GoalAchieved)
        assert event_counter["events"][0].actual_duration_days == 180

    # ========================================================================
    # HABIT EVENTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_habit_created_event_flow(self, event_bus, event_counter):
        """Test HabitCreated event publishing and subscription."""

        # Setup subscriber
        async def habit_event_handler(event):
            event_counter["count"] += 1
            event_counter["events"].append(event)

        event_bus.subscribe(HabitCreated, habit_event_handler)

        # Publish event
        event = HabitCreated(
            habit_uid="habit-123",
            user_uid="user-456",
            title="Morning meditation",
            frequency="daily",
            domain="personal",
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        # Verify event was received
        assert event_counter["count"] == 1
        assert len(event_counter["events"]) == 1
        assert isinstance(event_counter["events"][0], HabitCreated)
        assert event_counter["events"][0].title == "Morning meditation"

    @pytest.mark.asyncio
    async def test_habit_completed_event_flow(self, event_bus, event_counter):
        """Test HabitCompleted event publishing and subscription."""

        # Setup subscriber
        async def habit_event_handler(event):
            event_counter["count"] += 1
            event_counter["events"].append(event)

        event_bus.subscribe(HabitCompleted, habit_event_handler)

        # Publish event
        event = HabitCompleted(
            habit_uid="habit-123",
            user_uid="user-456",
            occurred_at=datetime.now(),
            current_streak=7,
            is_new_streak_record=False,
        )
        await event_bus.publish_async(event)

        # Verify event was received
        assert event_counter["count"] == 1
        assert len(event_counter["events"]) == 1
        assert isinstance(event_counter["events"][0], HabitCompleted)
        assert event_counter["events"][0].current_streak == 7

    # ========================================================================
    # MULTIPLE SUBSCRIBERS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_multiple_subscribers_receive_same_event(self, event_bus):
        """Test that multiple subscribers receive the same event."""
        counter1 = {"count": 0}
        counter2 = {"count": 0}
        counter3 = {"count": 0}

        async def handler1(event):
            counter1["count"] += 1

        async def handler2(event):
            counter2["count"] += 1

        async def handler3(event):
            counter3["count"] += 1

        # Subscribe all three handlers
        event_bus.subscribe(TaskCreated, handler1)
        event_bus.subscribe(TaskCreated, handler2)
        event_bus.subscribe(TaskCreated, handler3)

        # Publish one event
        event = TaskCreated(
            task_uid="task-123",
            user_uid="user-456",
            title="Test",
            priority="high",
            domain="tech",
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        # All three should have received it
        assert counter1["count"] == 1
        assert counter2["count"] == 1
        assert counter3["count"] == 1

    @pytest.mark.asyncio
    async def test_event_history_capture(self, event_bus):
        """Test event bus captures event history."""
        # Publish multiple events
        await event_bus.publish_async(
            TaskCreated(
                task_uid="task-1",
                user_uid="user-1",
                title="Task 1",
                priority="high",
                domain="tech",
                occurred_at=datetime.now(),
            )
        )

        await event_bus.publish_async(
            GoalCreated(
                goal_uid="goal-1",
                user_uid="user-1",
                title="Goal 1",
                domain="tech",
                target_date=None,
                occurred_at=datetime.now(),
            )
        )

        await event_bus.publish_async(
            HabitCreated(
                habit_uid="habit-1",
                user_uid="user-1",
                title="Habit 1",
                frequency="daily",
                domain="personal",
                occurred_at=datetime.now(),
            )
        )

        # Verify history
        history = event_bus.get_event_history()
        assert len(history) == 3
        assert isinstance(history[0], TaskCreated)
        assert isinstance(history[1], GoalCreated)
        assert isinstance(history[2], HabitCreated)

    # ========================================================================
    # ERROR HANDLING
    # ========================================================================

    @pytest.mark.asyncio
    async def test_subscriber_error_does_not_stop_other_subscribers(self, event_bus):
        """Test that one subscriber error doesn't prevent others from receiving event."""
        counter2 = {"count": 0}

        async def failing_handler(event):
            raise ValueError("Intentional error")

        async def working_handler(event):
            counter2["count"] += 1

        # Subscribe both handlers (failing first)
        event_bus.subscribe(TaskCreated, failing_handler)
        event_bus.subscribe(TaskCreated, working_handler)

        # Publish event
        event = TaskCreated(
            task_uid="task-123",
            user_uid="user-456",
            title="Test",
            priority="high",
            domain="tech",
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        # Working handler should still receive event
        assert counter2["count"] == 1
