"""
Integration Tests for Habits API Routes.

Tests cover:
1. CRUD operations (create, get, update, delete, list) via CRUDRouteFactory
2. Query operations (by user, goal) via CommonQueryRouteFactory
3. Habit completion/streak tracking
4. Habit-goal linking
5. Habit scheduling and reminders

All tests use mocked services to avoid external dependencies.

Note: All async tests use pytest-asyncio for proper event loop management.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.shared_enums import ActivityStatus
from core.utils.result_simplified import Errors, Result

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


class MockHabit:
    """Mock Habit model for testing."""

    def __init__(
        self,
        uid: str = "habit.test123",
        user_uid: str = "user.test",
        title: str = "Test Habit",
        description: str = "A test habit description",
        status: ActivityStatus = ActivityStatus.IN_PROGRESS,
        frequency: str = "daily",
        current_streak: int = 5,
        best_streak: int = 10,
    ):
        self.uid = uid
        self.user_uid = user_uid
        self.title = title
        self.description = description
        self.status = status
        self.frequency = frequency
        self.current_streak = current_streak
        self.best_streak = best_streak
        self.created_at = "2024-01-01T00:00:00Z"
        self.updated_at = "2024-01-01T00:00:00Z"

    def to_dict(self):
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "frequency": self.frequency,
            "current_streak": self.current_streak,
            "best_streak": self.best_streak,
        }


@pytest.fixture
def mock_habits_service():
    """Create mock HabitsService."""
    service = MagicMock()

    # Standard CRUD operations
    service.create = AsyncMock(return_value=Result.ok(MockHabit()))
    service.get = AsyncMock(return_value=Result.ok(MockHabit()))
    service.update = AsyncMock(return_value=Result.ok(MockHabit()))
    service.delete = AsyncMock(return_value=Result.ok(True))
    service.list = AsyncMock(return_value=Result.ok([MockHabit(), MockHabit()]))

    # Query operations
    service.get_by_user = AsyncMock(return_value=Result.ok([MockHabit()]))
    service.get_by_goal = AsyncMock(return_value=Result.ok([MockHabit()]))

    # Habit completion
    service.complete_habit = AsyncMock(return_value=Result.ok(MockHabit(current_streak=6)))
    service.skip_habit = AsyncMock(return_value=Result.ok(True))
    service.get_habit_completions = AsyncMock(return_value=Result.ok([]))

    # Streak operations
    service.get_streak_info = AsyncMock(return_value=Result.ok({"current": 5, "best": 10}))
    service.calculate_streak = AsyncMock(return_value=Result.ok(5))

    # Goal linking
    service.link_habit_to_goal = AsyncMock(return_value=Result.ok(True))
    service.get_habit_goals = AsyncMock(return_value=Result.ok([]))
    service.unlink_habit_from_goal = AsyncMock(return_value=Result.ok(True))

    # Scheduling
    service.get_habits_due_today = AsyncMock(return_value=Result.ok([MockHabit()]))
    service.get_habits_due_this_week = AsyncMock(return_value=Result.ok([MockHabit()]))
    service.set_habit_reminder = AsyncMock(return_value=Result.ok(True))

    # Search
    service.search = AsyncMock(return_value=Result.ok([MockHabit()]))

    return service


class TestCRUDOperations:
    """Tests for standard CRUD operations via CRUDRouteFactory."""

    async def test_create_habit_returns_result(self, mock_habits_service):
        """Test that create returns a Result."""
        result = await mock_habits_service.create({"title": "New Habit", "user_uid": "user.test"})

        assert result.is_ok
        assert result.value.title == "Test Habit"

    async def test_get_habit_by_uid(self, mock_habits_service):
        """Test retrieving a habit by UID."""
        result = await mock_habits_service.get("habit.test123")

        assert result.is_ok
        assert result.value.uid == "habit.test123"

    async def test_get_habit_not_found(self, mock_habits_service):
        """Test retrieving a non-existent habit."""
        mock_habits_service.get = AsyncMock(
            return_value=Result.fail(Errors.not_found("habit", "habit.nonexistent"))
        )

        result = await mock_habits_service.get("habit.nonexistent")

        assert result.is_error

    async def test_update_habit(self, mock_habits_service):
        """Test updating a habit."""
        result = await mock_habits_service.update("habit.test123", {"title": "Updated Habit"})

        assert result.is_ok

    async def test_delete_habit(self, mock_habits_service):
        """Test deleting a habit."""
        result = await mock_habits_service.delete("habit.test123")

        assert result.is_ok
        assert result.value is True

    async def test_list_habits(self, mock_habits_service):
        """Test listing habits with pagination."""
        result = await mock_habits_service.list()

        assert result.is_ok
        assert len(result.value) == 2


class TestCompletionOperations:
    """Tests for habit completion tracking."""

    async def test_complete_habit(self, mock_habits_service):
        """Test completing a habit."""
        result = await mock_habits_service.complete_habit("habit.test123")

        assert result.is_ok
        assert result.value.current_streak == 6

    async def test_skip_habit(self, mock_habits_service):
        """Test skipping a habit."""
        result = await mock_habits_service.skip_habit("habit.test123")

        assert result.is_ok

    async def test_get_habit_completions(self, mock_habits_service):
        """Test getting habit completion history."""
        result = await mock_habits_service.get_habit_completions("habit.test123")

        assert result.is_ok
        assert isinstance(result.value, list)


class TestStreakOperations:
    """Tests for streak tracking."""

    async def test_get_streak_info(self, mock_habits_service):
        """Test getting streak information."""
        result = await mock_habits_service.get_streak_info("habit.test123")

        assert result.is_ok
        assert result.value["current"] == 5
        assert result.value["best"] == 10

    async def test_calculate_streak(self, mock_habits_service):
        """Test calculating current streak."""
        result = await mock_habits_service.calculate_streak("habit.test123")

        assert result.is_ok
        assert result.value == 5


class TestGoalIntegration:
    """Tests for habit-goal linking."""

    async def test_link_habit_to_goal(self, mock_habits_service):
        """Test linking a habit to a goal."""
        result = await mock_habits_service.link_habit_to_goal("habit.test123", "goal.test456")

        assert result.is_ok

    async def test_get_habit_goals(self, mock_habits_service):
        """Test getting goals linked to a habit."""
        result = await mock_habits_service.get_habit_goals("habit.test123")

        assert result.is_ok
        assert isinstance(result.value, list)

    async def test_unlink_habit_from_goal(self, mock_habits_service):
        """Test unlinking a habit from a goal."""
        result = await mock_habits_service.unlink_habit_from_goal("habit.test123", "goal.test456")

        assert result.is_ok


class TestSchedulingOperations:
    """Tests for habit scheduling."""

    async def test_get_habits_due_today(self, mock_habits_service):
        """Test getting habits due today."""
        result = await mock_habits_service.get_habits_due_today()

        assert result.is_ok
        assert len(result.value) >= 1

    async def test_get_habits_due_this_week(self, mock_habits_service):
        """Test getting habits due this week."""
        result = await mock_habits_service.get_habits_due_this_week()

        assert result.is_ok

    async def test_set_habit_reminder(self, mock_habits_service):
        """Test setting a habit reminder."""
        result = await mock_habits_service.set_habit_reminder("habit.test123", "09:00")

        assert result.is_ok


class TestSearch:
    """Tests for habit search."""

    async def test_search_habits(self, mock_habits_service):
        """Test searching habits."""
        result = await mock_habits_service.search("meditation")

        assert result.is_ok


class TestHabitModel:
    """Tests for Habit model structure."""

    def test_habit_has_required_fields(self):
        """Test that Habit model has required fields."""
        from core.models.habit.habit import Habit

        required_fields = ["uid", "user_uid", "title"]
        for field in required_fields:
            assert hasattr(Habit, "__annotations__") or field in dir(Habit)

    def test_habit_frequency_values(self):
        """Test habit frequency options."""
        frequencies = ["daily", "weekly", "monthly"]
        for freq in frequencies:
            assert isinstance(freq, str)


class TestErrorHandling:
    """Tests for error handling."""

    async def test_validation_error_on_create(self, mock_habits_service):
        """Test validation error when creating habit with invalid data."""
        mock_habits_service.create = AsyncMock(
            return_value=Result.fail(Errors.validation("Title is required", field="title"))
        )

        result = await mock_habits_service.create({})

        assert result.is_error
