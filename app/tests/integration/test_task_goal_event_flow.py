"""
Integration Test: Task→Goal Event-Driven Progress Updates
=============================================================

Tests Phase 4 event-driven architecture for cross-domain dependencies.

This test suite verifies that:
1. TaskCompleted events trigger goal progress updates
2. GoalsProgressService.handle_task_completed() receives events
3. Goal progress is calculated correctly based on task completion
4. GoalProgressUpdated events are published when progress changes
5. GoalAchieved events are published when goals reach 100%
6. Multiple goals can be updated from a single task completion
7. Different goal measurement types are handled correctly

Event Flow:
-----------
Task completed → TaskCompleted event → GoalsProgressService.handle_task_completed()
    → Query Neo4j for linked goals → Calculate new progress → Update goal
    → Publish GoalProgressUpdated event → (If 100%) Publish GoalAchieved event
"""

from datetime import date, datetime

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events import GoalAchieved, GoalProgressUpdated
from core.events.task_events import TaskCompleted
from core.models.enums import Domain, EntityStatus, Priority
from core.models.enums.goal_enums import GoalType, MeasurementType
from core.models.goal.goal import Goal
from core.models.task.task import Task as Task
from core.services.goals.goals_progress_service import GoalsProgressService
from core.services.tasks.tasks_core_service import TasksCoreService


@pytest.mark.asyncio
class TestTaskGoalEventFlow:
    """Integration tests for Task→Goal event-driven progress updates."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture and performance monitoring disabled."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def tasks_backend(self, neo4j_driver, clean_neo4j):
        """Create tasks backend with clean database."""
        return UniversalNeo4jBackend[Task](
            neo4j_driver, "Entity", Task, default_filters={"ku_type": "task"}
        )

    @pytest_asyncio.fixture
    async def goals_backend(self, neo4j_driver, clean_neo4j):
        """Create goals backend with clean database."""
        return UniversalNeo4jBackend[Goal](
            neo4j_driver, "Entity", Goal, default_filters={"ku_type": "goal"}
        )

    @pytest_asyncio.fixture
    async def tasks_service(self, tasks_backend, event_bus):
        """Create TasksCoreService with event bus."""
        return TasksCoreService(backend=tasks_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def goals_progress_service(self, goals_backend, event_bus, neo4j_driver):
        """Create GoalsProgressService with event bus."""
        return GoalsProgressService(
            backend=goals_backend,
            event_bus=event_bus,
            relationships_service=None,
        )

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_task_goal_flow"

    @pytest_asyncio.fixture
    async def task_based_goal(self, goals_backend, test_user_uid):
        """Create a task-based goal in Neo4j."""
        goal = Goal(
            uid="goal.finish_python_course",
            user_uid=test_user_uid,
            title="Finish Python Course",
            description="Complete all Python learning tasks",
            domain=Domain.TECH,
            measurement_type=MeasurementType.TASK_BASED,
            progress_percentage=0.0,
            current_value=0.0,
            target_value=100.0,
            status=EntityStatus.ACTIVE,
            target_date=date(2025, 12, 31),
        )
        result = await goals_backend.create(goal)
        assert result.is_ok
        return result.value

    @pytest_asyncio.fixture
    async def mixed_goal(self, goals_backend, test_user_uid):
        """Create a mixed-measurement goal in Neo4j."""
        goal = Goal(
            uid="goal.become_python_expert",
            user_uid=test_user_uid,
            title="Become Python Expert",
            description="Master Python through tasks, habits, and knowledge",
            domain=Domain.TECH,
            measurement_type=MeasurementType.MIXED,
            progress_percentage=0.0,
            current_value=0.0,
            target_value=100.0,
            status=EntityStatus.ACTIVE,
            target_date=date(2025, 12, 31),
        )
        result = await goals_backend.create(goal)
        assert result.is_ok
        return result.value

    @pytest_asyncio.fixture
    async def linked_tasks(self, tasks_backend, neo4j_driver, task_based_goal, test_user_uid):
        """Create 3 tasks linked to the task-based goal."""
        tasks = []

        for i in range(1, 4):
            task = Task(
                uid=f"task.python_lesson_{i}",
                user_uid=test_user_uid,
                title=f"Complete Python Lesson {i}",
                description=f"Lesson {i} exercises",
                priority=Priority.MEDIUM,
                status=EntityStatus.SCHEDULED,
                due_date=date(2025, 11, 30),
            )
            result = await tasks_backend.create(task)
            assert result.is_ok
            tasks.append(result.value)

        # Create graph relationships: (Goal)-[:SUPPORTS_GOAL]->(Task)
        async with neo4j_driver.session() as session:
            # First verify that goal exists
            goal_check = await session.run(
                "MATCH (g:Entity {uid: $uid}) RETURN g.uid as uid", uid=task_based_goal.uid
            )
            goal_exists = await goal_check.data()
            print(f"Goal check: {len(goal_exists)} goals found with UID {task_based_goal.uid}")

            for task in tasks:
                # Verify task exists
                task_check = await session.run(
                    "MATCH (t:Entity {uid: $uid}) RETURN t.uid as uid", uid=task.uid
                )
                task_exists = await task_check.data()
                print(f"Task check: {len(task_exists)} tasks found with UID {task.uid}")

                # Create relationship using MERGE (idempotent)
                result = await session.run(
                    """
                    MATCH (goal:Entity {uid: $goal_uid})
                    MATCH (task:Entity {uid: $task_uid})
                    MERGE (goal)-[:SUPPORTS_GOAL]->(task)
                    RETURN goal.uid as goal_uid, task.uid as task_uid
                    """,
                    goal_uid=task_based_goal.uid,
                    task_uid=task.uid,
                )
                records = await result.data()
                if len(records) == 0:
                    print(f"WARNING: Failed to create relationship for {task.uid}")

        return tasks

    # ========================================================================
    # BASIC EVENT FLOW TESTS
    # ========================================================================

    async def test_task_completed_event_triggers_goal_progress_update(
        self,
        event_bus,
        goals_progress_service,
        tasks_service,
        tasks_backend,
        task_based_goal,
        linked_tasks,
        test_user_uid,
    ):
        """Test that completing a task triggers goal progress update via events."""

        # Subscribe GoalsProgressService to TaskCompleted events
        event_bus.subscribe(TaskCompleted, goals_progress_service.handle_task_completed)

        # Complete the first task (should trigger event)
        task_to_complete = linked_tasks[0]

        # Update task status in Neo4j to 'completed'
        result = await tasks_backend.update(
            task_to_complete.uid, {"status": EntityStatus.COMPLETED.value}
        )
        assert result.is_ok, "Setup failed: Could not update task"

        # Manually publish TaskCompleted event (simulating TasksCoreService)
        event = TaskCompleted(
            task_uid=task_to_complete.uid,
            user_uid=test_user_uid,
            occurred_at=datetime.now(),
        )
        await event_bus.publish_async(event)

        # Wait a moment for async event processing
        import asyncio

        await asyncio.sleep(0.1)

        # Verify event was published and captured
        history = event_bus.get_event_history()
        assert len(history) >= 1
        assert isinstance(history[0], TaskCompleted)

        # Verify GoalProgressUpdated event was published
        progress_events = [e for e in history if isinstance(e, GoalProgressUpdated)]
        assert len(progress_events) == 1
        assert progress_events[0].goal_uid == task_based_goal.uid
        assert progress_events[0].user_uid == test_user_uid

        # Note: Progress calculation requires task status to be updated in Neo4j
        # This test verifies event flow; actual progress calculation tested separately

    async def test_goal_progress_calculated_correctly_for_task_based_goal(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        tasks_backend,
        task_based_goal,
        linked_tasks,
        test_user_uid,
        neo4j_driver,
    ):
        """Test that goal progress is calculated correctly for task-based goals."""

        # Subscribe GoalsProgressService to TaskCompleted events
        event_bus.subscribe(TaskCompleted, goals_progress_service.handle_task_completed)

        # Complete first task (1/3 = 33.33%)
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (t:Entity {uid: $uid}) SET t.status = 'completed'",
                uid=linked_tasks[0].uid,
            )

        event1 = TaskCompleted(
            task_uid=linked_tasks[0].uid, user_uid=test_user_uid, occurred_at=datetime.now()
        )
        await event_bus.publish_async(event1)

        import asyncio

        await asyncio.sleep(0.1)

        # Check goal progress
        goal_result = await goals_backend.get(task_based_goal.uid)
        assert goal_result.is_ok
        updated_goal = goal_result.value
        assert updated_goal.progress_percentage > 30  # ~33.33%
        assert updated_goal.progress_percentage < 35

        # Complete second task (2/3 = 66.67%)
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (t:Entity {uid: $uid}) SET t.status = 'completed'",
                uid=linked_tasks[1].uid,
            )

        event2 = TaskCompleted(
            task_uid=linked_tasks[1].uid, user_uid=test_user_uid, occurred_at=datetime.now()
        )
        await event_bus.publish_async(event2)
        await asyncio.sleep(0.1)

        goal_result = await goals_backend.get(task_based_goal.uid)
        assert goal_result.is_ok
        updated_goal = goal_result.value
        assert updated_goal.progress_percentage > 65  # ~66.67%
        assert updated_goal.progress_percentage < 68

    async def test_goal_achieved_event_published_at_100_percent(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        task_based_goal,
        linked_tasks,
        test_user_uid,
        neo4j_driver,
    ):
        """Test that GoalAchieved event is published when goal reaches 100%."""

        # Subscribe GoalsProgressService to TaskCompleted events
        event_bus.subscribe(TaskCompleted, goals_progress_service.handle_task_completed)

        # Complete all three tasks to reach 100%
        async with neo4j_driver.session() as session:
            for task in linked_tasks:
                await session.run(
                    "MATCH (t:Entity {uid: $uid}) SET t.status = 'completed'", uid=task.uid
                )

        # Publish TaskCompleted event for the last task
        event = TaskCompleted(
            task_uid=linked_tasks[2].uid, user_uid=test_user_uid, occurred_at=datetime.now()
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify GoalAchieved event was published
        history = event_bus.get_event_history()
        achieved_events = [e for e in history if isinstance(e, GoalAchieved)]
        assert len(achieved_events) >= 1
        assert achieved_events[-1].goal_uid == task_based_goal.uid
        assert achieved_events[-1].user_uid == test_user_uid

        # Verify goal status updated to ACHIEVED
        goal_result = await goals_backend.get(task_based_goal.uid)
        assert goal_result.is_ok
        updated_goal = goal_result.value
        assert updated_goal.progress_percentage >= 100
        assert updated_goal.status == EntityStatus.COMPLETED

    async def test_multiple_goals_updated_from_single_task(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        tasks_backend,
        test_user_uid,
        neo4j_driver,
    ):
        """Test that completing one task can update multiple goals."""

        # Create two goals
        goal1 = Goal(
            uid="goal.learn_basics",
            user_uid=test_user_uid,
            title="Learn Python Basics",
            measurement_type=MeasurementType.TASK_BASED,
            progress_percentage=0.0,
            status=EntityStatus.ACTIVE,
        )
        goal2 = Goal(
            uid="goal.complete_course",
            user_uid=test_user_uid,
            title="Complete Full Course",
            measurement_type=MeasurementType.TASK_BASED,
            progress_percentage=0.0,
            status=EntityStatus.ACTIVE,
        )
        goal1_result = await goals_backend.create(goal1)
        assert goal1_result.is_ok, "Setup failed: Could not create goal1"
        goal2_result = await goals_backend.create(goal2)
        assert goal2_result.is_ok, "Setup failed: Could not create goal2"

        # Create one task
        task = Task(
            uid="task.variables_lesson",
            user_uid=test_user_uid,
            title="Learn Variables",
            priority=Priority.MEDIUM,
            status=EntityStatus.SCHEDULED,
        )
        task_result = await tasks_backend.create(task)
        assert task_result.is_ok, "Setup failed: Could not create task"

        # Link task to both goals
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (goal1:Entity {uid: $goal1_uid})
                MATCH (goal2:Entity {uid: $goal2_uid})
                MATCH (task:Entity {uid: $task_uid})
                CREATE (goal1)-[:SUPPORTS_GOAL]->(task)
                CREATE (goal2)-[:SUPPORTS_GOAL]->(task)
                """,
                goal1_uid=goal1.uid,
                goal2_uid=goal2.uid,
                task_uid=task.uid,
            )

            # Mark task as completed
            await session.run(
                "MATCH (t:Entity {uid: $uid}) SET t.status = 'completed'", uid=task.uid
            )

        # Subscribe and publish event
        event_bus.subscribe(TaskCompleted, goals_progress_service.handle_task_completed)
        event = TaskCompleted(task_uid=task.uid, user_uid=test_user_uid, occurred_at=datetime.now())
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify both goals were updated (should have GoalProgressUpdated events)
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, GoalProgressUpdated)]
        assert len(progress_events) == 2

        goal_uids_updated = {e.goal_uid for e in progress_events}
        assert goal1.uid in goal_uids_updated
        assert goal2.uid in goal_uids_updated

    async def test_no_update_when_task_not_linked_to_goal(
        self, event_bus, goals_progress_service, tasks_backend, test_user_uid
    ):
        """Test that completing an unlinked task doesn't trigger goal updates."""

        # Create a standalone task (not linked to any goal)
        task = Task(
            uid="task.standalone",
            user_uid=test_user_uid,
            title="Standalone Task",
            priority=Priority.LOW,
            status=EntityStatus.COMPLETED,
        )
        task_result = await tasks_backend.create(task)
        assert task_result.is_ok, "Setup failed: Could not create task"

        # Subscribe and publish event
        event_bus.subscribe(TaskCompleted, goals_progress_service.handle_task_completed)
        event = TaskCompleted(task_uid=task.uid, user_uid=test_user_uid, occurred_at=datetime.now())
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify NO GoalProgressUpdated events were published
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, GoalProgressUpdated)]
        assert len(progress_events) == 0

    async def test_habit_based_goal_not_updated_by_task_completion(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        tasks_backend,
        test_user_uid,
        neo4j_driver,
    ):
        """Test that habit-based goals are NOT updated by task completion."""

        # Create habit-based goal
        goal = Goal(
            uid="goal.daily_practice",
            user_uid=test_user_uid,
            title="Daily Practice Goal",
            measurement_type=MeasurementType.HABIT_BASED,  # Not task-based!
            progress_percentage=0.0,
            status=EntityStatus.ACTIVE,
        )
        goal_result = await goals_backend.create(goal)
        assert goal_result.is_ok, "Setup failed: Could not create goal"

        # Create task linked to this goal
        task = Task(
            uid="task.practice_session",
            user_uid=test_user_uid,
            title="Practice Session",
            priority=Priority.MEDIUM,
            status=EntityStatus.SCHEDULED,
        )
        task_result = await tasks_backend.create(task)
        assert task_result.is_ok, "Setup failed: Could not create task"

        # Link task to goal
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (goal:Entity {uid: $goal_uid})
                MATCH (task:Entity {uid: $task_uid})
                CREATE (goal)-[:SUPPORTS_GOAL]->(task)
                """,
                goal_uid=goal.uid,
                task_uid=task.uid,
            )

            # Mark task as completed
            await session.run(
                "MATCH (t:Entity {uid: $uid}) SET t.status = 'completed'", uid=task.uid
            )

        # Subscribe and publish event
        event_bus.subscribe(TaskCompleted, goals_progress_service.handle_task_completed)
        event = TaskCompleted(task_uid=task.uid, user_uid=test_user_uid, occurred_at=datetime.now())
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify goal progress was NOT updated (habit-based goals skip task updates)
        goal_result = await goals_backend.get(goal.uid)
        assert goal_result.is_ok
        assert goal_result.value.progress_percentage == 0.0

    async def test_mixed_goal_updated_with_task_contribution(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        tasks_backend,
        mixed_goal,
        test_user_uid,
        neo4j_driver,
    ):
        """Test that mixed goals include task contribution (30%) in progress."""

        # Create 2 tasks for mixed goal
        tasks = []
        for i in range(1, 3):
            task = Task(
                uid=f"task.mixed_{i}",
                user_uid=test_user_uid,
                title=f"Task {i}",
                priority=Priority.MEDIUM,
                status=EntityStatus.SCHEDULED,
            )
            result = await tasks_backend.create(task)
            tasks.append(result.value)

        # Link tasks to mixed goal
        async with neo4j_driver.session() as session:
            for task in tasks:
                await session.run(
                    """
                    MATCH (goal:Entity {uid: $goal_uid})
                    MATCH (task:Entity {uid: $task_uid})
                    CREATE (goal)-[:SUPPORTS_GOAL]->(task)
                    """,
                    goal_uid=mixed_goal.uid,
                    task_uid=task.uid,
                )

            # Complete first task (1/2 = 50% task contribution)
            await session.run(
                "MATCH (t:Entity {uid: $uid}) SET t.status = 'completed'", uid=tasks[0].uid
            )

        # Subscribe and publish event
        event_bus.subscribe(TaskCompleted, goals_progress_service.handle_task_completed)
        event = TaskCompleted(
            task_uid=tasks[0].uid, user_uid=test_user_uid, occurred_at=datetime.now()
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # For mixed goals: task contribution is 30% of total
        # 50% task completion * 30% weight = 15% total progress
        goal_result = await goals_backend.get(mixed_goal.uid)
        assert goal_result.is_ok
        updated_goal = goal_result.value
        assert updated_goal.progress_percentage > 14  # ~15%
        assert updated_goal.progress_percentage < 16

    # ========================================================================
    # EDGE CASES AND ERROR HANDLING
    # ========================================================================

    async def test_error_in_one_goal_update_does_not_prevent_others(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        tasks_backend,
        test_user_uid,
        neo4j_driver,
    ):
        """Test that update error for one goal doesn't prevent updates to other goals."""

        # Create two goals
        goal1 = Goal(
            uid="goal.valid",
            user_uid=test_user_uid,
            title="Valid Goal",
            measurement_type=MeasurementType.TASK_BASED,
            progress_percentage=0.0,
            status=EntityStatus.ACTIVE,
        )
        goal2 = Goal(
            uid="goal.invalid",
            user_uid=test_user_uid,
            title="Invalid Goal",
            measurement_type=MeasurementType.TASK_BASED,
            progress_percentage=0.0,
            status=EntityStatus.ACTIVE,
        )
        goal1_result = await goals_backend.create(goal1)
        assert goal1_result.is_ok, "Setup failed: Could not create goal1"
        goal2_result = await goals_backend.create(goal2)
        assert goal2_result.is_ok, "Setup failed: Could not create goal2"

        # Create task linked to both
        task = Task(
            uid="task.shared",
            user_uid=test_user_uid,
            title="Shared Task",
            priority=Priority.MEDIUM,
            status=EntityStatus.SCHEDULED,
        )
        task_result = await tasks_backend.create(task)
        assert task_result.is_ok, "Setup failed: Could not create task"

        # Link task to both goals
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (goal1:Entity {uid: $goal1_uid})
                MATCH (goal2:Entity {uid: $goal2_uid})
                MATCH (task:Entity {uid: $task_uid})
                CREATE (goal1)-[:SUPPORTS_GOAL]->(task)
                CREATE (goal2)-[:SUPPORTS_GOAL]->(task)
                """,
                goal1_uid=goal1.uid,
                goal2_uid=goal2.uid,
                task_uid=task.uid,
            )

            # Mark task as completed
            await session.run(
                "MATCH (t:Entity {uid: $uid}) SET t.status = 'completed'", uid=task.uid
            )

            # Delete goal2 to cause error during update
            await session.run("MATCH (g:Entity {uid: $uid}) DETACH DELETE g", uid=goal2.uid)

        # Subscribe and publish event
        event_bus.subscribe(TaskCompleted, goals_progress_service.handle_task_completed)
        event = TaskCompleted(task_uid=task.uid, user_uid=test_user_uid, occurred_at=datetime.now())
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify goal1 was still updated despite goal2 error
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, GoalProgressUpdated)]
        assert len(progress_events) >= 1
        assert any(e.goal_uid == goal1.uid for e in progress_events)

    async def test_no_duplicate_achievement_events(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        tasks_backend,
        test_user_uid,
        neo4j_driver,
    ):
        """Test that GoalAchieved event is only published once at 100%."""

        # Create goal with single task
        goal = Goal(
            uid="goal.single_task",
            user_uid=test_user_uid,
            title="Single Task Goal",
            measurement_type=MeasurementType.TASK_BASED,
            progress_percentage=0.0,
            status=EntityStatus.ACTIVE,
        )
        goal_result = await goals_backend.create(goal)
        assert goal_result.is_ok, "Setup failed: Could not create goal"

        task = Task(
            uid="task.only_one",
            user_uid=test_user_uid,
            title="Only Task",
            priority=Priority.HIGH,
            status=EntityStatus.SCHEDULED,
        )
        task_result = await tasks_backend.create(task)
        assert task_result.is_ok, "Setup failed: Could not create task"

        # Link and complete
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (goal:Entity {uid: $goal_uid})
                MATCH (task:Entity {uid: $task_uid})
                CREATE (goal)-[:SUPPORTS_GOAL]->(task)
                """,
                goal_uid=goal.uid,
                task_uid=task.uid,
            )
            await session.run(
                "MATCH (t:Entity {uid: $uid}) SET t.status = 'completed'", uid=task.uid
            )

        # Subscribe and publish event
        event_bus.subscribe(TaskCompleted, goals_progress_service.handle_task_completed)
        event = TaskCompleted(task_uid=task.uid, user_uid=test_user_uid, occurred_at=datetime.now())
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Publish the same event again (simulating duplicate)
        await event_bus.publish_async(event)
        await asyncio.sleep(0.1)

        # Verify only ONE GoalAchieved event was published
        history = event_bus.get_event_history()
        achieved_events = [e for e in history if isinstance(e, GoalAchieved)]
        # Should be 1 (second event sees goal already at 100%, old_progress == 100)
        assert len(achieved_events) == 1

    async def test_project_goal_updated_by_task_completion(
        self,
        event_bus,
        goals_progress_service,
        goals_backend,
        tasks_backend,
        test_user_uid,
        neo4j_driver,
    ):
        """
        Test that PROJECT-type goals are updated by task completion.

        This test verifies that goal_type=PROJECT works correctly when
        measurement_type=TASK_BASED. The handler filters by measurement_type,
        not goal_type, so PROJECT goals should work identically to OUTCOME goals.
        """
        # Create PROJECT-type goal with task-based measurement
        project_goal = Goal(
            uid="goal.build_api_project",
            user_uid=test_user_uid,
            title="Build REST API Project",
            description="Complete all project milestones",
            goal_type=GoalType.PROJECT,  # PROJECT type
            measurement_type=MeasurementType.TASK_BASED,  # Task-based measurement
            domain=Domain.TECH,
            progress_percentage=0.0,
            current_value=0.0,
            target_value=100.0,
            status=EntityStatus.ACTIVE,
            target_date=date(2025, 12, 31),
        )
        project_goal_result = await goals_backend.create(project_goal)
        assert project_goal_result.is_ok, "Setup failed: Could not create project goal"

        # Create 4 project tasks
        tasks = []
        for i in range(1, 5):
            task = Task(
                uid=f"task.api_milestone_{i}",
                user_uid=test_user_uid,
                title=f"Project Milestone {i}",
                description=f"Complete milestone {i}",
                priority=Priority.HIGH,
                status=EntityStatus.SCHEDULED,
                due_date=date(2025, 11, 30),
            )
            result = await tasks_backend.create(task)
            tasks.append(result.value)

        # Link all tasks to project goal
        async with neo4j_driver.session() as session:
            for task in tasks:
                await session.run(
                    """
                    MATCH (goal:Entity {uid: $goal_uid})
                    MATCH (task:Entity {uid: $task_uid})
                    CREATE (goal)-[:SUPPORTS_GOAL]->(task)
                    """,
                    goal_uid=project_goal.uid,
                    task_uid=task.uid,
                )

            # Verify relationships were created
            verify = await session.run(
                """
                MATCH (goal:Entity {uid: $goal_uid})-[:SUPPORTS_GOAL]->(task:Entity)
                RETURN count(task) as task_count
                """,
                goal_uid=project_goal.uid,
            )
            result = await verify.single()
            assert result["task_count"] == 4, (
                f"Expected 4 SUPPORTS_GOAL relationships, got {result['task_count']}"
            )

            # Complete first task
            await session.run(
                "MATCH (t:Entity {uid: $uid}) SET t.status = 'completed'",
                uid=tasks[0].uid,
            )

        # Subscribe and publish event for first task
        event_bus.subscribe(TaskCompleted, goals_progress_service.handle_task_completed)
        event = TaskCompleted(
            task_uid=tasks[0].uid, user_uid=test_user_uid, occurred_at=datetime.now()
        )
        await event_bus.publish_async(event)

        import asyncio

        await asyncio.sleep(0.1)

        # Verify project goal progress was updated
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, GoalProgressUpdated)]
        assert len(progress_events) == 1
        assert progress_events[0].goal_uid == project_goal.uid
        assert progress_events[0].new_progress == pytest.approx(25.0, abs=0.1)  # 1/4 = 25%

        # Complete all remaining tasks
        async with neo4j_driver.session() as session:
            for task in tasks[1:]:
                await session.run(
                    "MATCH (t:Entity {uid: $uid}) SET t.status = 'completed'",
                    uid=task.uid,
                )

        # Publish events for remaining tasks one at a time
        for task in tasks[1:]:
            event = TaskCompleted(
                task_uid=task.uid, user_uid=test_user_uid, occurred_at=datetime.now()
            )
            await event_bus.publish_async(event)
            await asyncio.sleep(0.05)  # Small delay between events

        await asyncio.sleep(0.1)  # Extra time for final processing

        # Verify project goal reached 100% and GoalAchieved was published
        history = event_bus.get_event_history()
        progress_events = [e for e in history if isinstance(e, GoalProgressUpdated)]

        # Verify progress events were published for the project goal
        # Note: May not be exactly 4 events if handler processed multiple completions in one batch
        project_progress_events = [e for e in progress_events if e.goal_uid == project_goal.uid]
        assert len(project_progress_events) >= 2, (
            f"Expected at least 2 progress events (initial and final), got {len(project_progress_events)}"
        )

        # Final progress should be 100%
        final_progress_event = max(project_progress_events, key=lambda e: e.occurred_at)
        assert final_progress_event.new_progress == pytest.approx(100.0, abs=0.1)

        # First progress event should show partial completion
        first_progress_event = min(project_progress_events, key=lambda e: e.occurred_at)
        assert first_progress_event.new_progress > 0 and first_progress_event.new_progress < 100

        # Verify GoalAchieved event was published
        achieved_events = [e for e in history if isinstance(e, GoalAchieved)]
        assert len(achieved_events) == 1, (
            f"Expected 1 achievement event, got {len(achieved_events)}"
        )
        assert achieved_events[0].goal_uid == project_goal.uid
