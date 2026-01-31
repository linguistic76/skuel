"""
Integration Test: Habit→Goal Event-Driven Progress Updates
=============================================================

Tests Phase 4 event-driven architecture for cross-domain dependencies.

This test suite verifies that:
1. HabitCompleted events trigger goal progress updates
2. GoalsProgressService.handle_habit_completed() receives events
3. Goal progress is calculated correctly based on habit streaks
4. GoalProgressUpdated events are published when progress changes
5. GoalAchieved events are published when goals reach 100%
6. Multiple goals can be updated from a single habit completion
7. Different goal measurement types are handled correctly

Event Flow:
-----------
Habit completed → HabitCompleted event → GoalsProgressService.handle_habit_completed()
    → Query Neo4j for linked goals → Calculate new progress → Update goal
    → Publish GoalProgressUpdated event → (If 100%) Publish GoalAchieved event
"""

from datetime import date, datetime

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import GoalAchieved, GoalProgressUpdated
from core.events.habit_events import HabitCompleted
from core.models.goal.goal import Goal, MeasurementType
from core.models.habit.habit import Habit
from core.models.shared_enums import Domain, GoalStatus
from core.services.goals.goals_progress_service import GoalsProgressService


@pytest.mark.asyncio
class TestHabitGoalEventFlow:
    """Integration tests for Habit→Goal event-driven progress updates."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture and performance monitoring disabled."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def habits_backend(self, neo4j_driver, clean_neo4j):
        """Create habits backend with clean database."""
        return UniversalNeo4jBackend[Habit](neo4j_driver, "Habit", Habit)

    @pytest_asyncio.fixture
    async def goals_backend(self, neo4j_driver, clean_neo4j):
        """Create goals backend with clean database."""
        return UniversalNeo4jBackend[Goal](neo4j_driver, "Goal", Goal)

    @pytest_asyncio.fixture
    async def goals_progress_service(self, goals_backend, event_bus, neo4j_driver):
        """Create GoalsProgressService with event bus and driver."""
        return GoalsProgressService(
            backend=goals_backend,
            event_bus=event_bus,
            relationships_service=None,
            driver=neo4j_driver,  # Phase 4: For Habit→Goal Cypher queries
        )

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_habit_goal_flow"

    @pytest_asyncio.fixture
    async def habit_based_goal(self, goals_backend, test_user_uid):
        """Create a habit-based goal in Neo4j - 30-day meditation streak."""
        goal = Goal(
            uid="goal.meditation_master",
            user_uid=test_user_uid,
            title="30-Day Meditation Streak",
            description="Build a consistent meditation habit",
            domain=Domain.PERSONAL,
            measurement_type=MeasurementType.HABIT_BASED,
            progress_percentage=0.0,
            current_value=0.0,
            target_value=30.0,  # Target 30-day streak
            status=GoalStatus.ACTIVE,
            target_date=date(2025, 12, 31),
        )
        result = await goals_backend.create(goal)
        assert result.is_ok
        return result.value

    @pytest_asyncio.fixture
    async def mixed_goal(self, goals_backend, test_user_uid):
        """Create a mixed-measurement goal in Neo4j."""
        goal = Goal(
            uid="goal.healthy_lifestyle",
            user_uid=test_user_uid,
            title="Build Healthy Lifestyle",
            description="Combine habits, tasks, and knowledge for wellness",
            domain=Domain.PERSONAL,
            measurement_type=MeasurementType.MIXED,
            progress_percentage=0.0,
            current_value=0.0,
            target_value=100.0,
            status=GoalStatus.ACTIVE,
            target_date=date(2025, 12, 31),
        )
        result = await goals_backend.create(goal)
        assert result.is_ok
        return result.value

    @pytest_asyncio.fixture
    async def task_based_goal(self, goals_backend, test_user_uid):
        """Create a task-based goal to verify habit completions don't affect it."""
        goal = Goal(
            uid="goal.learn_python",
            user_uid=test_user_uid,
            title="Learn Python",
            description="Complete Python course tasks",
            domain=Domain.TECH,
            measurement_type=MeasurementType.TASK_BASED,
            progress_percentage=0.0,
            current_value=0.0,
            target_value=100.0,
            status=GoalStatus.ACTIVE,
            target_date=date(2025, 12, 31),
        )
        result = await goals_backend.create(goal)
        assert result.is_ok
        return result.value

    @pytest_asyncio.fixture
    async def linked_habit(self, habits_backend, neo4j_driver, habit_based_goal, test_user_uid):
        """Create a habit linked to the habit-based goal."""
        habit = Habit(
            uid="habit.daily_meditation",
            user_uid=test_user_uid,
            name="Daily Meditation",
            description="10 minutes of mindfulness meditation",
            current_streak=0,
            best_streak=0,
        )
        result = await habits_backend.create(habit)
        assert result.is_ok
        created_habit = result.value

        # Create graph relationship: (Goal)-[:SUPPORTS_GOAL]->(Habit)
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (goal:Goal {uid: $goal_uid})
                MATCH (habit:Habit {uid: $habit_uid})
                MERGE (goal)-[:SUPPORTS_GOAL]->(habit)
                RETURN goal.uid as goal_uid, habit.uid as habit_uid
                """,
                goal_uid=habit_based_goal.uid,
                habit_uid=habit.uid,
            )

        return created_habit

    # ========================================================================
    # BASIC EVENT FLOW TESTS
    # ========================================================================

    async def test_habit_completed_event_triggers_goal_progress_update(
        self,
        event_bus,
        goals_progress_service,
        habits_backend,
        habit_based_goal,
        linked_habit,
        test_user_uid,
    ):
        """Test that completing a habit triggers goal progress update via events."""
        # Subscribe to HabitCompleted event
        event_bus.subscribe(HabitCompleted, goals_progress_service.handle_habit_completed)

        # Update habit streak in Neo4j
        result = await habits_backend.update(linked_habit.uid, {"current_streak": 15})
        assert result.is_ok, "Setup failed: Could not update habit"

        # Publish HabitCompleted event with 15-day streak
        event = HabitCompleted(
            habit_uid=linked_habit.uid,
            user_uid=test_user_uid,
            current_streak=15,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        # Give event processing time to complete
        import asyncio

        await asyncio.sleep(0.1)

        # Verify GoalProgressUpdated event was published
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, GoalProgressUpdated)]
        assert len(progress_events) == 1
        assert progress_events[0].goal_uid == habit_based_goal.uid
        assert progress_events[0].triggered_by_habit_completion is True

    async def test_goal_progress_calculated_correctly_for_habit_based_goal(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        habits_backend,
        habit_based_goal,
        linked_habit,
        test_user_uid,
    ):
        """Test that habit-based goal progress is calculated correctly (streak / target * 100)."""
        event_bus.subscribe(HabitCompleted, goals_progress_service.handle_habit_completed)

        # Update habit streak to 15 days (goal target is 30 days)
        result = await habits_backend.update(linked_habit.uid, {"current_streak": 15})
        assert result.is_ok, "Setup failed: Could not update habit"

        # Publish HabitCompleted event
        event = HabitCompleted(
            habit_uid=linked_habit.uid,
            user_uid=test_user_uid,
            current_streak=15,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify goal progress updated correctly
        # 15-day streak / 30-day target = 50% progress
        goal_result = await goals_backend.get(habit_based_goal.uid)
        assert goal_result.is_ok
        updated_goal = goal_result.value
        assert updated_goal.progress_percentage == pytest.approx(50.0, abs=0.1)

    async def test_goal_achieved_event_published_at_100_percent(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        habits_backend,
        habit_based_goal,
        linked_habit,
        test_user_uid,
    ):
        """Test that GoalAchieved event is published when habit streak reaches target."""
        event_bus.subscribe(HabitCompleted, goals_progress_service.handle_habit_completed)

        # Update habit streak to 30 days (goal target)
        result = await habits_backend.update(linked_habit.uid, {"current_streak": 30})
        assert result.is_ok, "Setup failed: Could not update habit"

        # Publish HabitCompleted event
        event = HabitCompleted(
            habit_uid=linked_habit.uid,
            user_uid=test_user_uid,
            current_streak=30,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify GoalAchieved event was published
        history = event_bus.get_event_history()
        achieved_events = [e for e in history if isinstance(e, GoalAchieved)]
        assert len(achieved_events) == 1
        assert achieved_events[0].goal_uid == habit_based_goal.uid

        # Verify goal status updated to ACHIEVED
        goal_result = await goals_backend.get(habit_based_goal.uid)
        assert goal_result.is_ok
        assert goal_result.value.status == GoalStatus.ACHIEVED

    async def test_no_update_when_habit_not_linked_to_goal(
        self,
        event_bus,
        goals_progress_service,
        habits_backend,
        habit_based_goal,
        test_user_uid,
    ):
        """Test that unlinked habit completion doesn't affect goals."""
        event_bus.subscribe(HabitCompleted, goals_progress_service.handle_habit_completed)

        # Create habit without linking to goal
        unlinked_habit = Habit(
            uid="habit.unlinked_exercise",
            user_uid=test_user_uid,
            name="Daily Exercise",
            description="30 minutes of exercise",
            current_streak=7,
            best_streak=7,
        )
        result = await habits_backend.create(unlinked_habit)
        assert result.is_ok, "Setup failed: Could not create habit"

        # Publish HabitCompleted event for unlinked habit
        event = HabitCompleted(
            habit_uid=unlinked_habit.uid,
            user_uid=test_user_uid,
            current_streak=7,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify no GoalProgressUpdated events
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, GoalProgressUpdated)]
        assert len(progress_events) == 0

    # ========================================================================
    # GOAL MEASUREMENT TYPE TESTS
    # ========================================================================

    async def test_task_based_goal_not_updated_by_habit_completion(
        self,
        event_bus,
        goals_progress_service,
        habits_backend,
        neo4j_driver,
        task_based_goal,
        test_user_uid,
    ):
        """Test that task-based goals are not updated by habit completions."""
        event_bus.subscribe(HabitCompleted, goals_progress_service.handle_habit_completed)

        # Create habit and link to task-based goal
        habit = Habit(
            uid="habit.code_daily",
            user_uid=test_user_uid,
            name="Code Daily",
            description="1 hour of coding",
            current_streak=7,
            best_streak=7,
        )
        result = await habits_backend.create(habit)
        assert result.is_ok, "Setup failed: Could not create habit"

        # Link habit to task-based goal
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (goal:Goal {uid: $goal_uid})
                MATCH (habit:Habit {uid: $habit_uid})
                MERGE (goal)-[:SUPPORTS_GOAL]->(habit)
                """,
                goal_uid=task_based_goal.uid,
                habit_uid=habit.uid,
            )

        # Publish HabitCompleted event
        event = HabitCompleted(
            habit_uid=habit.uid,
            user_uid=test_user_uid,
            current_streak=7,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify no GoalProgressUpdated events (task-based goal should be skipped)
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, GoalProgressUpdated)]
        assert len(progress_events) == 0

    async def test_mixed_goal_updated_with_habit_contribution(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        habits_backend,
        neo4j_driver,
        mixed_goal,
        test_user_uid,
    ):
        """Test that mixed goals receive 30% contribution from habit streaks."""
        event_bus.subscribe(HabitCompleted, goals_progress_service.handle_habit_completed)

        # Set initial progress (e.g., from tasks)
        result = await goals_backend.update(mixed_goal.uid, {"progress_percentage": 20.0})
        assert result.is_ok, "Setup failed: Could not update goal"

        # Create habit and link to mixed goal
        habit = Habit(
            uid="habit.healthy_eating",
            user_uid=test_user_uid,
            name="Healthy Eating",
            description="Track meals",
            current_streak=50,  # 50% of target (100 days)
            best_streak=50,
        )
        result = await habits_backend.create(habit)
        assert result.is_ok, "Setup failed: Could not create habit"

        # Link habit to mixed goal
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (goal:Goal {uid: $goal_uid})
                MATCH (habit:Habit {uid: $habit_uid})
                MERGE (goal)-[:SUPPORTS_GOAL]->(habit)
                """,
                goal_uid=mixed_goal.uid,
                habit_uid=habit.uid,
            )

        # Publish HabitCompleted event
        event = HabitCompleted(
            habit_uid=habit.uid,
            user_uid=test_user_uid,
            current_streak=50,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify mixed goal progress updated correctly
        # Old progress: 20%
        # Habit contribution: (50 / 100) * 30% = 15%
        # New progress: (20 * 0.7) + 15 = 14 + 15 = 29%
        goal_result = await goals_backend.get(mixed_goal.uid)
        assert goal_result.is_ok
        updated_goal = goal_result.value
        expected_progress = (20.0 * 0.7) + ((50.0 / 100.0) * 30)
        assert updated_goal.progress_percentage == pytest.approx(expected_progress, abs=0.1)
