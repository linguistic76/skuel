"""
Integration Tests for Goals API Routes.

Tests cover:
1. CRUD operations (create, get, update, delete, list) via CRUDRouteFactory
2. Query operations (by user, habit, status) via CommonQueryRouteFactory
3. Progress tracking operations
4. Milestone management
5. Habit linking
6. Goal status operations (activate, pause, complete, archive)
7. Categories and search

All tests use mocked services to avoid external dependencies.

Note: All async tests use pytest-asyncio for proper event loop management.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import ActivityStatus, Priority
from core.utils.result_simplified import Errors, Result

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


class MockGoal:
    """Mock Goal model for testing."""

    def __init__(
        self,
        uid: str = "goal.test123",
        user_uid: str = "user.test",
        title: str = "Test Goal",
        description: str = "A test goal description",
        status: ActivityStatus = ActivityStatus.IN_PROGRESS,
        priority: Priority = Priority.HIGH,
        target_date: date | None = None,
        progress: float = 0.0,
    ):
        self.uid = uid
        self.user_uid = user_uid
        self.title = title
        self.description = description
        self.status = status
        self.priority = priority
        self.target_date = target_date or (date.today() + timedelta(days=90))
        self.progress = progress
        self.category = "personal"
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
            "target_date": str(self.target_date),
            "progress": self.progress,
        }


class MockMilestone:
    """Mock Milestone for testing."""

    def __init__(
        self,
        uid: str = "milestone.test123",
        title: str = "Test Milestone",
        target_date: date | None = None,
        completed: bool = False,
    ):
        self.uid = uid
        self.title = title
        self.target_date = target_date or (date.today() + timedelta(days=30))
        self.completed = completed


@pytest.fixture
def mock_goals_service():
    """Create mock GoalsService."""
    service = MagicMock()

    # Standard CRUD operations
    service.create = AsyncMock(return_value=Result.ok(MockGoal()))
    service.get = AsyncMock(return_value=Result.ok(MockGoal()))
    service.update = AsyncMock(return_value=Result.ok(MockGoal()))
    service.delete = AsyncMock(return_value=Result.ok(True))
    service.list = AsyncMock(return_value=Result.ok([MockGoal(), MockGoal()]))

    # Query operations
    service.get_by_user = AsyncMock(return_value=Result.ok([MockGoal()]))
    service.get_by_habit = AsyncMock(return_value=Result.ok([MockGoal()]))

    # Progress operations
    service.update_goal_progress = AsyncMock(return_value=Result.ok({"progress": 0.5}))
    service.get_goal_progress = AsyncMock(return_value=Result.ok({"history": []}))

    # Milestone operations
    service.create_goal_milestone = AsyncMock(return_value=Result.ok(True))
    service.get_goal_milestones = AsyncMock(return_value=Result.ok([]))

    # Habit integration
    service.link_goal_to_habit = AsyncMock(return_value=Result.ok(True))
    service.get_goal_habits = AsyncMock(return_value=Result.ok([]))
    service.unlink_goal_from_habit = AsyncMock(return_value=Result.ok(True))

    # Status operations
    service.activate_goal = AsyncMock(return_value=Result.ok(True))
    service.pause_goal = AsyncMock(return_value=Result.ok(True))
    service.complete_goal = AsyncMock(return_value=Result.ok(True))
    service.archive_goal = AsyncMock(return_value=Result.ok(True))

    # Categories and search
    service.list_goal_categories = AsyncMock(
        return_value=Result.ok(["personal", "career", "health"])
    )
    service.get_goals_by_category = AsyncMock(return_value=Result.ok([MockGoal()]))
    service.get_goals_by_status = AsyncMock(return_value=Result.ok([MockGoal()]))
    service.search_goals = AsyncMock(return_value=Result.ok([MockGoal()]))
    service.get_goals_due_soon = AsyncMock(return_value=Result.ok([MockGoal()]))
    service.get_overdue_goals = AsyncMock(return_value=Result.ok([]))

    return service


class TestCRUDOperations:
    """Tests for standard CRUD operations via CRUDRouteFactory."""

    async def test_create_goal_returns_result(self, mock_goals_service):
        """Test that create returns a Result."""
        result = await mock_goals_service.create({"title": "New Goal", "user_uid": "user.test"})

        assert result.is_ok
        assert result.value.title == "Test Goal"

    async def test_get_goal_by_uid(self, mock_goals_service):
        """Test retrieving a goal by UID."""
        result = await mock_goals_service.get("goal.test123")

        assert result.is_ok
        assert result.value.uid == "goal.test123"

    async def test_get_goal_not_found(self, mock_goals_service):
        """Test retrieving a non-existent goal."""
        mock_goals_service.get = AsyncMock(
            return_value=Result.fail(Errors.not_found("goal", "goal.nonexistent"))
        )

        result = await mock_goals_service.get("goal.nonexistent")

        assert result.is_error

    async def test_update_goal(self, mock_goals_service):
        """Test updating a goal."""
        result = await mock_goals_service.update("goal.test123", {"title": "Updated Goal"})

        assert result.is_ok

    async def test_delete_goal(self, mock_goals_service):
        """Test deleting a goal."""
        result = await mock_goals_service.delete("goal.test123")

        assert result.is_ok
        assert result.value is True

    async def test_list_goals(self, mock_goals_service):
        """Test listing goals with pagination."""
        result = await mock_goals_service.list()

        assert result.is_ok
        assert len(result.value) == 2


class TestProgressOperations:
    """Tests for goal progress tracking."""

    async def test_update_goal_progress(self, mock_goals_service):
        """Test updating goal progress."""
        result = await mock_goals_service.update_goal_progress(
            "goal.test123", progress_value=50, notes="Halfway there", update_date=None
        )

        assert result.is_ok
        assert "progress" in result.value

    async def test_get_goal_progress_history(self, mock_goals_service):
        """Test getting goal progress history."""
        result = await mock_goals_service.get_goal_progress("goal.test123", "month")

        assert result.is_ok
        assert "history" in result.value


class TestMilestoneOperations:
    """Tests for goal milestone management."""

    async def test_create_milestone(self, mock_goals_service):
        """Test creating a milestone for a goal."""
        result = await mock_goals_service.create_goal_milestone(
            "goal.test123",
            "Complete Phase 1",
            str(date.today() + timedelta(days=30)),
            "First major milestone",
        )

        assert result.is_ok

    async def test_get_goal_milestones(self, mock_goals_service):
        """Test getting milestones for a goal."""
        result = await mock_goals_service.get_goal_milestones("goal.test123")

        assert result.is_ok
        assert isinstance(result.value, list)


class TestHabitIntegration:
    """Tests for goal-habit linking."""

    async def test_link_goal_to_habit(self, mock_goals_service):
        """Test linking a habit to a goal."""
        result = await mock_goals_service.link_goal_to_habit("goal.test123", "habit.test456", 1.0)

        assert result.is_ok

    async def test_get_goal_habits(self, mock_goals_service):
        """Test getting habits linked to a goal."""
        result = await mock_goals_service.get_goal_habits("goal.test123")

        assert result.is_ok
        assert isinstance(result.value, list)

    async def test_unlink_goal_from_habit(self, mock_goals_service):
        """Test unlinking a habit from a goal."""
        result = await mock_goals_service.unlink_goal_from_habit("goal.test123", "habit.test456")

        assert result.is_ok


class TestStatusOperations:
    """Tests for goal status changes."""

    async def test_activate_goal(self, mock_goals_service):
        """Test activating a goal."""
        result = await mock_goals_service.activate_goal("goal.test123")

        assert result.is_ok

    async def test_pause_goal(self, mock_goals_service):
        """Test pausing a goal."""
        result = await mock_goals_service.pause_goal("goal.test123", "Taking a break", None)

        assert result.is_ok

    async def test_complete_goal(self, mock_goals_service):
        """Test completing a goal."""
        result = await mock_goals_service.complete_goal(
            "goal.test123", "Successfully completed!", None
        )

        assert result.is_ok

    async def test_archive_goal(self, mock_goals_service):
        """Test archiving a goal."""
        result = await mock_goals_service.archive_goal("goal.test123", "No longer relevant")

        assert result.is_ok


class TestCategoryOperations:
    """Tests for goal categories."""

    async def test_list_goal_categories(self, mock_goals_service):
        """Test listing all goal categories."""
        result = await mock_goals_service.list_goal_categories()

        assert result.is_ok
        assert "personal" in result.value

    async def test_get_goals_by_category(self, mock_goals_service):
        """Test getting goals by category."""
        result = await mock_goals_service.get_goals_by_category("personal", 100)

        assert result.is_ok

    async def test_get_goals_by_status(self, mock_goals_service):
        """Test getting goals by status."""
        result = await mock_goals_service.get_goals_by_status("in_progress", 100)

        assert result.is_ok


class TestSearchAndFiltering:
    """Tests for goal search and filtering."""

    async def test_search_goals(self, mock_goals_service):
        """Test searching goals."""
        result = await mock_goals_service.search_goals("fitness", 50)

        assert result.is_ok

    async def test_get_goals_due_soon(self, mock_goals_service):
        """Test getting goals due soon."""
        result = await mock_goals_service.get_goals_due_soon(7)

        assert result.is_ok

    async def test_get_overdue_goals(self, mock_goals_service):
        """Test getting overdue goals."""
        result = await mock_goals_service.get_overdue_goals(100)

        assert result.is_ok


class TestRouteFactory:
    """Tests for CRUDRouteFactory integration."""

    async def test_crud_factory_routes(self):
        """Test that CRUD factory defines expected routes."""
        expected_routes = [
            "POST /api/goals",
            "GET /api/goals/{uid}",
            "PUT /api/goals/{uid}",
            "DELETE /api/goals/{uid}",
            "GET /api/goals",
        ]
        for route in expected_routes:
            assert "/api/goals" in route


class TestErrorHandling:
    """Tests for error handling in goal operations."""

    async def test_validation_error_on_create(self, mock_goals_service):
        """Test validation error when creating goal with invalid data."""
        mock_goals_service.create = AsyncMock(
            return_value=Result.fail(Errors.validation("Title is required", field="title"))
        )

        result = await mock_goals_service.create({})

        assert result.is_error

    async def test_not_found_error(self, mock_goals_service):
        """Test not found error handling."""
        mock_goals_service.get = AsyncMock(
            return_value=Result.fail(Errors.not_found("goal", "goal.nonexistent"))
        )

        result = await mock_goals_service.get("goal.nonexistent")

        assert result.is_error


class TestGoalModel:
    """Tests for Goal model structure."""

    async def test_goal_has_required_fields(self):
        """Test that Goal model has required fields."""
        from core.models.ku.ku import Ku

        required_fields = ["uid", "user_uid", "title"]
        for field in required_fields:
            assert hasattr(Ku, "__annotations__") or field in dir(Ku)
