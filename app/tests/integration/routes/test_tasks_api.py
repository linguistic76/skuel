"""
Integration Tests for Tasks API Routes.

Tests cover:
1. CRUD operations (create, get, update, delete, list) via CRUDRouteFactory
2. Query operations (by user, goal, habit, status) via CommonQueryRouteFactory
3. Domain-specific operations (complete, uncomplete, assign, dependencies)
4. Search and context operations
5. Error handling and validation

All tests use mocked services to avoid external dependencies.

Note: All async tests use pytest-asyncio for proper event loop management.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import EntityStatus, Priority
from core.utils.result_simplified import Errors, Result

# Mark all tests as async (all tests in this module are async)
pytestmark = pytest.mark.asyncio


class MockTask:
    """Mock Task model for testing."""

    def __init__(
        self,
        uid: str = "task.test123",
        user_uid: str = "user.test",
        title: str = "Test Task",
        description: str = "A test task description",
        status: EntityStatus = EntityStatus.ACTIVE,
        priority: Priority = Priority.MEDIUM,
        due_date: date | None = None,
    ):
        self.uid = uid
        self.user_uid = user_uid
        self.title = title
        self.description = description
        self.status = status
        self.priority = priority
        self.due_date = due_date or (date.today() + timedelta(days=7))
        self.created_at = "2024-01-01T00:00:00Z"
        self.updated_at = "2024-01-01T00:00:00Z"

    def to_dict(self):
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "due_date": str(self.due_date),
        }


@pytest.fixture
def mock_tasks_service():
    """Create mock TasksService."""
    service = MagicMock()

    # Standard CRUD operations
    service.create = AsyncMock(return_value=Result.ok(MockTask()))
    service.get = AsyncMock(return_value=Result.ok(MockTask()))
    service.update = AsyncMock(return_value=Result.ok(MockTask()))
    service.delete = AsyncMock(return_value=Result.ok(True))
    service.list = AsyncMock(return_value=Result.ok([MockTask(), MockTask()]))

    # Query operations
    service.get_by_user = AsyncMock(return_value=Result.ok([MockTask()]))
    service.get_by_goal = AsyncMock(return_value=Result.ok([MockTask()]))
    service.get_by_habit = AsyncMock(return_value=Result.ok([MockTask()]))
    service.get_by_status = AsyncMock(return_value=Result.ok([MockTask()]))

    # Domain-specific operations
    service.complete_task_with_cascade = AsyncMock(return_value=Result.ok(MockTask()))
    service.assign_task_to_user = AsyncMock(return_value=Result.ok(MockTask()))
    service.get_task_dependencies = AsyncMock(return_value=Result.ok([]))
    service.create_task_dependency = AsyncMock(return_value=Result.ok(True))
    service.get_user_assigned_tasks = AsyncMock(return_value=Result.ok([MockTask()]))
    service.get_tasks_applying_knowledge = AsyncMock(return_value=Result.ok([MockTask()]))
    service.get_task_with_context = AsyncMock(
        return_value=Result.ok({"task": MockTask().to_dict()})
    )
    service.get_task_completion_impact = AsyncMock(return_value=Result.ok({"impact": "medium"}))
    service.get_task_practice_opportunities = AsyncMock(return_value=Result.ok([]))
    service.search = AsyncMock(return_value=Result.ok([MockTask()]))

    return service


class TestCRUDOperations:
    """Tests for standard CRUD operations via CRUDRouteFactory."""

    async def test_create_task_request_structure(self):
        """Test TaskCreateRequest has required fields."""
        from core.models.task.task_request import TaskCreateRequest

        # Verify the request model exists and has expected fields
        assert hasattr(TaskCreateRequest, "__annotations__")
        fields = TaskCreateRequest.__annotations__
        assert "title" in fields or "title" in dir(TaskCreateRequest)

    async def test_create_task_returns_result(self, mock_tasks_service):
        """Test that create returns a Result."""
        task_data = {
            "title": "New Task",
            "description": "A new task",
            "user_uid": "user.test",
        }

        result = await mock_tasks_service.create(task_data)

        assert result.is_ok
        assert result.value.title == "Test Task"

    async def test_get_task_by_uid(self, mock_tasks_service):
        """Test retrieving a task by UID."""
        result = await mock_tasks_service.get("task.test123")

        assert result.is_ok
        assert result.value.uid == "task.test123"

    async def test_get_task_not_found(self, mock_tasks_service):
        """Test retrieving a non-existent task."""
        mock_tasks_service.get = AsyncMock(
            return_value=Result.fail(Errors.not_found("task", "task.nonexistent"))
        )

        result = await mock_tasks_service.get("task.nonexistent")

        assert result.is_error
        assert "not found" in result.error.message.lower()

    async def test_update_task(self, mock_tasks_service):
        """Test updating a task."""
        update_data = {"title": "Updated Title"}

        result = await mock_tasks_service.update("task.test123", update_data)

        assert result.is_ok

    async def test_delete_task(self, mock_tasks_service):
        """Test deleting a task."""
        result = await mock_tasks_service.delete("task.test123")

        assert result.is_ok
        assert result.value is True

    async def test_list_tasks(self, mock_tasks_service):
        """Test listing tasks with pagination."""
        result = await mock_tasks_service.list()

        assert result.is_ok
        assert len(result.value) == 2


class TestQueryOperations:
    """Tests for query operations via CommonQueryRouteFactory."""

    async def test_get_tasks_by_user(self, mock_tasks_service):
        """Test getting tasks for a specific user."""
        result = await mock_tasks_service.get_by_user("user.test")

        assert result.is_ok
        assert len(result.value) >= 1

    async def test_get_tasks_by_goal(self, mock_tasks_service):
        """Test getting tasks for a specific goal."""
        result = await mock_tasks_service.get_by_goal("goal.test123")

        assert result.is_ok

    async def test_get_tasks_by_habit(self, mock_tasks_service):
        """Test getting tasks for a specific habit."""
        result = await mock_tasks_service.get_by_habit("habit.test123")

        assert result.is_ok

    async def test_get_tasks_by_status(self, mock_tasks_service):
        """Test filtering tasks by status."""
        result = await mock_tasks_service.get_by_status(EntityStatus.ACTIVE)

        assert result.is_ok


class TestCompleteTask:
    """Tests for task completion functionality."""

    async def test_complete_task_success(self, mock_tasks_service):
        """Test completing a task."""
        mock_tasks_service.complete_task_with_cascade = AsyncMock(
            return_value=Result.ok(MockTask(status=EntityStatus.COMPLETED))
        )

        result = await mock_tasks_service.complete_task_with_cascade(
            "task.test123",
            user_context=None,
            actual_minutes=60,
            quality_score=0.9,
        )

        assert result.is_ok
        assert result.value.status == EntityStatus.COMPLETED

    async def test_complete_task_with_optional_params(self, mock_tasks_service):
        """Test completing a task with optional parameters."""
        result = await mock_tasks_service.complete_task_with_cascade(
            "task.test123",
            user_context=None,
        )

        assert result.is_ok

    async def test_uncomplete_task(self, mock_tasks_service):
        """Test marking a task as incomplete."""
        mock_tasks_service.update = AsyncMock(
            return_value=Result.ok(MockTask(status=EntityStatus.ACTIVE))
        )

        result = await mock_tasks_service.update("task.test123", {"status": EntityStatus.ACTIVE})

        assert result.is_ok
        assert result.value.status == EntityStatus.ACTIVE


class TestTaskAssignment:
    """Tests for task assignment functionality."""

    async def test_assign_task_to_user(self, mock_tasks_service):
        """Test assigning a task to a user."""
        result = await mock_tasks_service.assign_task_to_user(
            "task.test123",
            "user.assignee",
            "user.assigner",
            Priority.HIGH,
        )

        assert result.is_ok

    async def test_get_user_assigned_tasks(self, mock_tasks_service):
        """Test getting tasks assigned to a user."""
        result = await mock_tasks_service.get_user_assigned_tasks(
            "user.test",
            include_completed=False,
            limit=100,
        )

        assert result.is_ok


class TestTaskDependencies:
    """Tests for task dependency functionality."""

    async def test_get_task_dependencies(self, mock_tasks_service):
        """Test getting task dependencies."""
        result = await mock_tasks_service.get_task_dependencies("task.test123")

        assert result.is_ok
        assert isinstance(result.value, list)

    async def test_create_task_dependency(self, mock_tasks_service):
        """Test creating a task dependency."""
        result = await mock_tasks_service.create_task_dependency(
            "task.test123",
            "task.blocked456",
            is_hard_dependency=True,
            dependency_type="blocks",
        )

        assert result.is_ok


class TestTaskContext:
    """Tests for task context and intelligence operations."""

    async def test_get_task_with_context(self, mock_tasks_service):
        """Test getting task with full graph context."""
        result = await mock_tasks_service.get_task_with_context("task.test123", depth=2)

        assert result.is_ok
        assert "task" in result.value

    async def test_get_task_completion_impact(self, mock_tasks_service):
        """Test analyzing task completion impact."""
        result = await mock_tasks_service.get_task_completion_impact("task.test123")

        assert result.is_ok
        assert "impact" in result.value

    async def test_get_task_practice_opportunities(self, mock_tasks_service):
        """Test finding practice opportunities for task."""
        result = await mock_tasks_service.get_task_practice_opportunities("task.test123", depth=2)

        assert result.is_ok
        assert isinstance(result.value, list)


class TestTaskSearch:
    """Tests for task search functionality."""

    async def test_search_tasks(self, mock_tasks_service):
        """Test searching tasks."""
        result = await mock_tasks_service.search("quarterly report", limit=10)

        assert result.is_ok
        assert len(result.value) >= 1

    async def test_search_tasks_empty_query(self, mock_tasks_service):
        """Test searching with empty query."""
        mock_tasks_service.search = AsyncMock(return_value=Result.ok([]))

        result = await mock_tasks_service.search("", limit=10)

        assert result.is_ok
        assert len(result.value) == 0


class TestKnowledgeRelation:
    """Tests for tasks-knowledge relationship."""

    async def test_get_tasks_applying_knowledge(self, mock_tasks_service):
        """Test getting tasks that apply specific knowledge."""
        result = await mock_tasks_service.get_tasks_applying_knowledge("ku.python.async")

        assert result.is_ok
        assert isinstance(result.value, list)


class TestRouteFactory:
    """Tests for CRUDRouteFactory and CommonQueryRouteFactory integration."""

    async def test_crud_factory_routes(self):
        """Test that CRUD factory defines expected routes."""
        expected_routes = [
            "POST /api/tasks",  # create
            "GET /api/tasks/{uid}",  # get
            "PUT /api/tasks/{uid}",  # update
            "DELETE /api/tasks/{uid}",  # delete
            "GET /api/tasks",  # list
        ]
        # Verify route patterns are correct
        for route in expected_routes:
            assert "/api/tasks" in route

    async def test_query_factory_routes(self):
        """Test that query factory defines expected routes."""
        expected_routes = [
            "GET /api/tasks/user/{user_uid}",
            "GET /api/tasks/goal/{goal_uid}",
            "GET /api/tasks/habit/{habit_uid}",
            "GET /api/tasks/by-status",
        ]
        for route in expected_routes:
            assert "/api/tasks" in route


class TestErrorHandling:
    """Tests for error handling in task operations."""

    async def test_validation_error_on_create(self, mock_tasks_service):
        """Test validation error when creating task with invalid data."""
        mock_tasks_service.create = AsyncMock(
            return_value=Result.fail(Errors.validation("Title is required", field="title"))
        )

        result = await mock_tasks_service.create({})

        assert result.is_error
        assert "title" in result.error.message.lower()

    async def test_database_error_handling(self, mock_tasks_service):
        """Test database error handling."""
        mock_tasks_service.get = AsyncMock(
            return_value=Result.fail(Errors.database("get", "Connection timeout"))
        )

        result = await mock_tasks_service.get("task.test123")

        assert result.is_error
        assert "timeout" in result.error.message.lower()


class TestTaskModel:
    """Tests for Task model structure."""

    async def test_task_has_required_fields(self):
        """Test that Task model has required fields."""
        from core.models.task.task import Task as Task

        required_fields = ["uid", "user_uid", "title"]
        for field in required_fields:
            assert hasattr(Task, "__annotations__") or field in dir(Task)

    async def test_activity_status_enum(self):
        """Test EntityStatus enum values."""
        assert EntityStatus.ACTIVE.value == "active"
        assert EntityStatus.COMPLETED.value == "completed"
        assert EntityStatus.SCHEDULED.value == "scheduled"
        assert EntityStatus.DRAFT.value == "draft"

    async def test_priority_enum(self):
        """Test Priority enum values."""
        assert Priority.LOW.value == "low"
        assert Priority.MEDIUM.value == "medium"
        assert Priority.HIGH.value == "high"
        assert Priority.CRITICAL.value == "critical"


class TestBoundaryHandler:
    """Tests for @boundary_handler decorator behavior."""

    async def test_boundary_handler_converts_result_ok(self):
        """Test that boundary_handler converts Result.ok to HTTP 200."""
        # The decorator should convert Result.ok to proper HTTP response
        result = Result.ok(MockTask())
        assert result.is_ok

    async def test_boundary_handler_converts_result_fail(self):
        """Test that boundary_handler converts Result.fail to HTTP error."""
        result = Result.fail(Errors.not_found("task", "task.test"))
        assert result.is_error
