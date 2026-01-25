"""
Integration Tests: Multi-Domain Analytics Flow (Phase 4)
==========================================================

Tests the complete event-driven analytics flow:
1. Activity events published from multiple domains (Tasks, Habits, Events, etc.)
2. CrossDomainAnalyticsService subscribes to events
3. Analytics data aggregated in Neo4j
4. Cross-domain insights generated

Version: 1.0.0
Date: 2025-11-05
"""

from datetime import date, datetime

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from core.events.calendar_event_events import CalendarEventCompleted
from core.events.habit_events import HabitCompleted
from core.events.task_events import TaskCompleted
from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService


@pytest.mark.asyncio
@pytest.mark.integration
class TestMultiDomainAnalyticsFlow:
    """
    Integration tests for Multi-Domain Analytics event-driven flow.

    Tests cover:
    - TaskCompleted → Productivity analytics
    - HabitCompleted → Consistency analytics
    - CalendarEventCompleted → Engagement analytics
    - Cross-domain data aggregation
    - Analytics persistence in Neo4j
    """

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus for capturing published events."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def analytics_service(self, neo4j_driver, clean_neo4j):
        """Create CrossDomainAnalyticsService with clean database."""
        return CrossDomainAnalyticsService(driver=neo4j_driver)

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Test user UID for analytics."""
        return "user.analytics_test"

    # ========================================================================
    # TASK COMPLETION ANALYTICS TESTS
    # ========================================================================

    async def test_task_completed_tracked(self, analytics_service, neo4j_driver, test_user_uid):
        """Test that TaskCompleted event is tracked in analytics."""
        # Publish TaskCompleted event
        event = TaskCompleted(
            task_uid="task.write_report",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )

        # Handle event
        result = await analytics_service.handle_task_completed(event)
        assert result.is_ok

        # Verify analytics node created in Neo4j
        query = """
        MATCH (analytics:ProductivityAnalytics {user_uid: $user_uid})
        RETURN analytics.tasks_completed as count
        """
        async with neo4j_driver.session() as session:
            neo_result = await session.run(query, user_uid=test_user_uid)
            record = await neo_result.single()

        assert record is not None
        assert record["count"] == 1

    async def test_multiple_task_completions_aggregated(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """Test that multiple task completions are aggregated correctly."""
        # Complete 3 tasks
        for i in range(3):
            event = TaskCompleted(
                task_uid=f"task.task_{i}",
                user_uid=test_user_uid,
                occurred_at=datetime.now(),
            )
            result = await analytics_service.handle_task_completed(event)
            assert result.is_ok

        # Verify count aggregated correctly
        query = """
        MATCH (analytics:ProductivityAnalytics {user_uid: $user_uid})
        RETURN analytics.tasks_completed as count
        """
        async with neo4j_driver.session() as session:
            neo_result = await session.run(query, user_uid=test_user_uid)
            record = await neo_result.single()

        assert record["count"] == 3

    # ========================================================================
    # HABIT COMPLETION ANALYTICS TESTS
    # ========================================================================

    async def test_habit_completed_tracked(self, analytics_service, neo4j_driver, test_user_uid):
        """Test that HabitCompleted event is tracked in analytics."""
        # Publish HabitCompleted event
        event = HabitCompleted(
            habit_uid="habit.daily_meditation",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
            current_streak=5,
        )

        # Handle event
        result = await analytics_service.handle_habit_completed(event)
        assert result.is_ok

        # Verify analytics node created
        query = """
        MATCH (analytics:HabitAnalytics {user_uid: $user_uid})
        RETURN analytics.total_completions as count
        """
        async with neo4j_driver.session() as session:
            neo_result = await session.run(query, user_uid=test_user_uid)
            record = await neo_result.single()

        assert record is not None
        assert record["count"] == 1

    async def test_habit_consistency_tracking(self, analytics_service, neo4j_driver, test_user_uid):
        """Test that habit completions track consistency."""
        # Complete habit 5 times
        for i in range(5):
            event = HabitCompleted(
                habit_uid="habit.exercise",
                user_uid=test_user_uid,
                occurred_at=datetime.now(),
                current_streak=i + 1,
            )
            result = await analytics_service.handle_habit_completed(event)
            assert result.is_ok

        # Verify consistency tracked
        query = """
        MATCH (analytics:HabitAnalytics {user_uid: $user_uid})
        RETURN analytics.total_completions as count,
               analytics.first_completion_at as first,
               analytics.last_completion_at as last
        """
        async with neo4j_driver.session() as session:
            neo_result = await session.run(query, user_uid=test_user_uid)
            record = await neo_result.single()

        assert record["count"] == 5
        assert record["first"] is not None
        assert record["last"] is not None

    # ========================================================================
    # EVENT COMPLETION ANALYTICS TESTS
    # ========================================================================

    async def test_event_completed_tracked(self, analytics_service, neo4j_driver, test_user_uid):
        """Test that CalendarEventCompleted is tracked in analytics."""
        # Publish CalendarEventCompleted event
        event = CalendarEventCompleted(
            event_uid="event.team_meeting",
            user_uid=test_user_uid,
            completion_date=date.today(),
            quality_score=4,
            occurred_at=datetime.now(),
        )

        # Handle event
        result = await analytics_service.handle_event_completed(event)
        assert result.is_ok

        # Verify analytics node created
        query = """
        MATCH (analytics:EventAnalytics {user_uid: $user_uid})
        RETURN analytics.events_attended as count
        """
        async with neo4j_driver.session() as session:
            neo_result = await session.run(query, user_uid=test_user_uid)
            record = await neo_result.single()

        assert record is not None
        assert record["count"] == 1

    # ========================================================================
    # CROSS-DOMAIN ANALYTICS TESTS
    # ========================================================================

    async def test_cross_domain_activity_tracked(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """Test that activity across multiple domains is tracked."""
        # Complete task
        task_event = TaskCompleted(
            task_uid="task.test",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await analytics_service.handle_task_completed(task_event)

        # Complete habit
        habit_event = HabitCompleted(
            habit_uid="habit.test",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
            current_streak=1,
        )
        await analytics_service.handle_habit_completed(habit_event)

        # Complete event
        event_event = CalendarEventCompleted(
            event_uid="event.test",
            user_uid=test_user_uid,
            completion_date=date.today(),
            quality_score=4,
            occurred_at=datetime.now(),
        )
        await analytics_service.handle_event_completed(event_event)

        # Verify all three analytics nodes exist
        query = """
        MATCH (productivity:ProductivityAnalytics {user_uid: $user_uid})
        MATCH (habits:HabitAnalytics {user_uid: $user_uid})
        MATCH (events:EventAnalytics {user_uid: $user_uid})
        RETURN productivity.tasks_completed as tasks,
               habits.total_completions as habits,
               events.events_attended as events
        """
        async with neo4j_driver.session() as session:
            neo_result = await session.run(query, user_uid=test_user_uid)
            record = await neo_result.single()

        assert record is not None
        assert record["tasks"] == 1
        assert record["habits"] == 1
        assert record["events"] == 1

    # ========================================================================
    # ERROR HANDLING TESTS
    # ========================================================================

    async def test_error_handling_task_completion(self, analytics_service, test_user_uid):
        """Test error handling in task completion handler."""
        # Create event with minimal data
        event = TaskCompleted(
            task_uid="task.test",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )

        # Should not raise error
        result = await analytics_service.handle_task_completed(event)
        assert result.is_ok

    async def test_error_handling_habit_completion(self, analytics_service, test_user_uid):
        """Test error handling in habit completion handler."""
        event = HabitCompleted(
            habit_uid="habit.test",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
            current_streak=1,
        )

        # Should not raise error
        result = await analytics_service.handle_habit_completed(event)
        assert result.is_ok

    async def test_error_handling_event_completion(self, analytics_service, test_user_uid):
        """Test error handling in event completion handler."""
        event = CalendarEventCompleted(
            event_uid="event.test",
            user_uid=test_user_uid,
            completion_date=date.today(),
            quality_score=4,
            occurred_at=datetime.now(),
        )

        # Should not raise error
        result = await analytics_service.handle_event_completed(event)
        assert result.is_ok

    # ========================================================================
    # ANALYTICS NODE TIMESTAMPS TESTS
    # ========================================================================

    async def test_timestamps_tracked_correctly(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """Test that first and last timestamps are tracked correctly."""
        # Complete first task
        first_event = TaskCompleted(
            task_uid="task.first",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await analytics_service.handle_task_completed(first_event)

        # Complete second task
        second_event = TaskCompleted(
            task_uid="task.second",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await analytics_service.handle_task_completed(second_event)

        # Verify both timestamps exist
        query = """
        MATCH (analytics:ProductivityAnalytics {user_uid: $user_uid})
        RETURN analytics.first_completion_at as first,
               analytics.last_completion_at as last
        """
        async with neo4j_driver.session() as session:
            neo_result = await session.run(query, user_uid=test_user_uid)
            record = await neo_result.single()

        assert record["first"] is not None
        assert record["last"] is not None
