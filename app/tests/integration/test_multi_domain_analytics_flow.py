"""
Integration Tests: Multi-Domain Analytics Flow
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
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.events.calendar_event_events import CalendarEventCompleted
from core.events.habit_events import HabitCompleted
from core.events.task_events import TaskCompleted
from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService

_PRODUCTIVITY_QUERY = """
MATCH (analytics:ProductivityAnalytics {user_uid: $user_uid})
RETURN analytics.first_completion_at AS first,
       analytics.last_completion_at AS last,
       analytics.tasks_completed AS retired_count
"""


async def _productivity(neo4j_driver, user_uid: str):
    async with neo4j_driver.session() as session:
        neo_result = await session.run(_PRODUCTIVITY_QUERY, user_uid=user_uid)
        return await neo_result.single()


def _naive(stamp) -> datetime:
    """A stored ZONED DATETIME, back to the naive local moment the event carried."""
    return stamp.to_native().replace(tzinfo=None)


@pytest.mark.asyncio
@pytest.mark.integration
class TestMultiDomainAnalyticsFlow:
    """
    Integration tests for Multi-Domain Analytics event-driven flow.

    Tests cover:
    - TaskCompleted → ProductivityAnalytics completion stamps (the node holds
      only first/last_completion_at; tasks_completed is derived at read and
      proven in test_completion_velocity_window.py)
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
        from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend

        executor = Neo4jQueryExecutor(neo4j_driver)
        backend = CrossDomainBackend(executor)
        return CrossDomainAnalyticsService(backend=backend)

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Test user UID for analytics."""
        return "user_analytics_test"

    # ========================================================================
    # TASK COMPLETION ANALYTICS TESTS
    # ========================================================================

    async def test_a_first_completion_stamps_first_and_last_and_nothing_else(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """The node is the two stamps. No count is written — ``tasks_completed``
        is derived at read, and a node that still carried it would be exactly
        the stored figure that drifted."""
        moment = datetime(2026, 8, 1, 9, 0)

        result = await analytics_service.handle_task_completed(
            TaskCompleted(task_uid="task.write_report", user_uid=test_user_uid, occurred_at=moment)
        )
        assert result.is_ok

        record = await _productivity(neo4j_driver, test_user_uid)
        assert record is not None
        assert _naive(record["first"]) == moment
        assert _naive(record["last"]) == moment
        assert record["retired_count"] is None, "the handler writes no count"

    async def test_later_completions_advance_last_and_keep_first(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        moments = [
            datetime(2026, 8, 1, 9, 0),
            datetime(2026, 8, 2, 9, 0),
            datetime(2026, 8, 3, 9, 0),
        ]
        for i, moment in enumerate(moments):
            result = await analytics_service.handle_task_completed(
                TaskCompleted(task_uid=f"task.task_{i}", user_uid=test_user_uid, occurred_at=moment)
            )
            assert result.is_ok

        record = await _productivity(neo4j_driver, test_user_uid)
        assert _naive(record["first"]) == moments[0], "first is written once and never moved"
        assert _naive(record["last"]) == moments[-1]

    async def test_a_repeat_complete_does_not_move_the_completion_stamps(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """A repeat is not a completion moment (Codex #1134 P2).

        The explicit-complete cascade re-runs on an already-completed task and
        publishes a *fresh* ``occurred_at`` with ``is_repeat=True``. Recording
        that would move "when did this user most recently complete something"
        forward on a click that completed nothing.
        """
        assert (
            await analytics_service.handle_task_completed(
                TaskCompleted(
                    task_uid="task.once",
                    user_uid=test_user_uid,
                    occurred_at=datetime(2026, 8, 1, 9, 0),
                )
            )
        ).is_ok
        before = await _productivity(neo4j_driver, test_user_uid)

        assert (
            await analytics_service.handle_task_completed(
                TaskCompleted(
                    task_uid="task.once",
                    user_uid=test_user_uid,
                    occurred_at=datetime(2026, 8, 20, 9, 0),
                    is_repeat=True,
                )
            )
        ).is_ok

        after = await _productivity(neo4j_driver, test_user_uid)
        assert after["last"] == before["last"], "a repeat complete is not a completion moment"
        assert after["first"] == before["first"]

    async def test_a_repeat_before_any_completion_creates_no_node(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """The handler is gated whole: with no count to recompute, a repeat has
        no business reaching the graph, so it does not even upsert the node."""
        result = await analytics_service.handle_task_completed(
            TaskCompleted(
                task_uid="task.repeat_only",
                user_uid=test_user_uid,
                occurred_at=datetime.now(),
                is_repeat=True,
            )
        )
        assert result.is_ok

        assert await _productivity(neo4j_driver, test_user_uid) is None

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
        RETURN productivity.last_completion_at IS NOT NULL as tasks_stamped,
               habits.total_completions as habits,
               events.events_attended as events
        """
        async with neo4j_driver.session() as session:
            neo_result = await session.run(query, user_uid=test_user_uid)
            record = await neo_result.single()

        assert record is not None
        assert record["tasks_stamped"] is True
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
