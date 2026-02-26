"""
Integration Test: User-Entity Relationship Tracking
====================================================

Verify that user-entity relationships are created and queried correctly
across all domains.

Tests -4 implementation of user-entity tracking:





This test suite verifies:
1. Auto-relationship creation on entity creation
2. User-specific entity filtering via graph traversal
3. Cross-domain statistics aggregation
4. User isolation (no cross-user data leakage)
5. Profile hub data completeness
"""

from datetime import datetime, timedelta

import pytest

from core.models.enums import Domain, EntityStatus, Priority, RecurrencePattern
from core.models.enums.entity_enums import EntityStatus as HabitStatus
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.task.task import Task as Task

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def test_user_uid() -> str:
    """Test user UID."""
    return "user_test_123"


@pytest.fixture
def test_user_uid_2() -> str:
    """Second test user UID for isolation testing."""
    return "user_test_456"


@pytest.fixture
async def clean_test_data(
    tasks_backend, events_backend, habits_backend, goals_backend, test_user_uid, test_user_uid_2
):
    """Clean up test data before and after tests."""
    # Cleanup before test
    await _cleanup_user_data(tasks_backend, test_user_uid)
    await _cleanup_user_data(tasks_backend, test_user_uid_2)
    # ... cleanup for other backends

    yield

    # Cleanup after test
    await _cleanup_user_data(tasks_backend, test_user_uid)
    await _cleanup_user_data(tasks_backend, test_user_uid_2)


async def _cleanup_user_data(backend, user_uid: str):
    """Helper to cleanup user data."""
    try:
        result = await backend.get_user_entities(user_uid=user_uid)
        if result.is_ok and result.value:
            for entity in result.value:
                await backend.delete(entity.uid, cascade=True)
    except Exception:
        pass  # Ignore cleanup errors


# ============================================================================
# TESTS: Backend Relationship Methods
# ============================================================================


@pytest.mark.asyncio
async def test_task_relationship_auto_creation(tasks_backend, test_user_uid, create_test_users):
    """
    Test that creating a task automatically creates user relationship.

    Verifies auto-relationship creation in UniversalNeo4jBackend.create().
    """
    # Create task with user_uid
    task = Task(
        uid="task_test_001",
        user_uid=test_user_uid,
        title="Test Task Auto Relationship",
        description="Testing automatic relationship creation",
        status=EntityStatus.DRAFT,
        priority=Priority.MEDIUM,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    # Create task - should auto-create (User)-[:HAS_TASK]->(Task)
    result = await tasks_backend.create(task)
    assert result.is_ok, f"Task creation failed: {result.error}"

    # Verify user relationship exists via graph traversal
    user_tasks_result = await tasks_backend.get_user_entities(user_uid=test_user_uid)
    assert user_tasks_result.is_ok, f"Get user entities failed: {user_tasks_result.error}"
    # Unpack pagination tuple
    tasks, total_count = user_tasks_result.value
    assert len(tasks) == 1, "Should have exactly 1 task for user"
    assert total_count == 1, "Total count should be 1"
    assert tasks[0].uid == "task_test_001"

    # Cleanup (cascade=True to remove auto-created HAS_TASK relationship)
    result = await tasks_backend.delete("task_test_001", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete task"


@pytest.mark.asyncio
async def test_event_relationship_auto_creation(events_backend, test_user_uid, create_test_users):
    """Test automatic user relationship creation for events."""

    event = Event(
        uid="event_test_001",
        user_uid=test_user_uid,
        title="Test Event",
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=1),
        status=EntityStatus.SCHEDULED,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    result = await events_backend.create(event)
    assert result.is_ok

    # Verify relationship
    user_events = await events_backend.get_user_entities(user_uid=test_user_uid)
    assert user_events.is_ok
    # Unpack pagination tuple
    entities, total_count = user_events.value
    assert len(entities) == 1
    assert entities[0].uid == "event_test_001"

    # Cleanup (cascade=True to remove auto-created HAS_EVENT relationship)
    result = await events_backend.delete("event_test_001", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete event"


@pytest.mark.asyncio
async def test_habit_relationship_auto_creation(habits_backend, test_user_uid, create_test_users):
    """Test automatic user relationship creation for habits."""
    habit = Habit(
        uid="habit_test_001",
        user_uid=test_user_uid,
        title="Test Habit",
        description="Testing habit relationship",
        recurrence_pattern=RecurrencePattern.DAILY,
        status=HabitStatus.ACTIVE,
        current_streak=0,
        best_streak=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    result = await habits_backend.create(habit)
    assert result.is_ok

    # Verify relationship
    user_habits = await habits_backend.get_user_entities(user_uid=test_user_uid)
    assert user_habits.is_ok
    # Unpack pagination tuple
    entities, total_count = user_habits.value
    assert len(entities) == 1

    # Cleanup (cascade=True to remove auto-created HAS_HABIT relationship)
    result = await habits_backend.delete("habit_test_001", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete habit"


@pytest.mark.asyncio
async def test_goal_relationship_auto_creation(goals_backend, test_user_uid, create_test_users):
    """Test automatic user relationship creation for goals."""
    goal = Goal(
        uid="goal_test_001",
        user_uid=test_user_uid,
        title="Test Goal",
        description="Testing goal relationship",
        status=EntityStatus.ACTIVE,
        domain=Domain.PERSONAL,
        current_value=0.0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    result = await goals_backend.create(goal)
    assert result.is_ok

    # Verify relationship
    user_goals = await goals_backend.get_user_entities(user_uid=test_user_uid)
    assert user_goals.is_ok
    # Unpack pagination tuple
    entities, total_count = user_goals.value
    assert len(entities) == 1

    # Cleanup (cascade=True to remove auto-created HAS_GOAL relationship)
    result = await goals_backend.delete("goal_test_001", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete goal"


@pytest.mark.asyncio
async def test_user_entity_count(tasks_backend, test_user_uid, create_test_users):
    """Test counting user entities via graph relationships."""
    # Create multiple tasks
    for i in range(5):
        task = Task(
            uid=f"task_count_{i}",
            user_uid=test_user_uid,
            title=f"Test Task {i}",
            status=EntityStatus.DRAFT,
            priority=Priority.MEDIUM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        create_result = await tasks_backend.create(task)
        assert create_result.is_ok, f"Setup failed: Could not create task {i}"

    # Count user entities
    count_result = await tasks_backend.count_user_entities(user_uid=test_user_uid)
    assert count_result.is_ok
    assert count_result.value == 5

    # Cleanup (cascade=True to remove auto-created relationships)
    for i in range(5):
        result = await tasks_backend.delete(f"task_count_{i}", cascade=True)
        assert result.is_ok, f"Cleanup failed: Could not delete task_count_{i}"


# ============================================================================
# USER ISOLATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_user_isolation_tasks(
    tasks_backend, test_user_uid, test_user_uid_2, create_test_users
):
    """
    Test that users can only see their own tasks (user isolation).

    Critical security test - ensures no cross-user data leakage.
    """
    # User 1 creates task
    task_user1 = Task(
        uid="task_user1_001",
        user_uid=test_user_uid,
        title="User 1 Task",
        status=EntityStatus.DRAFT,
        priority=Priority.MEDIUM,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    create_result_u1 = await tasks_backend.create(task_user1)
    assert create_result_u1.is_ok, "Setup failed: Could not create user 1 task"

    # User 2 creates task
    task_user2 = Task(
        uid="task_user2_001",
        user_uid=test_user_uid_2,
        title="User 2 Task",
        status=EntityStatus.DRAFT,
        priority=Priority.MEDIUM,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    create_result_u2 = await tasks_backend.create(task_user2)
    assert create_result_u2.is_ok, "Setup failed: Could not create user 2 task"

    # User 1 should only see their own task
    user1_tasks = await tasks_backend.get_user_entities(user_uid=test_user_uid)
    assert user1_tasks.is_ok
    # Unpack pagination tuple
    entities, total_count = user1_tasks.value
    assert len(entities) == 1
    assert entities[0].uid == "task_user1_001"

    # User 2 should only see their own task
    user2_tasks = await tasks_backend.get_user_entities(user_uid=test_user_uid_2)
    assert user2_tasks.is_ok
    # Unpack pagination tuple
    entities, total_count = user2_tasks.value
    assert len(entities) == 1
    assert entities[0].uid == "task_user2_001"

    # Cleanup (cascade=True to remove auto-created HAS_TASK relationships)
    result = await tasks_backend.delete("task_user1_001", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete task_user1_001"
    result = await tasks_backend.delete("task_user2_001", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete task_user2_001"


@pytest.mark.asyncio
async def test_user_isolation_cross_domain(
    tasks_backend, goals_backend, create_test_users, test_user_uid, test_user_uid_2
):
    """Test user isolation across multiple domains."""
    # User 1: Create task and goal
    task_u1 = Task(
        uid="task_iso_u1",
        user_uid=test_user_uid,
        title="User 1 Task",
        status=EntityStatus.DRAFT,
        priority=Priority.MEDIUM,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    task_u1_result = await tasks_backend.create(task_u1)
    assert task_u1_result.is_ok, "Setup failed: Could not create user 1 task"

    goal_u1 = Goal(
        uid="goal_iso_u1",
        user_uid=test_user_uid,
        title="User 1 Goal",
        status=EntityStatus.ACTIVE,
        domain=Domain.PERSONAL,
        current_value=0.0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    goal_u1_result = await goals_backend.create(goal_u1)
    assert goal_u1_result.is_ok, "Setup failed: Could not create user 1 goal"

    # User 2: Create task and goal
    task_u2 = Task(
        uid="task_iso_u2",
        user_uid=test_user_uid_2,
        title="User 2 Task",
        status=EntityStatus.DRAFT,
        priority=Priority.MEDIUM,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    task_u2_result = await tasks_backend.create(task_u2)
    assert task_u2_result.is_ok, "Setup failed: Could not create user 2 task"

    goal_u2 = Goal(
        uid="goal_iso_u2",
        user_uid=test_user_uid_2,
        title="User 2 Goal",
        status=EntityStatus.ACTIVE,
        domain=Domain.PERSONAL,
        current_value=0.0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    goal_u2_result = await goals_backend.create(goal_u2)
    assert goal_u2_result.is_ok, "Setup failed: Could not create user 2 goal"

    # Verify isolation
    user1_tasks_result = await tasks_backend.get_user_entities(user_uid=test_user_uid)
    user1_goals_result = await goals_backend.get_user_entities(user_uid=test_user_uid)

    # Unpack pagination tuples
    user1_tasks, _ = user1_tasks_result.value
    user1_goals, _ = user1_goals_result.value

    assert len(user1_tasks) == 1
    assert len(user1_goals) == 1

    user2_tasks_result = await tasks_backend.get_user_entities(user_uid=test_user_uid_2)
    user2_goals_result = await goals_backend.get_user_entities(user_uid=test_user_uid_2)

    # Unpack pagination tuples
    user2_tasks, _ = user2_tasks_result.value
    user2_goals, _ = user2_goals_result.value

    assert len(user2_tasks) == 1
    assert len(user2_goals) == 1

    # Cleanup (cascade=True to remove auto-created HAS_* relationships)
    result = await tasks_backend.delete("task_iso_u1", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete task_iso_u1"
    result = await tasks_backend.delete("task_iso_u2", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete task_iso_u2"
    result = await goals_backend.delete("goal_iso_u1", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete goal_iso_u1"
    result = await goals_backend.delete("goal_iso_u2", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete goal_iso_u2"


# ============================================================================
# TESTS: UserService Aggregation
# ============================================================================


@pytest.mark.asyncio
async def test_user_stats_aggregation_structure(user_service, test_user_uid, create_test_users):
    """
    Test that user stats are aggregated correctly across all domains.

    Verifies UserService aggregation methods.
    """
    # Get profile hub data
    result = await user_service.get_profile_hub_data(test_user_uid)
    assert result.is_ok, f"Profile hub data failed: {result.error}"

    hub_data = result.value

    # Pattern 3C + UserContext: hub_data now includes full context
    # Verify context exists (THE source of truth)
    assert hasattr(hub_data, "context"), "ProfileHubData must have context field"
    context = hub_data.context
    assert context is not None, "Context must not be None"

    # Verify domain_stats exists and is DomainStatsAggregate (computed from context)
    assert hasattr(hub_data, "domain_stats")
    domain_stats = hub_data.domain_stats

    # Verify all domain stat objects exist (frozen dataclasses)
    assert hasattr(domain_stats, "tasks")
    assert hasattr(domain_stats, "events")
    assert hasattr(domain_stats, "habits")
    assert hasattr(domain_stats, "goals")
    assert hasattr(domain_stats, "choices")
    assert hasattr(domain_stats, "principles")
    assert hasattr(domain_stats, "journals")
    assert hasattr(domain_stats, "finance")
    assert hasattr(domain_stats, "learning")

    # Verify tasks structure (use attribute access)
    assert hasattr(domain_stats.tasks, "total_active")
    assert hasattr(domain_stats.tasks, "completed_today")
    assert hasattr(domain_stats.tasks, "completed_this_week")
    assert hasattr(domain_stats.tasks, "overdue")
    assert hasattr(domain_stats.tasks, "completion_rate")

    # Verify events structure
    assert hasattr(domain_stats.events, "total_upcoming")
    assert hasattr(domain_stats.events, "this_week")
    assert hasattr(domain_stats.events, "this_month")
    assert hasattr(domain_stats.events, "attended")

    # Verify habits structure
    assert hasattr(domain_stats.habits, "total_active")
    assert hasattr(domain_stats.habits, "current_streak")
    assert hasattr(domain_stats.habits, "longest_streak")
    assert hasattr(domain_stats.habits, "consistency_rate")

    # Verify goals structure
    assert hasattr(domain_stats.goals, "total_active")
    assert hasattr(domain_stats.goals, "on_track")
    assert hasattr(domain_stats.goals, "at_risk")
    assert hasattr(domain_stats.goals, "completed")
    assert hasattr(domain_stats.goals, "average_progress")

    # Verify choices structure
    assert hasattr(domain_stats.choices, "total_active")
    assert hasattr(domain_stats.choices, "pending")
    assert hasattr(domain_stats.choices, "resolved")
    assert hasattr(domain_stats.choices, "deferred")

    # Verify principles structure
    assert hasattr(domain_stats.principles, "total_active")
    assert hasattr(domain_stats.principles, "practicing")
    assert hasattr(domain_stats.principles, "avg_alignment")
    assert hasattr(domain_stats.principles, "needs_review")

    # Verify journals structure
    assert hasattr(domain_stats.journals, "total_entries")
    assert hasattr(domain_stats.journals, "this_week")
    assert hasattr(domain_stats.journals, "this_month")
    assert hasattr(domain_stats.journals, "avg_per_week")

    # Verify finance structure
    assert hasattr(domain_stats.finance, "total_expenses")
    assert hasattr(domain_stats.finance, "this_month_spending")
    assert hasattr(domain_stats.finance, "active_budgets")
    assert hasattr(domain_stats.finance, "over_budget_count")

    # Verify learning structure
    assert hasattr(domain_stats.learning, "knowledge_mastered")
    assert hasattr(domain_stats.learning, "paths_active")
    assert hasattr(domain_stats.learning, "paths_completed")


@pytest.mark.asyncio
async def test_cross_domain_analytics(user_service, test_user_uid, create_test_users):
    """Test cross-domain analytics and overall metrics calculation."""
    result = await user_service.get_profile_hub_data(test_user_uid)
    assert result.is_ok

    hub_data = result.value

    # Pattern 3C: Verify overall metrics (OverallMetrics frozen dataclass)
    assert hasattr(hub_data, "overall_metrics")
    overall = hub_data.overall_metrics

    # Verify metric structure (use attribute access)
    assert hasattr(overall, "activity_score")
    assert hasattr(overall, "completion_rate")
    assert hasattr(overall, "productivity_score")
    assert hasattr(overall, "total_active_items")
    assert hasattr(overall, "completed_today")

    # Verify metric types
    assert isinstance(overall.activity_score, int | float)
    assert isinstance(overall.completion_rate, int | float)
    assert isinstance(overall.productivity_score, int | float)
    assert isinstance(overall.total_active_items, int)
    assert isinstance(overall.completed_today, int)

    # Verify recommendations exist (attribute access)
    assert hasattr(hub_data, "recommendations")
    assert isinstance(hub_data.recommendations, list)

    # Verify recent activities exist (attribute access)
    assert hasattr(hub_data, "recent_activities")
    assert isinstance(hub_data.recent_activities, list)


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.slow
async def test_performance_large_dataset(tasks_backend, test_user_uid, create_test_users):
    """
    Test performance with realistic data volumes.

    Creates 100 tasks and measures query performance.
    """
    import time

    # Create 100 tasks
    task_uids = []
    for i in range(100):
        task = Task(
            uid=f"task_perf_{i}",
            user_uid=test_user_uid,
            title=f"Performance Test Task {i}",
            status=EntityStatus.DRAFT,
            priority=Priority.MEDIUM,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        create_result = await tasks_backend.create(task)
        assert create_result.is_ok, f"Setup failed: Could not create task {i}"
        task_uids.append(f"task_perf_{i}")

    # Measure query performance
    start = time.time()
    result = await tasks_backend.get_user_entities(user_uid=test_user_uid, limit=100)
    end = time.time()

    query_time = end - start

    # Verify results
    assert result.is_ok
    # Unpack pagination tuple
    entities, total_count = result.value
    assert len(entities) == 100

    # Performance assertion (should be < 1 second for 100 entities)
    assert query_time < 1.0, f"Query took {query_time:.3f}s (should be < 1s)"

    # Cleanup (cascade=True to remove auto-created HAS_TASK relationships)
    for uid in task_uids:
        result = await tasks_backend.delete(uid, cascade=True)
        assert result.is_ok, f"Cleanup failed: Could not delete {uid}"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_entity_without_user_uid(tasks_backend, create_test_users):
    """Test creating entity with empty user_uid string (edge case)."""
    task = Task(
        uid="task_no_user",
        user_uid="",  # Empty string (edge case - no valid user)
        title="Task Without User",
        status=EntityStatus.DRAFT,
        priority=Priority.MEDIUM,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    # Should succeed (entity creation works, but relationship creation may fail)
    result = await tasks_backend.create(task)
    assert result.is_ok, f"Task creation should succeed even with empty user_uid: {result.error}"

    # Cleanup (cascade=True in case any relationships were created)
    result = await tasks_backend.delete("task_no_user", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete task"


@pytest.mark.asyncio
async def test_relationship_access_tracking(tasks_backend, test_user_uid, create_test_users):
    """Test relationship metadata updates (access tracking)."""
    # Create task
    task = Task(
        uid="task_access_001",
        user_uid=test_user_uid,
        title="Access Tracking Test",
        status=EntityStatus.DRAFT,
        priority=Priority.MEDIUM,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    create_result = await tasks_backend.create(task)
    assert create_result.is_ok, "Setup failed: Could not create task"

    # Update relationship access
    result = await tasks_backend.update_relationship_access(
        user_uid=test_user_uid, entity_uid="task_access_001"
    )
    assert result.is_ok

    # Cleanup (cascade=True to remove auto-created HAS_TASK relationship)
    result = await tasks_backend.delete("task_access_001", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete task"


@pytest.mark.asyncio
async def test_delete_user_relationship(tasks_backend, test_user_uid, create_test_users):
    """Test deleting user-entity relationship."""
    # Create task
    task = Task(
        uid="task_delete_rel",
        user_uid=test_user_uid,
        title="Delete Relationship Test",
        status=EntityStatus.DRAFT,
        priority=Priority.MEDIUM,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    create_result = await tasks_backend.create(task)
    assert create_result.is_ok, "Setup failed: Could not create task"

    # Verify relationship exists
    user_tasks = await tasks_backend.get_user_entities(user_uid=test_user_uid)
    # Unpack pagination tuple
    entities, total_count = user_tasks.value
    assert len(entities) == 1

    # Delete relationship (not entity)
    delete_result = await tasks_backend.delete_user_relationship(
        user_uid=test_user_uid, entity_uid="task_delete_rel"
    )
    assert delete_result.is_ok

    # Verify relationship deleted
    user_tasks_after = await tasks_backend.get_user_entities(user_uid=test_user_uid)
    # Unpack pagination tuple
    entities, total_count = user_tasks_after.value
    assert len(entities) == 0

    # Entity should still exist
    entity_result = await tasks_backend.get("task_delete_rel")
    assert entity_result.is_ok

    # Cleanup (relationship was deleted above, but cascade=True for safety)
    result = await tasks_backend.delete("task_delete_rel", cascade=True)
    assert result.is_ok, "Cleanup failed: Could not delete task"


# ============================================================================
# SUMMARY STATS
# ============================================================================


def test_summary():
    """
    Test Suite Summary
    ==================

    Tests (Backend): 7 tests
    - Auto-relationship creation for all domains
    - Entity counting via relationships
    - Relationship access tracking
    - Relationship deletion

    Tests (UserService): 2 tests
    - Stats aggregation structure
    - Cross-domain analytics

    User Isolation Tests: 2 tests
    - Single domain isolation
    - Cross-domain isolation

    Performance Tests: 1 test
    - Large dataset query performance

    Edge Cases: 3 tests
    - Entity without user_uid
    - Relationship access tracking
    - Relationship deletion

    Total: 15 comprehensive tests
    """
    pass
