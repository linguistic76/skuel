"""
Integration Test: Tasks Core Operations
========================================

Tests basic CRUD operations and core functionality for the Tasks domain.

This test suite verifies that:
1. Tasks can be created, retrieved, and listed
2. Tasks can be filtered by status, priority, and due date
3. Task business logic works correctly (validation, priority rules)
4. Event publishing works correctly

Test Coverage:
--------------
- TasksCoreService.create()
- TasksCoreService.get()
- TasksCoreService.list()
- Task business logic
- Task enum classifications
"""

from datetime import date, timedelta

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import EntityStatus, Priority
from core.models.enums.entity_enums import EntityType
from core.models.task.task import Task as Task
from core.services.tasks.tasks_core_service import TasksCoreService


@pytest.mark.asyncio
class TestTasksCoreOperations:
    """Integration tests for Tasks core CRUD operations."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def tasks_backend(self, neo4j_driver, clean_neo4j):
        """Create tasks backend with clean database."""
        return UniversalNeo4jBackend[Task](
            neo4j_driver, "Entity", Task, default_filters={"ku_type": "task"}
        )

    @pytest_asyncio.fixture
    async def tasks_service(self, tasks_backend, event_bus):
        """Create TasksCoreService with event bus."""
        return TasksCoreService(backend=tasks_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_tasks_core"

    # ==========================================================================
    # CRUD OPERATIONS TESTS (5 tests)
    # ==========================================================================

    async def test_create_task(self, tasks_service, test_user_uid):
        """Test creating a new task."""
        # Arrange
        today = date.today()
        task = Task(
            uid="task.write_report",
            user_uid=test_user_uid,
            title="Write Quarterly Report",
            description="Compile Q3 performance metrics and analysis",
            due_date=today + timedelta(days=7),
            priority=Priority.HIGH,
            status=EntityStatus.ACTIVE,
            duration_minutes=120,
        )

        # Act
        result = await tasks_service.create(task)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.uid == "task.write_report"
        assert created.title == "Write Quarterly Report"
        assert created.priority == Priority.HIGH
        assert created.status == EntityStatus.ACTIVE
        assert created.duration_minutes == 120

    async def test_get_task_by_uid(self, tasks_service, test_user_uid):
        """Test retrieving a task by UID."""
        # Arrange - Create a task first
        task = Task(
            uid="task.get_test",
            user_uid=test_user_uid,
            title="Test Task for Retrieval",
            description="This task tests retrieval functionality",
            status=EntityStatus.ACTIVE,
        )
        create_result = await tasks_service.create(task)
        assert create_result.is_ok

        # Act - Retrieve the task
        result = await tasks_service.get("task.get_test")

        # Assert
        assert result.is_ok
        retrieved = result.value
        assert retrieved.uid == "task.get_test"
        assert retrieved.title == "Test Task for Retrieval"

    async def test_get_nonexistent_task(self, tasks_service):
        """Test getting a task that doesn't exist."""
        # Act
        result = await tasks_service.get("task.nonexistent")

        # Assert
        assert result.is_error
        assert "not found" in result.error.message.lower()

    async def test_list_user_tasks(self, tasks_service, test_user_uid):
        """Test listing all tasks for a user."""
        # Arrange - Create multiple tasks
        tasks = [
            Task(
                uid=f"task.list_test_{i}",
                user_uid=test_user_uid,
                title=f"Test Task {i}",
                description=f"Description for task {i}",
                status=EntityStatus.ACTIVE,
            )
            for i in range(3)
        ]

        for task in tasks:
            result = await tasks_service.create(task)
            assert result.is_ok

        # Act - List tasks
        result = await tasks_service.backend.find_by(user_uid=test_user_uid)

        # Assert
        assert result.is_ok
        user_tasks = result.value
        assert len(user_tasks) >= 3

    async def test_multiple_tasks_same_user(self, tasks_service, test_user_uid):
        """Test creating multiple tasks for the same user."""
        # Arrange & Act - Create 5 tasks
        for i in range(5):
            task = Task(
                uid=f"task.multi_{i}",
                user_uid=test_user_uid,
                title=f"Multi Task {i}",
                description=f"Multiple task {i}",
                status=EntityStatus.ACTIVE,
            )
            result = await tasks_service.create(task)
            assert result.is_ok

        # Assert - Verify all were created
        list_result = await tasks_service.backend.find_by(user_uid=test_user_uid)
        assert list_result.is_ok
        assert len(list_result.value) >= 5

    # ==========================================================================
    # FILTERING TESTS (3 tests)
    # ==========================================================================

    async def test_filter_by_status(self, tasks_service, test_user_uid):
        """Test filtering tasks by status."""
        # Arrange - Create tasks with different statuses
        active_task = Task(
            uid="task.active",
            user_uid=test_user_uid,
            title="Active Task",
            description="Currently working on this",
            status=EntityStatus.ACTIVE,
        )
        completed_task = Task(
            uid="task.completed",
            user_uid=test_user_uid,
            title="Completed Task",
            description="Successfully finished",
            status=EntityStatus.COMPLETED,
        )

        await tasks_service.create(active_task)
        await tasks_service.create(completed_task)

        # Act - Filter by status
        active_result = await tasks_service.backend.find_by(
            user_uid=test_user_uid, status=EntityStatus.ACTIVE.value
        )
        completed_result = await tasks_service.backend.find_by(
            user_uid=test_user_uid, status=EntityStatus.COMPLETED.value
        )

        # Assert
        assert active_result.is_ok
        assert len(active_result.value) >= 1
        assert all(t.status == EntityStatus.ACTIVE for t in active_result.value)

        assert completed_result.is_ok
        assert len(completed_result.value) >= 1
        assert all(t.status == EntityStatus.COMPLETED for t in completed_result.value)

    async def test_filter_by_priority(self, tasks_service, test_user_uid):
        """Test filtering tasks by priority."""
        # Arrange - Create tasks with different priorities
        today = date.today()
        high_task = Task(
            uid="task.high_priority",
            user_uid=test_user_uid,
            title="High Priority Task",
            description="Critical task",
            priority=Priority.HIGH,
            due_date=today + timedelta(days=1),  # Required for high priority
            status=EntityStatus.ACTIVE,
        )
        low_task = Task(
            uid="task.low_priority",
            user_uid=test_user_uid,
            title="Low Priority Task",
            description="Nice to have",
            priority=Priority.LOW,
            status=EntityStatus.ACTIVE,
        )

        await tasks_service.create(high_task)
        await tasks_service.create(low_task)

        # Act - Filter by priority
        high_result = await tasks_service.backend.find_by(
            user_uid=test_user_uid, priority=Priority.HIGH.value
        )
        low_result = await tasks_service.backend.find_by(
            user_uid=test_user_uid, priority=Priority.LOW.value
        )

        # Assert
        assert high_result.is_ok
        assert len(high_result.value) >= 1
        assert all(t.priority == Priority.HIGH for t in high_result.value)

        assert low_result.is_ok
        assert len(low_result.value) >= 1
        assert all(t.priority == Priority.LOW for t in low_result.value)

    async def test_filter_by_due_date(self, tasks_service, test_user_uid):
        """Test filtering tasks by due date range."""
        # Arrange - Create tasks with different due dates
        today = date.today()
        near_task = Task(
            uid="task.due_soon",
            user_uid=test_user_uid,
            title="Due Soon Task",
            description="Due this week",
            due_date=today + timedelta(days=3),
            status=EntityStatus.ACTIVE,
        )
        far_task = Task(
            uid="task.due_later",
            user_uid=test_user_uid,
            title="Due Later Task",
            description="Due next month",
            due_date=today + timedelta(days=30),
            status=EntityStatus.ACTIVE,
        )

        await tasks_service.create(near_task)
        await tasks_service.create(far_task)

        # Act - Filter by due date (tasks due within 1 week)
        week_from_now = today + timedelta(days=7)
        result = await tasks_service.backend.find_by(
            user_uid=test_user_uid, due_date__lte=str(week_from_now)
        )

        # Assert
        assert result.is_ok
        assert len(result.value) >= 1
        # All returned tasks should have due_date <= week_from_now
        for task in result.value:
            if task.due_date:
                assert str(task.due_date) <= str(week_from_now)

    # ==========================================================================
    # BUSINESS LOGIC TESTS (4 tests)
    # ==========================================================================

    async def test_task_statuses(self, tasks_service, test_user_uid):
        """Test creating tasks with all status types."""
        # Arrange & Act - Create tasks with each status
        statuses = [
            EntityStatus.DRAFT,
            EntityStatus.ACTIVE,
            EntityStatus.ACTIVE,
            EntityStatus.COMPLETED,
            EntityStatus.CANCELLED,
        ]

        for status in statuses:
            task = Task(
                uid=f"task.status_{status.value}",
                user_uid=test_user_uid,
                title=f"Task with {status.value} status",
                description=f"Testing {status.value} status",
                status=status,
            )
            result = await tasks_service.create(task)
            assert result.is_ok
            assert result.value.status == status

    async def test_task_priorities(self, tasks_service, test_user_uid):
        """Test creating tasks with all priority types."""
        # Arrange & Act - Create tasks with each priority
        today = date.today()
        priorities = [
            (Priority.LOW, None),  # Low priority doesn't need due date
            (Priority.MEDIUM, None),  # Medium priority doesn't need due date
            (Priority.HIGH, today + timedelta(days=1)),  # High requires due date
            (Priority.CRITICAL, today + timedelta(days=1)),  # Critical requires due date
        ]

        for priority, due_date in priorities:
            task = Task(
                uid=f"task.priority_{priority.value}",
                user_uid=test_user_uid,
                title=f"{priority.value.title()} Priority Task",
                description=f"Testing {priority.value} priority",
                priority=priority,
                due_date=due_date,
            )
            result = await tasks_service.create(task)
            assert result.is_ok
            assert result.value.priority == priority

    async def test_high_priority_requires_due_date(self, tasks_service, test_user_uid):
        """Test that high/critical priority tasks must have due dates."""
        # Arrange - Create high priority task without due date
        invalid_task = Task(
            uid="task.invalid_high_priority",
            user_uid=test_user_uid,
            title="Invalid High Priority Task",
            description="High priority without due date",
            priority=Priority.HIGH,
            due_date=None,  # Invalid: high priority requires due date
        )

        # Act
        result = await tasks_service.create(invalid_task)

        # Assert - Should fail validation
        assert result.is_error
        assert "must have a due date" in result.error.message.lower()

    async def test_task_with_time_tracking(self, tasks_service, test_user_uid):
        """Test creating a task with duration estimates and tracking."""
        # Arrange
        task = Task(
            uid="task.with_time_tracking",
            user_uid=test_user_uid,
            title="Task with Time Tracking",
            description="Track estimated vs actual time",
            status=EntityStatus.ACTIVE,
            duration_minutes=60,  # Estimated duration
            actual_minutes=45,  # Actual time spent
        )

        # Act
        result = await tasks_service.create(task)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.duration_minutes == 60
        assert created.actual_minutes == 45

    # ==========================================================================
    # EDGE CASES TESTS (3 tests)
    # ==========================================================================

    async def test_task_with_optional_fields(self, tasks_service, test_user_uid):
        """Test creating a task with optional fields populated."""
        # Arrange
        today = date.today()
        task = Task(
            uid="task.full_details",
            user_uid=test_user_uid,
            title="Fully Detailed Task",
            description="Complete task with all optional fields",
            due_date=today + timedelta(days=7),
            scheduled_date=today + timedelta(days=5),
            duration_minutes=90,
            status=EntityStatus.ACTIVE,
            priority=Priority.CRITICAL,
            project="Q3 Goals",
            tags=("urgent", "quarterly", "report"),
        )

        # Act
        result = await tasks_service.create(task)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.scheduled_date == today + timedelta(days=5)
        assert created.project == "Q3 Goals"
        assert len(created.tags) == 3
        assert "urgent" in created.tags

    async def test_task_without_optional_fields(self, tasks_service, test_user_uid):
        """Test creating a task with minimal required fields."""
        # Arrange - Only required fields (ku_type=TASK for correct defaults)
        task = Task(
            uid="task.minimal",
            user_uid=test_user_uid,
            title="Minimal Task",
            description=None,  # Optional
            ku_type=EntityType.TASK,
        )

        # Act
        result = await tasks_service.create(task)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.description is None
        assert created.due_date is None
        assert created.scheduled_date is None
        # Check defaults are set
        assert created.status == EntityStatus.DRAFT
        assert created.priority is None  # Entity default: no priority
        assert created.duration_minutes is None  # Entity default: no duration

    async def test_task_date_ranges(self, tasks_service, test_user_uid):
        """Test creating tasks with different date ranges."""
        # Arrange & Act - Create tasks with different dates
        today = date.today()
        date_configs = [
            (today + timedelta(days=1), None),  # Due tomorrow, no schedule
            (
                today + timedelta(days=7),
                today + timedelta(days=3),
            ),  # Due in week, scheduled in 3 days
            (
                today + timedelta(days=30),
                today + timedelta(days=20),
            ),  # Due in month, scheduled in 20 days
        ]

        for i, (due, scheduled) in enumerate(date_configs):
            task = Task(
                uid=f"task.date_range_{i}",
                user_uid=test_user_uid,
                title=f"Task with date range {i}",
                description=f"Due {due}, scheduled {scheduled}",
                status=EntityStatus.ACTIVE,
                due_date=due,
                scheduled_date=scheduled,
            )
            result = await tasks_service.create(task)
            assert result.is_ok
            # Compare string representations (Neo4j stores dates as strings)
            assert str(result.value.due_date) == str(due)
            if scheduled:
                assert str(result.value.scheduled_date) == str(scheduled)
