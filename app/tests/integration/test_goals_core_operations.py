"""
Integration Test: Goals Core Operations
========================================

Tests basic CRUD operations and core functionality for the Goals domain.

This test suite verifies that:
1. Goals can be created, retrieved, and listed
2. Goals can be filtered by status, priority, and timeframe
3. Goal business logic works correctly (validation, progress tracking)
4. Event publishing works correctly

Test Coverage:
--------------
- GoalsCoreService.create()
- GoalsCoreService.get()
- GoalsCoreService.backend.find_by()
- Goal business logic
- Goal enum classifications
"""

from datetime import date, timedelta

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import Domain, EntityStatus, Priority
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.goal.goal import Goal
from core.services.goals.goals_core_service import GoalsCoreService


@pytest.mark.asyncio
class TestGoalsCoreOperations:
    """Integration tests for Goals core CRUD operations."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def goals_backend(self, neo4j_driver, clean_neo4j):
        """Create goals backend with clean database."""
        return UniversalNeo4jBackend[Goal](
            neo4j_driver, "Entity", Goal, default_filters={"ku_type": "goal"}
        )

    @pytest_asyncio.fixture
    async def goals_service(self, goals_backend, event_bus):
        """Create GoalsCoreService with event bus."""
        return GoalsCoreService(backend=goals_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_goals_core"

    # ==========================================================================
    # CRUD OPERATIONS TESTS (5 tests)
    # ==========================================================================

    async def test_create_goal(self, goals_service, test_user_uid):
        """Test creating a new goal."""
        # Arrange
        today = date.today()
        goal = Goal(
            uid="goal.learn_python",
            user_uid=test_user_uid,
            title="Learn Python Programming",
            description="Master Python for data science and automation",
            goal_type=GoalType.LEARNING,
            domain=Domain.TECH,
            timeframe=GoalTimeframe.QUARTERLY,
            measurement_type=MeasurementType.PERCENTAGE,
            target_value=100.0,
            current_value=0.0,
            start_date=today,
            target_date=today + timedelta(days=90),
            status=EntityStatus.ACTIVE,
            priority=Priority.HIGH,
        )

        # Act
        result = await goals_service.create(goal)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.uid == "goal.learn_python"
        assert created.title == "Learn Python Programming"
        assert created.goal_type == GoalType.LEARNING
        assert created.status == EntityStatus.ACTIVE
        assert created.priority == Priority.HIGH

    async def test_get_goal_by_uid(self, goals_service, test_user_uid):
        """Test retrieving a goal by UID."""
        # Arrange - Create a goal first
        goal = Goal(
            uid="goal.get_test",
            user_uid=test_user_uid,
            title="Test Goal for Retrieval",
            description="This goal tests retrieval functionality",
            goal_type=GoalType.OUTCOME,
            domain=Domain.PERSONAL,
            timeframe=GoalTimeframe.MONTHLY,
        )
        create_result = await goals_service.create(goal)
        assert create_result.is_ok

        # Act - Retrieve the goal
        result = await goals_service.get("goal.get_test")

        # Assert
        assert result.is_ok
        retrieved = result.value
        assert retrieved.uid == "goal.get_test"
        assert retrieved.title == "Test Goal for Retrieval"

    async def test_get_nonexistent_goal(self, goals_service):
        """Test getting a goal that doesn't exist."""
        # Act
        result = await goals_service.get("goal.nonexistent")

        # Assert
        assert result.is_error
        assert "not found" in result.error.message.lower()

    async def test_list_user_goals(self, goals_service, test_user_uid):
        """Test listing all goals for a user."""
        # Arrange - Create multiple goals
        goals = [
            Goal(
                uid=f"goal.list_test_{i}",
                user_uid=test_user_uid,
                title=f"Test Goal {i}",
                description=f"Description for goal {i}",
                goal_type=GoalType.OUTCOME,
                domain=Domain.PERSONAL,
                timeframe=GoalTimeframe.WEEKLY,
            )
            for i in range(3)
        ]

        for goal in goals:
            result = await goals_service.create(goal)
            assert result.is_ok

        # Act - List goals
        result = await goals_service.backend.find_by(user_uid=test_user_uid)

        # Assert
        assert result.is_ok
        user_goals = result.value
        assert len(user_goals) >= 3

    async def test_multiple_goals_same_user(self, goals_service, test_user_uid):
        """Test creating multiple goals for the same user."""
        # Arrange & Act - Create 5 goals
        for i in range(5):
            goal = Goal(
                uid=f"goal.multi_{i}",
                user_uid=test_user_uid,
                title=f"Multi Goal {i}",
                description=f"Multiple goal {i}",
                goal_type=GoalType.PROCESS,
                domain=Domain.HEALTH,
                timeframe=GoalTimeframe.MONTHLY,
            )
            result = await goals_service.create(goal)
            assert result.is_ok

        # Assert - Verify all were created
        list_result = await goals_service.backend.find_by(user_uid=test_user_uid)
        assert list_result.is_ok
        assert len(list_result.value) >= 5

    # ==========================================================================
    # FILTERING TESTS (3 tests)
    # ==========================================================================

    async def test_filter_by_status(self, goals_service, test_user_uid):
        """Test filtering goals by status."""
        # Arrange - Create goals with different statuses
        active_goal = Goal(
            uid="goal.active",
            user_uid=test_user_uid,
            title="Active Goal",
            description="Currently pursuing this goal",
            goal_type=GoalType.OUTCOME,
            domain=Domain.PERSONAL,
            status=EntityStatus.ACTIVE,
        )
        achieved_goal = Goal(
            uid="goal.achieved",
            user_uid=test_user_uid,
            title="Achieved Goal",
            description="Successfully completed",
            goal_type=GoalType.OUTCOME,
            domain=Domain.PERSONAL,
            status=EntityStatus.COMPLETED,
        )

        await goals_service.create(active_goal)
        await goals_service.create(achieved_goal)

        # Act - Filter by status
        active_result = await goals_service.backend.find_by(
            user_uid=test_user_uid, status=EntityStatus.ACTIVE.value
        )
        achieved_result = await goals_service.backend.find_by(
            user_uid=test_user_uid, status=EntityStatus.COMPLETED.value
        )

        # Assert
        assert active_result.is_ok
        assert len(active_result.value) >= 1
        assert all(g.status == EntityStatus.ACTIVE for g in active_result.value)

        assert achieved_result.is_ok
        assert len(achieved_result.value) >= 1
        assert all(g.status == EntityStatus.COMPLETED for g in achieved_result.value)

    async def test_filter_by_priority(self, goals_service, test_user_uid):
        """Test filtering goals by priority."""
        # Arrange - Create goals with different priorities
        high_goal = Goal(
            uid="goal.high_priority",
            user_uid=test_user_uid,
            title="High Priority Goal",
            description="Critical goal",
            goal_type=GoalType.OUTCOME,
            domain=Domain.BUSINESS,
            priority=Priority.HIGH,
        )
        low_goal = Goal(
            uid="goal.low_priority",
            user_uid=test_user_uid,
            title="Low Priority Goal",
            description="Nice to have",
            goal_type=GoalType.OUTCOME,
            domain=Domain.PERSONAL,
            priority=Priority.LOW,
        )

        await goals_service.create(high_goal)
        await goals_service.create(low_goal)

        # Act - Filter by priority
        high_result = await goals_service.backend.find_by(
            user_uid=test_user_uid, priority=Priority.HIGH.value
        )
        low_result = await goals_service.backend.find_by(
            user_uid=test_user_uid, priority=Priority.LOW.value
        )

        # Assert
        assert high_result.is_ok
        assert len(high_result.value) >= 1
        assert all(g.priority == Priority.HIGH for g in high_result.value)

        assert low_result.is_ok
        assert len(low_result.value) >= 1
        assert all(g.priority == Priority.LOW for g in low_result.value)

    async def test_filter_by_timeframe(self, goals_service, test_user_uid):
        """Test filtering goals by timeframe."""
        # Arrange - Create goals with different timeframes
        weekly_goal = Goal(
            uid="goal.weekly",
            user_uid=test_user_uid,
            title="Weekly Goal",
            description="Short-term goal",
            goal_type=GoalType.PROCESS,
            domain=Domain.HEALTH,
            timeframe=GoalTimeframe.WEEKLY,
        )
        yearly_goal = Goal(
            uid="goal.yearly",
            user_uid=test_user_uid,
            title="Yearly Goal",
            description="Long-term goal",
            goal_type=GoalType.MILESTONE,
            domain=Domain.BUSINESS,
            timeframe=GoalTimeframe.YEARLY,
        )

        await goals_service.create(weekly_goal)
        await goals_service.create(yearly_goal)

        # Act - Filter by timeframe
        weekly_result = await goals_service.backend.find_by(
            user_uid=test_user_uid, timeframe=GoalTimeframe.WEEKLY.value
        )
        yearly_result = await goals_service.backend.find_by(
            user_uid=test_user_uid, timeframe=GoalTimeframe.YEARLY.value
        )

        # Assert
        assert weekly_result.is_ok
        assert len(weekly_result.value) >= 1
        assert all(g.timeframe == GoalTimeframe.WEEKLY for g in weekly_result.value)

        assert yearly_result.is_ok
        assert len(yearly_result.value) >= 1
        assert all(g.timeframe == GoalTimeframe.YEARLY for g in yearly_result.value)

    # ==========================================================================
    # BUSINESS LOGIC TESTS (4 tests)
    # ==========================================================================

    async def test_goal_statuses(self, goals_service, test_user_uid):
        """Test creating goals with all status types."""
        # Arrange & Act - Create goals with each status
        statuses = [
            EntityStatus.DRAFT,
            EntityStatus.ACTIVE,
            EntityStatus.PAUSED,
            EntityStatus.COMPLETED,
            EntityStatus.CANCELLED,
        ]

        for status in statuses:
            goal = Goal(
                uid=f"goal.status_{status.value}",
                user_uid=test_user_uid,
                title=f"Goal with {status.value} status",
                description=f"Testing {status.value} status",
                goal_type=GoalType.OUTCOME,
                domain=Domain.PERSONAL,
                status=status,
            )
            result = await goals_service.create(goal)
            assert result.is_ok
            assert result.value.status == status

    async def test_goal_types(self, goals_service, test_user_uid):
        """Test creating goals with all goal types."""
        # Arrange & Act - Create goals with each type
        goal_types = [
            GoalType.OUTCOME,
            GoalType.PROCESS,
            GoalType.LEARNING,
            GoalType.PROJECT,
            GoalType.MILESTONE,
        ]

        for goal_type in goal_types:
            goal = Goal(
                uid=f"goal.type_{goal_type.value}",
                user_uid=test_user_uid,
                title=f"{goal_type.value.title()} Goal",
                description=f"Testing {goal_type.value} type",
                goal_type=goal_type,
                domain=Domain.TECH,
            )
            result = await goals_service.create(goal)
            assert result.is_ok
            assert result.value.goal_type == goal_type

    async def test_date_validation(self, goals_service, test_user_uid):
        """Test that target date must be after start date."""
        # Arrange - Create goal with invalid dates (target before start)
        today = date.today()
        invalid_goal = Goal(
            uid="goal.invalid_dates",
            user_uid=test_user_uid,
            title="Invalid Date Goal",
            description="Target date is before start date",
            goal_type=GoalType.OUTCOME,
            domain=Domain.PERSONAL,
            start_date=today,
            target_date=today - timedelta(days=10),  # Invalid: before start
        )

        # Act
        result = await goals_service.create(invalid_goal)

        # Assert - Should fail validation
        assert result.is_error
        assert "after start date" in result.error.message.lower()

    async def test_goal_with_progress_tracking(self, goals_service, test_user_uid):
        """Test creating a goal with progress tracking fields."""
        # Arrange
        goal = Goal(
            uid="goal.with_progress",
            user_uid=test_user_uid,
            title="Goal with Progress Tracking",
            description="Track progress numerically",
            goal_type=GoalType.OUTCOME,
            domain=Domain.HEALTH,
            measurement_type=MeasurementType.NUMERIC,
            target_value=100.0,
            current_value=25.0,
            unit_of_measurement="miles",
            progress_percentage=25.0,
            why_important="Improve cardiovascular health",
            success_criteria="Complete 100 miles of running",
        )

        # Act
        result = await goals_service.create(goal)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.measurement_type == MeasurementType.NUMERIC
        assert created.target_value == 100.0
        assert created.current_value == 25.0
        assert created.unit_of_measurement == "miles"
        assert created.progress_percentage == 25.0
        assert created.calculate_progress() == 0.25  # 25/100 = 0.25 (0.0-1.0 scale)

    # ==========================================================================
    # EDGE CASES TESTS (3 tests)
    # ==========================================================================

    async def test_goal_with_optional_fields(self, goals_service, test_user_uid):
        """Test creating a goal with optional fields populated."""
        # Arrange
        today = date.today()
        goal = Goal(
            uid="goal.full_details",
            user_uid=test_user_uid,
            title="Fully Detailed Goal",
            description="Complete goal with all optional fields",
            vision_statement="Become a senior software engineer",
            goal_type=GoalType.LEARNING,
            domain=Domain.TECH,
            timeframe=GoalTimeframe.YEARLY,
            measurement_type=MeasurementType.PERCENTAGE,
            target_value=100.0,
            start_date=today,
            target_date=today + timedelta(days=365),
            why_important="Career advancement and skill development",
            success_criteria="Complete advanced courses and build 3 projects",
            potential_obstacles=("Time constraints", "Complex topics"),
            strategies=("Daily practice", "Seek mentorship", "Join community"),
            priority=Priority.CRITICAL,
            tags=("career", "learning", "tech"),
        )

        # Act
        result = await goals_service.create(goal)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.vision_statement == "Become a senior software engineer"
        assert len(created.potential_obstacles) == 2
        assert len(created.strategies) == 3
        assert len(created.tags) == 3
        assert "career" in created.tags

    async def test_goal_without_optional_fields(self, goals_service, test_user_uid):
        """Test creating a goal with minimal required fields."""
        # Arrange - Only required fields
        goal = Goal(
            uid="goal.minimal",
            user_uid=test_user_uid,
            title="Minimal Goal",
            description=None,  # Optional
            goal_type=GoalType.OUTCOME,
            domain=Domain.PERSONAL,
        )

        # Act
        result = await goals_service.create(goal)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.description is None
        assert created.vision_statement is None
        assert created.why_important is None
        assert len(created.tags) == 0

    async def test_goal_date_range(self, goals_service, test_user_uid):
        """Test creating goals with different date ranges."""
        # Arrange & Act - Create goals with different timeframes
        today = date.today()
        date_ranges = [
            (today, today + timedelta(days=7)),  # Weekly
            (today, today + timedelta(days=30)),  # Monthly
            (today, today + timedelta(days=90)),  # Quarterly
        ]

        for i, (start, target) in enumerate(date_ranges):
            goal = Goal(
                uid=f"goal.date_range_{i}",
                user_uid=test_user_uid,
                title=f"Goal with date range {i}",
                description=f"Start {start}, target {target}",
                goal_type=GoalType.OUTCOME,
                domain=Domain.PERSONAL,
                start_date=start,
                target_date=target,
            )
            result = await goals_service.create(goal)
            assert result.is_ok
            # Neo4j stores dates as strings, so compare string representations
            assert str(result.value.start_date) == str(start)
            assert str(result.value.target_date) == str(target)
