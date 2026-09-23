"""
Integration Test: Task→Goal Event-Driven Progress Updates
=============================================================

Verifies that completing a task moves the goal it fulfills:

1. ``TaskCompleted`` reaches ``GoalsProgressService.handle_task_completed()``
2. Goal progress is calculated from the goal's linked tasks
3. ``GoalProgressUpdated`` is published when progress changes
4. ``GoalAchieved`` is published once when the goal reaches 100%
5. Only task-based goals move — a MIXED goal is not recomputed from one component

Every link is written by the production writer — ``TasksCoreService.create`` with
``fulfills_goal_uid``, which dual-writes the stamp and ``(Task)-[:FULFILLS_GOAL]->(Goal)``
— and every completion goes through the production door, ``update_task``, which
publishes ``TaskCompleted``. A task fulfills at most one goal (GOALS_CONFIG /
TASKS_CONFIG declare the link ``single``), so there is no multi-goal case here; the
habit sibling covers a completion fanning out to several goals.

Event Flow:
-----------
update_task(status=completed) → TaskCompleted → GoalsProgressService.handle_task_completed()
    → GoalsBackend.find_linked_goals_for_task → recompute_progress_from_linked_tasks
      (lock the goal, tally its tasks, plan, guarded write — one transaction)
    → GoalProgressUpdated → (at 100%) GoalAchieved
"""

import asyncio
from datetime import date

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.activity_backends import GoalsBackend, TasksBackend
from core.events import GoalAchieved, GoalProgressUpdated
from core.events.task_events import TaskCompleted
from core.models.enums import Domain, EntityStatus, Priority
from core.models.enums.goal_enums import GoalType, MeasurementType
from core.models.enums.neo_labels import NeoLabel
from core.models.goal.goal import Goal
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent
from core.services.goals.goals_progress_service import GoalsProgressService
from core.services.tasks.tasks_core_service import TasksCoreService

_USER_UID = "user_test_task_goal_flow"


@pytest.mark.asyncio
class TestTaskGoalEventFlow:
    """Integration tests for Task→Goal event-driven progress updates."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def goals_backend(self, neo4j_driver, clean_neo4j):
        return GoalsBackend(neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY)

    @pytest_asyncio.fixture
    async def tasks_service(self, neo4j_driver, clean_neo4j, event_bus):
        backend = TasksBackend(neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)
        return TasksCoreService(backend=backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def goals_progress_service(self, goals_backend, event_bus):
        service = GoalsProgressService(
            backend=goals_backend, event_bus=event_bus, relationship_service=None
        )
        event_bus.subscribe(TaskCompleted, service.handle_task_completed)
        return service

    async def _create_goal(
        self,
        goals_backend: GoalsBackend,
        uid: str,
        measurement: MeasurementType,
        goal_type: GoalType = GoalType.OUTCOME,
    ) -> Goal:
        result = await goals_backend.create(
            Goal(
                uid=uid,
                user_uid=_USER_UID,
                title=uid,
                domain=Domain.TECH,
                goal_type=goal_type,
                measurement_type=measurement,
                progress_percentage=0.0,
                current_value=0.0,
                target_value=100.0,
                status=EntityStatus.ACTIVE,
                target_date=date(2025, 12, 31),
            )
        )
        assert result.is_ok, result
        return result.value

    async def _create_task(
        self, tasks_service: TasksCoreService, uid: str, goal_uid: str | None
    ) -> Task:
        """Create a task through the production door, linked to ``goal_uid`` if given."""
        result = await tasks_service.create(
            Task(
                uid=uid,
                user_uid=_USER_UID,
                title=uid,
                priority=Priority.MEDIUM,
                status=EntityStatus.SCHEDULED,
                fulfills_goal_uid=goal_uid,
            )
        )
        assert result.is_ok, result
        # The door clears the stamp when it could not write the edge — a surviving
        # stamp means (Task)-[:FULFILLS_GOAL]->(Goal) exists.
        assert result.value.fulfills_goal_uid == goal_uid
        return result.value

    async def _complete(self, tasks_service: TasksCoreService, task_uid: str) -> None:
        result = await tasks_service.update_task(
            task_uid, TaskUpdateIntent(status=EntityStatus.COMPLETED.value)
        )
        assert result.is_ok, result

    @staticmethod
    def _events(event_bus: InMemoryEventBus, event_type: type) -> list:
        return [e for e in event_bus.get_event_history() if isinstance(e, event_type)]

    # ========================================================================
    # BASIC EVENT FLOW
    # ========================================================================

    async def test_task_completed_event_triggers_goal_progress_update(
        self, event_bus, goals_progress_service, goals_backend, tasks_service
    ):
        """Completing a linked task publishes GoalProgressUpdated for its goal."""
        goal = await self._create_goal(goals_backend, "goal.flow", MeasurementType.TASK_BASED)
        tasks = [
            await self._create_task(tasks_service, f"task.flow_{i}", goal.uid) for i in (1, 2, 3)
        ]

        await self._complete(tasks_service, tasks[0].uid)

        progress_events = self._events(event_bus, GoalProgressUpdated)
        assert len(progress_events) == 1
        assert progress_events[0].goal_uid == goal.uid
        assert progress_events[0].user_uid == _USER_UID

    async def test_goal_progress_calculated_correctly_for_task_based_goal(
        self, goals_progress_service, goals_backend, tasks_service
    ):
        """1 of 3 → ~33%; 2 of 3 → ~67%."""
        goal = await self._create_goal(goals_backend, "goal.calc", MeasurementType.TASK_BASED)
        tasks = [
            await self._create_task(tasks_service, f"task.calc_{i}", goal.uid) for i in (1, 2, 3)
        ]

        await self._complete(tasks_service, tasks[0].uid)
        stored = (await goals_backend.get(goal.uid)).value
        assert stored.progress_percentage == pytest.approx(100 / 3)

        await self._complete(tasks_service, tasks[1].uid)
        stored = (await goals_backend.get(goal.uid)).value
        assert stored.progress_percentage == pytest.approx(200 / 3)

    async def test_goal_achieved_event_published_at_100_percent(
        self, event_bus, goals_progress_service, goals_backend, tasks_service
    ):
        """Completing every linked task achieves the goal, announced once."""
        goal = await self._create_goal(goals_backend, "goal.all", MeasurementType.TASK_BASED)
        tasks = [
            await self._create_task(tasks_service, f"task.all_{i}", goal.uid) for i in (1, 2, 3)
        ]

        for task in tasks:
            await self._complete(tasks_service, task.uid)

        achieved = self._events(event_bus, GoalAchieved)
        assert [e.goal_uid for e in achieved] == [goal.uid]
        stored = (await goals_backend.get(goal.uid)).value
        assert stored.progress_percentage >= 100
        assert stored.status == EntityStatus.COMPLETED

    async def test_no_update_when_task_not_linked_to_goal(
        self, event_bus, goals_progress_service, tasks_service
    ):
        """Completing an unlinked task publishes no goal progress."""
        task = await self._create_task(tasks_service, "task.standalone", None)

        await self._complete(tasks_service, task.uid)

        assert self._events(event_bus, GoalProgressUpdated) == []

    async def test_habit_based_goal_not_updated_by_task_completion(
        self, goals_progress_service, goals_backend, tasks_service
    ):
        """A habit-based goal ignores task completions."""
        goal = await self._create_goal(goals_backend, "goal.habitual", MeasurementType.HABIT_BASED)
        task = await self._create_task(tasks_service, "task.practice", goal.uid)

        await self._complete(tasks_service, task.uid)

        stored = (await goals_backend.get(goal.uid)).value
        assert stored.progress_percentage == 0.0

    async def test_mixed_goal_not_moved_by_task_completions(
        self, event_bus, goals_progress_service, goals_backend, tasks_service
    ):
        """A MIXED goal is not recomputed from its task tally — completions leave it alone."""
        goal = await self._create_goal(goals_backend, "goal.mixed", MeasurementType.MIXED)
        tasks = [
            await self._create_task(tasks_service, f"task.mixed_{i}", goal.uid) for i in (1, 2)
        ]

        for task in tasks:
            await self._complete(tasks_service, task.uid)

        stored = (await goals_backend.get(goal.uid)).value
        assert stored.progress_percentage == 0.0
        assert self._events(event_bus, GoalProgressUpdated) == []

    # ========================================================================
    # EDGE CASES
    # ========================================================================

    async def test_no_duplicate_achievement_events(
        self, event_bus, goals_progress_service, goals_backend, tasks_service
    ):
        """A redelivered TaskCompleted does not announce the achievement twice."""
        goal = await self._create_goal(goals_backend, "goal.single", MeasurementType.TASK_BASED)
        task = await self._create_task(tasks_service, "task.only_one", goal.uid)

        await self._complete(tasks_service, task.uid)
        # Redeliver the event the door published — the door itself never republishes.
        [completed] = self._events(event_bus, TaskCompleted)
        await event_bus.publish_async(completed)

        assert len(self._events(event_bus, GoalAchieved)) == 1

    async def test_project_goal_updated_by_task_completion(
        self, event_bus, goals_progress_service, goals_backend, tasks_service
    ):
        """PROJECT goals are filtered by measurement_type like any other: 1/4 → 25% … 100%."""
        goal = await self._create_goal(
            goals_backend,
            "goal.api_project",
            MeasurementType.TASK_BASED,
            goal_type=GoalType.PROJECT,
        )
        tasks = [
            await self._create_task(tasks_service, f"task.api_{i}", goal.uid) for i in (1, 2, 3, 4)
        ]

        await self._complete(tasks_service, tasks[0].uid)
        [first] = self._events(event_bus, GoalProgressUpdated)
        assert first.goal_uid == goal.uid
        assert first.new_progress == pytest.approx(25.0)

        for task in tasks[1:]:
            await self._complete(tasks_service, task.uid)

        progress = [e.new_progress for e in self._events(event_bus, GoalProgressUpdated)]
        assert progress == pytest.approx([25.0, 50.0, 75.0, 100.0])
        assert [e.goal_uid for e in self._events(event_bus, GoalAchieved)] == [goal.uid]


@pytest.mark.asyncio
class TestTaskGoalRecomputeUnderTheGoalLock:
    """The tally is counted under the goal's write-lock, not before it.

    The race: two tasks of one goal complete together, and each completion's handler
    recomputes the goal. If a handler counts before it takes the goal's lock, it can
    count 1/2, wait for the lock while the other handler writes 2/2 and 100%, and then
    land its stale 1/2 and 50% on top.

    Racing two handlers with ``gather`` does not reproduce this reliably, because each
    call does enough work to stagger itself. So the test holds the goal's write-lock in
    a raw transaction that also completes the second task, and runs the first task's
    handler against it. A handler that counts before the lock reads the committed
    1-of-2 and writes it after the holder commits. A handler that counts under the
    lock waits, and then reads both.
    """

    async def test_a_count_cannot_land_after_a_completion_it_did_not_see(
        self, neo4j_driver, clean_neo4j
    ):
        bus = InMemoryEventBus(capture_history=True)
        goals_backend = GoalsBackend(neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY)
        tasks_service = TasksCoreService(
            backend=TasksBackend(neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY),
            event_bus=bus,
        )
        # Not subscribed: this test fires the handler itself, at the moment it chooses.
        progress = GoalsProgressService(backend=goals_backend, event_bus=bus)

        flow = TestTaskGoalEventFlow()
        goal = await flow._create_goal(goals_backend, "goal.race", MeasurementType.TASK_BASED)
        first = await flow._create_task(tasks_service, "task.race_1", goal.uid)
        second = await flow._create_task(tasks_service, "task.race_2", goal.uid)
        await flow._complete(tasks_service, first.uid)

        async with neo4j_driver.session() as session:
            holder = await session.begin_transaction()
            # A real property write takes the goal's write-lock until commit.
            await holder.run(
                "MATCH (g:Entity {uid: $g}) SET g.race_probe = 1 REMOVE g.race_probe",
                g=goal.uid,
            )
            await holder.run(
                "MATCH (t:Entity {uid: $t}) SET t.status = $completed",
                t=second.uid,
                completed=EntityStatus.COMPLETED.value,
            )

            handler = asyncio.create_task(
                progress.handle_task_completed(
                    TaskCompleted(task_uid=first.uid, user_uid=_USER_UID)
                )
            )
            # Long enough for a handler that counts before the lock to have counted.
            await asyncio.sleep(1.0)
            assert not handler.done(), "the handler wrote without waiting for the goal's lock"
            await holder.commit()

        await asyncio.wait_for(handler, timeout=30)

        stored = (await goals_backend.get(goal.uid)).value
        assert stored is not None
        assert (stored.current_value, stored.target_value) == (2.0, 2.0)
        assert stored.progress_percentage == pytest.approx(100.0)
        assert stored.status == EntityStatus.COMPLETED
