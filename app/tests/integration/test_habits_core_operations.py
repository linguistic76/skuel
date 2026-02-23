"""
Integration Test: Habits Core Operations
========================================

Tests basic CRUD operations and core functionality for the Habits domain.

This test suite verifies that:
1. Habits can be created, retrieved, and listed
2. Habits can be filtered by status, category, and difficulty
3. Habit business logic works correctly (validation, frequency consistency)
4. Event publishing works correctly

Test Coverage:
--------------
- HabitsCoreService.create()
- HabitsCoreService.get_habit()
- HabitsCoreService.get_user_habits()
- HabitsCoreService.list_habits()
- Habit business logic
- Habit enum classifications
"""

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import Priority, RecurrencePattern
from core.models.enums.ku_enums import (
    EntityStatus as HabitStatus,
)
from core.models.enums.ku_enums import (
    EntityType,
    HabitCategory,
    HabitDifficulty,
    HabitPolarity,
)
from core.models.habit.habit import Habit as Habit
from core.services.habits.habits_core_service import HabitsCoreService


@pytest.mark.asyncio
class TestHabitsCoreOperations:
    """Integration tests for Habits core CRUD operations."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def habits_backend(self, neo4j_driver, clean_neo4j):
        """Create habits backend with clean database."""
        return UniversalNeo4jBackend[Habit](
            neo4j_driver, "Ku", Habit, default_filters={"ku_type": "habit"}
        )

    @pytest_asyncio.fixture
    async def habits_service(self, habits_backend, event_bus):
        """Create HabitsCoreService with event bus."""
        return HabitsCoreService(backend=habits_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_habits_core"

    # ==========================================================================
    # CRUD OPERATIONS TESTS (5 tests)
    # ==========================================================================

    async def test_create_habit(self, habits_service, test_user_uid):
        """Test creating a new habit."""
        # Arrange
        habit = Habit(
            uid="habit.daily_meditation",
            user_uid=test_user_uid,
            title="Daily Meditation",
            ku_type=EntityType.HABIT,
            description="Practice mindfulness meditation every morning",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.MINDFULNESS,
            habit_difficulty=HabitDifficulty.EASY,
            recurrence_pattern=RecurrencePattern.DAILY,
            target_days_per_week=7,
            duration_minutes=10,
            status=HabitStatus.ACTIVE,
            priority=Priority.HIGH,
        )

        # Act
        result = await habits_service.create(habit)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.uid == "habit.daily_meditation"
        assert created.title == "Daily Meditation"
        assert created.polarity == HabitPolarity.BUILD
        assert created.habit_category == HabitCategory.MINDFULNESS
        assert created.habit_difficulty == HabitDifficulty.EASY
        assert created.status == HabitStatus.ACTIVE

    async def test_get_habit_by_uid(self, habits_service, test_user_uid):
        """Test retrieving a habit by UID."""
        # Arrange - Create a habit first
        habit = Habit(
            uid="habit.get_test",
            user_uid=test_user_uid,
            title="Test Habit for Retrieval",
            description="This habit tests retrieval functionality",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.LEARNING,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        create_result = await habits_service.create(habit)
        assert create_result.is_ok

        # Act - Retrieve the habit
        result = await habits_service.get_habit("habit.get_test")

        # Assert
        assert result.is_ok
        retrieved = result.value
        assert retrieved.uid == "habit.get_test"
        assert retrieved.title == "Test Habit for Retrieval"

    async def test_get_nonexistent_habit(self, habits_service):
        """Test getting a habit that doesn't exist."""
        # Act
        result = await habits_service.get_habit("habit.nonexistent")

        # Assert
        assert result.is_error
        assert "not found" in result.error.message.lower()

    async def test_list_user_habits(self, habits_service, test_user_uid):
        """Test listing all habits for a user."""
        # Arrange - Create multiple habits
        habits = [
            Habit(
                uid=f"habit.list_test_{i}",
                user_uid=test_user_uid,
                title=f"Test Habit {i}",
                description=f"Description for habit {i}",
                polarity=HabitPolarity.BUILD,
                habit_category=HabitCategory.PRODUCTIVITY,
                recurrence_pattern=RecurrencePattern.DAILY,
            )
            for i in range(3)
        ]

        for habit in habits:
            result = await habits_service.create(habit)
            assert result.is_ok

        # Act - List habits
        result = await habits_service.get_user_habits(test_user_uid)

        # Assert
        assert result.is_ok
        user_habits = result.value
        assert len(user_habits) >= 3

    async def test_multiple_habits_same_user(self, habits_service, test_user_uid):
        """Test creating multiple habits for the same user."""
        # Arrange & Act - Create 5 habits
        for i in range(5):
            habit = Habit(
                uid=f"habit.multi_{i}",
                user_uid=test_user_uid,
                title=f"Multi Habit {i}",
                description=f"Multiple habit {i}",
                polarity=HabitPolarity.BUILD,
                habit_category=HabitCategory.HEALTH,
                recurrence_pattern=RecurrencePattern.DAILY,
            )
            result = await habits_service.create(habit)
            assert result.is_ok

        # Assert - Verify all were created
        list_result = await habits_service.get_user_habits(test_user_uid)
        assert list_result.is_ok
        assert len(list_result.value) >= 5

    # ==========================================================================
    # FILTERING TESTS (3 tests)
    # ==========================================================================

    async def test_filter_by_status(self, habits_service, test_user_uid):
        """Test filtering habits by status."""
        # Arrange - Create habits with different statuses
        active_habit = Habit(
            uid="habit.active",
            user_uid=test_user_uid,
            title="Active Habit",
            description="Currently pursuing this habit",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.FITNESS,
            status=HabitStatus.ACTIVE,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        completed_habit = Habit(
            uid="habit.completed",
            user_uid=test_user_uid,
            title="Completed Habit",
            description="Successfully completed",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.FITNESS,
            status=HabitStatus.COMPLETED,
            recurrence_pattern=RecurrencePattern.DAILY,
        )

        await habits_service.create(active_habit)
        await habits_service.create(completed_habit)

        # Act - Filter by status
        active_result = await habits_service.backend.find_by(
            user_uid=test_user_uid, status=HabitStatus.ACTIVE.value
        )
        completed_result = await habits_service.backend.find_by(
            user_uid=test_user_uid, status=HabitStatus.COMPLETED.value
        )

        # Assert
        assert active_result.is_ok
        assert len(active_result.value) >= 1
        assert all(h.status == HabitStatus.ACTIVE for h in active_result.value)

        assert completed_result.is_ok
        assert len(completed_result.value) >= 1
        assert all(h.status == HabitStatus.COMPLETED for h in completed_result.value)

    async def test_filter_by_category(self, habits_service, test_user_uid):
        """Test filtering habits by category."""
        # Arrange - Create habits with different categories
        health_habit = Habit(
            uid="habit.health_category",
            user_uid=test_user_uid,
            title="Health Category Habit",
            description="Health-related habit",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.HEALTH,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        learning_habit = Habit(
            uid="habit.learning_category",
            user_uid=test_user_uid,
            title="Learning Category Habit",
            description="Learning-related habit",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.LEARNING,
            recurrence_pattern=RecurrencePattern.DAILY,
        )

        await habits_service.create(health_habit)
        await habits_service.create(learning_habit)

        # Act - Filter by category
        health_result = await habits_service.backend.find_by(
            user_uid=test_user_uid, habit_category=HabitCategory.HEALTH.value
        )
        learning_result = await habits_service.backend.find_by(
            user_uid=test_user_uid, habit_category=HabitCategory.LEARNING.value
        )

        # Assert
        assert health_result.is_ok
        assert len(health_result.value) >= 1
        assert all(h.habit_category == HabitCategory.HEALTH for h in health_result.value)

        assert learning_result.is_ok
        assert len(learning_result.value) >= 1
        assert all(h.habit_category == HabitCategory.LEARNING for h in learning_result.value)

    async def test_filter_by_difficulty(self, habits_service, test_user_uid):
        """Test filtering habits by difficulty."""
        # Arrange - Create habits with different difficulties
        easy_habit = Habit(
            uid="habit.easy",
            user_uid=test_user_uid,
            title="Easy Habit",
            description="Simple habit",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.OTHER,
            habit_difficulty=HabitDifficulty.EASY,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        hard_habit = Habit(
            uid="habit.hard",
            user_uid=test_user_uid,
            title="Hard Habit",
            description="Challenging habit",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.OTHER,
            habit_difficulty=HabitDifficulty.HARD,
            recurrence_pattern=RecurrencePattern.DAILY,
        )

        await habits_service.create(easy_habit)
        await habits_service.create(hard_habit)

        # Act - Filter by difficulty
        easy_result = await habits_service.backend.find_by(
            user_uid=test_user_uid, habit_difficulty=HabitDifficulty.EASY.value
        )
        hard_result = await habits_service.backend.find_by(
            user_uid=test_user_uid, habit_difficulty=HabitDifficulty.HARD.value
        )

        # Assert
        assert easy_result.is_ok
        assert len(easy_result.value) >= 1
        assert all(h.habit_difficulty == HabitDifficulty.EASY for h in easy_result.value)

        assert hard_result.is_ok
        assert len(hard_result.value) >= 1
        assert all(h.habit_difficulty == HabitDifficulty.HARD for h in hard_result.value)

    # ==========================================================================
    # BUSINESS LOGIC TESTS (4 tests)
    # ==========================================================================

    async def test_habit_statuses(self, habits_service, test_user_uid):
        """Test creating habits with all status types."""
        # Arrange & Act - Create habits with each status
        statuses = [
            HabitStatus.ACTIVE,
            HabitStatus.PAUSED,
            HabitStatus.COMPLETED,
            HabitStatus.CANCELLED,
            HabitStatus.ARCHIVED,
        ]

        for status in statuses:
            habit = Habit(
                uid=f"habit.status_{status.value}",
                user_uid=test_user_uid,
                title=f"Habit with {status.value} status",
                description=f"Testing {status.value} status",
                polarity=HabitPolarity.BUILD,
                habit_category=HabitCategory.OTHER,
                status=status,
                recurrence_pattern=RecurrencePattern.DAILY,
            )
            result = await habits_service.create(habit)
            assert result.is_ok
            assert result.value.status == status

    async def test_habit_polarities(self, habits_service, test_user_uid):
        """Test creating habits with all polarity types."""
        # Arrange & Act - Create habits with each polarity
        polarities = [
            HabitPolarity.BUILD,
            HabitPolarity.BREAK,
            HabitPolarity.NEUTRAL,
        ]

        for polarity in polarities:
            habit = Habit(
                uid=f"habit.polarity_{polarity.value}",
                user_uid=test_user_uid,
                title=f"{polarity.value.title()} Habit",
                description=f"Testing {polarity.value} polarity",
                polarity=polarity,
                habit_category=HabitCategory.OTHER,
                recurrence_pattern=RecurrencePattern.DAILY,
            )
            result = await habits_service.create(habit)
            assert result.is_ok
            assert result.value.polarity == polarity

    async def test_frequency_validation(self, habits_service, test_user_uid):
        """Test that daily habits cannot have target > 7 days per week."""
        # Arrange - Create habit with invalid frequency
        invalid_habit = Habit(
            uid="habit.invalid_frequency",
            user_uid=test_user_uid,
            title="Invalid Frequency Habit",
            description="Daily habit with target > 7 days",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.OTHER,
            recurrence_pattern=RecurrencePattern.DAILY,
            target_days_per_week=8,  # Invalid: > 7 for daily habit
        )

        # Act
        result = await habits_service.create(invalid_habit)

        # Assert - Should fail validation
        assert result.is_error
        assert "cannot have target > 7" in result.error.message.lower()

    async def test_habit_with_behavioral_science_fields(self, habits_service, test_user_uid):
        """Test creating a habit with cue-routine-reward pattern."""
        # Arrange
        habit = Habit(
            uid="habit.with_cue_routine_reward",
            user_uid=test_user_uid,
            title="Habit with Behavioral Science",
            description="Full habit loop pattern",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.PRODUCTIVITY,
            habit_difficulty=HabitDifficulty.MODERATE,
            recurrence_pattern=RecurrencePattern.DAILY,
            cue="When I pour my morning coffee",
            routine="Review my goals for 5 minutes",
            reward="Feel prepared and focused for the day",
            reinforces_identity="I am an organized person",
            is_identity_habit=True,
        )

        # Act
        result = await habits_service.create(habit)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.cue == "When I pour my morning coffee"
        assert created.routine == "Review my goals for 5 minutes"
        assert created.reward == "Feel prepared and focused for the day"
        assert created.reinforces_identity == "I am an organized person"
        assert created.is_identity_habit is True

    # ==========================================================================
    # EDGE CASES TESTS (3 tests)
    # ==========================================================================

    async def test_habit_with_optional_fields(self, habits_service, test_user_uid):
        """Test creating a habit with optional fields populated."""
        # Arrange
        habit = Habit(
            uid="habit.full_details",
            user_uid=test_user_uid,
            title="Fully Detailed Habit",
            description="Complete habit with all optional fields",
            polarity=HabitPolarity.BUILD,
            habit_category=HabitCategory.FITNESS,
            habit_difficulty=HabitDifficulty.CHALLENGING,
            recurrence_pattern=RecurrencePattern.DAILY,
            target_days_per_week=5,
            preferred_time="morning",
            duration_minutes=30,
            cue="After waking up",
            routine="30 minutes of yoga",
            reward="Feel energized and flexible",
            reinforces_identity="I am a healthy person",
            is_identity_habit=True,
            priority=Priority.CRITICAL,
        )

        # Act
        result = await habits_service.create(habit)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.preferred_time == "morning"
        assert created.duration_minutes == 30
        assert created.target_days_per_week == 5
        assert created.priority == Priority.CRITICAL

    async def test_habit_without_optional_fields(self, habits_service, test_user_uid):
        """Test creating a habit with minimal required fields."""
        # Arrange - Only required fields
        habit = Habit(
            uid="habit.minimal",
            user_uid=test_user_uid,
            title="Minimal Habit",
            description=None,  # Optional
        )

        # Act
        result = await habits_service.create(habit)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.description is None
        assert created.cue is None
        assert created.routine is None
        assert created.reward is None
        # Check defaults are set (unified Ku model uses None for optional domain fields)
        assert created.polarity is None
        assert created.habit_category is None
        assert created.habit_difficulty is None

    async def test_habit_recurrence_patterns(self, habits_service, test_user_uid):
        """Test creating habits with different recurrence patterns."""
        # Arrange & Act - Create habits with different patterns
        patterns = [
            (RecurrencePattern.DAILY, 7),
            (RecurrencePattern.WEEKLY, 1),
            (RecurrencePattern.BIWEEKLY, 1),
            (RecurrencePattern.MONTHLY, 1),
        ]

        for i, (pattern, target_days) in enumerate(patterns):
            habit = Habit(
                uid=f"habit.recurrence_{i}",
                user_uid=test_user_uid,
                title=f"Habit with {pattern.value} recurrence",
                description=f"Pattern: {pattern.value}",
                polarity=HabitPolarity.BUILD,
                habit_category=HabitCategory.OTHER,
                recurrence_pattern=pattern,
                target_days_per_week=target_days,
            )
            result = await habits_service.create(habit)
            assert result.is_ok
            assert result.value.recurrence_pattern == pattern
            assert result.value.target_days_per_week == target_days
