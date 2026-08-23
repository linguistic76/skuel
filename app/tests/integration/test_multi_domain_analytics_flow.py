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
from core.events.task_events import TaskCompleted, TaskReopened
from core.models.enums.entity_enums import EntityStatus
from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService

_PRODUCTIVITY_QUERY = """
MATCH (analytics:ProductivityAnalytics {user_uid: $user_uid})
RETURN analytics.tasks_completed AS count,
       analytics.first_completion_at AS first,
       analytics.last_completion_at AS last
"""


async def _seed_task(neo4j_driver, user_uid: str, task_uid: str, status: EntityStatus) -> None:
    """Own a Task off the user — the shape the recompute counts.

    ``tasks_completed`` is derived from ``(:User)-[:OWNS]->(:Task)`` (ADR-086),
    so these tests have to put real rows in the graph rather than trusting the
    event to carry the number.
    """
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            MERGE (t:Entity:Task {uid: $task_uid})
            SET t.user_uid = $user_uid,
                t.entity_type = 'task',
                t.title = $task_uid,
                t.status = $status
            MERGE (u)-[:OWNS]->(t)
            """,
            user_uid=user_uid,
            task_uid=task_uid,
            status=status.value,
        )
        await result.consume()


async def _set_task_status(neo4j_driver, task_uid: str, status: EntityStatus) -> None:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (t:Task {uid: $task_uid}) SET t.status = $status",
            task_uid=task_uid,
            status=status.value,
        )
        await result.consume()


async def _productivity(neo4j_driver, user_uid: str):
    async with neo4j_driver.session() as session:
        neo_result = await session.run(_PRODUCTIVITY_QUERY, user_uid=user_uid)
        return await neo_result.single()


@pytest.mark.asyncio
@pytest.mark.integration
class TestMultiDomainAnalyticsFlow:
    """
    Integration tests for Multi-Domain Analytics event-driven flow.

    Tests cover:
    - TaskCompleted → Productivity analytics (recomputed from the graph, so the
      seeded (:User)-[:OWNS]->(:Task) rows are what the number comes from)
    - TaskReopened → the same recompute, without moving the completion stamps
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

    async def test_task_completed_tracked(self, analytics_service, neo4j_driver, test_user_uid):
        """Test that TaskCompleted event is tracked in analytics."""
        await _seed_task(neo4j_driver, test_user_uid, "task.write_report", EntityStatus.COMPLETED)

        event = TaskCompleted(
            task_uid="task.write_report",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )

        result = await analytics_service.handle_task_completed(event)
        assert result.is_ok

        record = await _productivity(neo4j_driver, test_user_uid)
        assert record is not None
        assert record["count"] == 1

    async def test_multiple_task_completions_aggregated(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """Test that multiple task completions are aggregated correctly."""
        for i in range(3):
            await _seed_task(neo4j_driver, test_user_uid, f"task.task_{i}", EntityStatus.COMPLETED)
            event = TaskCompleted(
                task_uid=f"task.task_{i}",
                user_uid=test_user_uid,
                occurred_at=datetime.now(),
            )
            result = await analytics_service.handle_task_completed(event)
            assert result.is_ok

        record = await _productivity(neo4j_driver, test_user_uid)
        assert record["count"] == 3

    async def test_open_tasks_are_not_counted(self, analytics_service, neo4j_driver, test_user_uid):
        """``tasks_completed`` means *currently* completed, so an open task the
        user also owns must not land in the number."""
        await _seed_task(neo4j_driver, test_user_uid, "task.done", EntityStatus.COMPLETED)
        await _seed_task(neo4j_driver, test_user_uid, "task.open", EntityStatus.ACTIVE)

        await analytics_service.handle_task_completed(
            TaskCompleted(task_uid="task.done", user_uid=test_user_uid, occurred_at=datetime.now())
        )

        record = await _productivity(neo4j_driver, test_user_uid)
        assert record["count"] == 1

    async def test_another_users_tasks_are_not_counted(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """The count is scoped by the ``:OWNS`` edge (ADR-086), not by label."""
        await _seed_task(neo4j_driver, test_user_uid, "task.mine", EntityStatus.COMPLETED)
        await _seed_task(neo4j_driver, "user_other", "task.theirs", EntityStatus.COMPLETED)

        await analytics_service.handle_task_completed(
            TaskCompleted(task_uid="task.mine", user_uid=test_user_uid, occurred_at=datetime.now())
        )

        record = await _productivity(neo4j_driver, test_user_uid)
        assert record["count"] == 1

    async def test_a_repeat_complete_does_not_inflate_the_count(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """The reason the ``is_repeat`` gate could come off this subscriber.

        Both explicit-complete doors re-run the cascade on an already-completed
        task (the repair path), so the handler is called again with
        ``is_repeat=True``. A recompute converges; the increment it replaced
        would have read 2.
        """
        await _seed_task(neo4j_driver, test_user_uid, "task.once", EntityStatus.COMPLETED)
        event = TaskCompleted(
            task_uid="task.once", user_uid=test_user_uid, occurred_at=datetime.now()
        )
        repeat = TaskCompleted(
            task_uid="task.once",
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
            is_repeat=True,
        )

        assert (await analytics_service.handle_task_completed(event)).is_ok
        assert (await analytics_service.handle_task_completed(repeat)).is_ok

        record = await _productivity(neo4j_driver, test_user_uid)
        assert record["count"] == 1

    async def test_a_reopen_lowers_the_count_without_moving_the_stamps(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """A reopen recomputes and nothing else.

        ``last_completion_at`` is the endpoint of the velocity denominator, and
        a reopen is not a completion — moving it would silently stretch the
        window while looking like bookkeeping.
        """
        for uid in ("task.a", "task.b"):
            await _seed_task(neo4j_driver, test_user_uid, uid, EntityStatus.COMPLETED)
            assert (
                await analytics_service.handle_task_completed(
                    TaskCompleted(task_uid=uid, user_uid=test_user_uid, occurred_at=datetime.now())
                )
            ).is_ok

        before = await _productivity(neo4j_driver, test_user_uid)
        assert before["count"] == 2

        await _set_task_status(neo4j_driver, "task.b", EntityStatus.ACTIVE)
        result = await analytics_service.handle_task_reopened(
            TaskReopened(task_uid="task.b", user_uid=test_user_uid)
        )
        assert result.is_ok

        after = await _productivity(neo4j_driver, test_user_uid)
        assert after["count"] == 1, "a reopen must be able to lower the count"
        assert after["last"] == before["last"], "a reopen is not a completion"
        assert after["first"] == before["first"]

    async def test_a_reopen_before_any_completion_records_no_stamps(
        self, analytics_service, neo4j_driver, test_user_uid
    ):
        """The node is still upserted, but a reopen never establishes a first
        completion moment out of thin air."""
        await _seed_task(neo4j_driver, test_user_uid, "task.open", EntityStatus.ACTIVE)

        result = await analytics_service.handle_task_reopened(
            TaskReopened(task_uid="task.open", user_uid=test_user_uid)
        )
        assert result.is_ok

        record = await _productivity(neo4j_driver, test_user_uid)
        assert record["count"] == 0
        assert record["first"] is None
        assert record["last"] is None

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
        await _seed_task(neo4j_driver, test_user_uid, "task.test", EntityStatus.COMPLETED)
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
        await _seed_task(neo4j_driver, test_user_uid, "task.first", EntityStatus.COMPLETED)
        first_at = datetime(2026, 8, 1, 9, 0)
        first_event = TaskCompleted(
            task_uid="task.first",
            user_uid=test_user_uid,
            occurred_at=first_at,
        )
        await analytics_service.handle_task_completed(first_event)

        # Complete second task
        await _seed_task(neo4j_driver, test_user_uid, "task.second", EntityStatus.COMPLETED)
        second_event = TaskCompleted(
            task_uid="task.second",
            user_uid=test_user_uid,
            occurred_at=datetime(2026, 8, 8, 9, 0),
        )
        await analytics_service.handle_task_completed(second_event)

        record = await _productivity(neo4j_driver, test_user_uid)

        assert record["first"] is not None
        assert record["last"] is not None
        # first_completion_at is pinned to the FIRST completion, not re-stamped:
        # the recompute uses coalesce where the increment used ON CREATE SET.
        assert record["first"].year == first_at.year
        assert record["first"].month == first_at.month
        assert record["first"].day == first_at.day
        assert record["last"] > record["first"]
