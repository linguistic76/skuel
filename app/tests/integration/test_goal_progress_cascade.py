"""
Goal progress moves when a linked task or habit is completed — through the composed app.

Every link in this file is written by a production writer and every completion goes
through a production door, with the event wiring the app composes at bootstrap:

- Task → Goal: ``TasksService.create`` with ``fulfills_goal_uid`` dual-writes the stamp
  and ``(Task)-[:FULFILLS_GOAL]->(Goal)``; ``TasksService.update_task`` to ``completed``
  publishes ``TaskCompleted``.
- Habit → Goal: ``GoalsService.link_goal_to_habit`` writes
  ``(Habit)-[:SUPPORTS_GOAL]->(Goal)``; ``HabitsService.complete_habit_with_quality``
  publishes ``HabitCompleted``.

A task that leaves ``completed`` — through ``update_task`` or through the vault ingest
door — publishes ``TaskReopened``, and the same recompute lowers its goal and un-achieves
it (ruled 2026-09-23, ``docs/roadmap/done/goal-progress-one-way.md``).

``GoalsProgressService`` subscribes to all three events and reads the links back through
``GoalsBackend``. A reader that matches a shape no writer produces returns no goals, the
handler logs at DEBUG and returns, and the goal never moves — so these tests assert on the
goal the handler writes, not on the handler being called.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import Domain, EntityStatus, Priority
from core.models.enums.entity_enums import EntityType
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent
from core.ports import EventBusOperations
from core.services.goals_service import GoalsService
from core.services.habits_service import HabitsService
from core.services.tasks_service import TasksService
from core.services.user.unified_user_context import UserContext
from services_bootstrap._container import Services

pytestmark = pytest.mark.skipif(
    IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
    reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
)

_USER_UID = "user_goal_progress_cascade"
_PREFIX = "gpc_"
#: Vault-authored uids carry their type prefix (``task.``), so they get their own sweep.
_VAULT_TASK_PREFIX = "task.gpc-"


@dataclass(frozen=True)
class _Composed:
    """The composed facades these tests drive — ``Services`` fields narrowed from ``| None``."""

    tasks: TasksService
    goals: GoalsService
    habits: HabitsService
    event_bus: EventBusOperations
    neo4j_driver: AsyncDriver


@pytest_asyncio.fixture(loop_scope="session")
async def services(skuel_app) -> AsyncIterator[_Composed]:
    """The composed services, with this module's user seeded and its entities swept after.

    ``skuel_app``'s graph is session-scoped and shared, so every entity here carries the
    ``gpc_`` prefix and is removed on teardown.
    """
    composed: Services = skuel_app.state.services
    assert composed.tasks and composed.goals and composed.habits and composed.neo4j_driver
    assert composed.event_bus
    services = _Composed(
        tasks=composed.tasks,
        goals=composed.goals,
        habits=composed.habits,
        event_bus=composed.event_bus,
        neo4j_driver=composed.neo4j_driver,
    )
    driver = services.neo4j_driver
    async with driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) SET u.username = $uid, u.email = $email",
            uid=_USER_UID,
            email=f"{_USER_UID}@example.test",
        )
    yield services
    async with driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid STARTS WITH $prefix DETACH DELETE n",
            prefix=_PREFIX,
        )
        await session.run(
            "MATCH (n:Entity) WHERE n.uid STARTS WITH $prefix DETACH DELETE n",
            prefix=_VAULT_TASK_PREFIX,
        )
        await session.run(
            "MATCH (m:IngestionMetadata) WHERE m.entity_uid STARTS WITH $prefix DELETE m",
            prefix=_VAULT_TASK_PREFIX,
        )


async def _create_goal(services: _Composed, slug: str, measurement: MeasurementType) -> Goal:
    result = await services.goals.create(
        Goal(
            uid=f"{_PREFIX}goal_{slug}",
            user_uid=_USER_UID,
            title=f"Goal {slug}",
            domain=Domain.TECH,
            measurement_type=measurement,
            progress_percentage=0.0,
            current_value=0.0,
            target_value=10.0,
            status=EntityStatus.ACTIVE,
        )
    )
    assert result.is_ok, result
    return result.value


async def _stored_goal(services: _Composed, goal_uid: str) -> Goal:
    result = await services.goals.backend.get(goal_uid)
    assert result.is_ok and result.value is not None, result
    return result.value


@pytest.mark.asyncio(loop_scope="session")
async def test_completing_a_linked_task_moves_its_goal(services: _Composed) -> None:
    """One of two linked tasks completed through ``update_task`` → the goal reads 50%."""
    goal = await _create_goal(services, "task_based", MeasurementType.TASK_BASED)

    task_uids = []
    for i in (1, 2):
        created = await services.tasks.create(
            Task(
                uid=f"{_PREFIX}task_{i}",
                user_uid=_USER_UID,
                title=f"Task {i}",
                priority=Priority.MEDIUM,
                status=EntityStatus.SCHEDULED,
                fulfills_goal_uid=goal.uid,
            )
        )
        assert created.is_ok, created
        # The create door clears the stamp when it could not write the edge, so a
        # surviving stamp means (Task)-[:FULFILLS_GOAL]->(Goal) exists.
        assert created.value.fulfills_goal_uid == goal.uid
        task_uids.append(created.value.uid)

    completed = await services.tasks.update_task(
        task_uids[0], TaskUpdateIntent(status=EntityStatus.COMPLETED.value)
    )
    assert completed.is_ok, completed

    stored = await _stored_goal(services, goal.uid)
    assert stored.progress_percentage == pytest.approx(50.0)
    assert (stored.current_value, stored.target_value) == (1, 2)


@pytest.mark.asyncio(loop_scope="session")
async def test_completing_a_linked_habit_moves_its_goal(services: _Composed) -> None:
    """A habit linked by ``link_goal_to_habit`` and completed once → streak 1 of 10 = 10%."""
    goal = await _create_goal(services, "habit_based", MeasurementType.HABIT_BASED)

    created = await services.habits.create(
        Habit(
            uid=f"{_PREFIX}habit",
            user_uid=_USER_UID,
            entity_type=EntityType.HABIT,
            title="Daily habit",
            current_streak=0,
            best_streak=0,
        )
    )
    assert created.is_ok, created
    habit = created.value

    linked = await services.goals.link_goal_to_habit(goal.uid, habit.uid)
    assert linked.is_ok, linked

    completed = await services.habits.complete_habit_with_quality(
        habit.uid, UserContext(user_uid=_USER_UID)
    )
    assert completed.is_ok, completed
    assert completed.value.current_streak == 1

    stored = await _stored_goal(services, goal.uid)
    assert stored.progress_percentage == pytest.approx(10.0)


@pytest.mark.asyncio(loop_scope="session")
async def test_achievement_context_reads_the_written_links(services: _Composed) -> None:
    """``get_achievement_context`` returns the habits and Kus the goal writers linked."""
    goal = await _create_goal(services, "achieved", MeasurementType.PERCENTAGE)

    habit = await services.habits.create(
        Habit(
            uid=f"{_PREFIX}ctx_habit",
            user_uid=_USER_UID,
            entity_type=EntityType.HABIT,
            title="Context habit",
        )
    )
    assert habit.is_ok, habit
    async with services.neo4j_driver.session() as session:
        await session.run(
            "CREATE (:Entity:Ku {uid: $uid, entity_type: $type, title: 'Context Ku'})",
            uid=f"{_PREFIX}ku",
            type=EntityType.KU.value,
        )

    assert (await services.goals.link_goal_to_habit(goal.uid, habit.value.uid)).is_ok
    assert (await services.goals.link_goal_to_knowledge(goal.uid, f"{_PREFIX}ku")).is_ok

    result = await services.goals.backend.get_achievement_context(goal.uid, _USER_UID)
    assert result.is_ok, result
    [row] = result.value
    assert [h["uid"] for h in row["habits"]] == [habit.value.uid]
    assert [k["uid"] for k in row["knowledge_units"]] == [f"{_PREFIX}ku"]


async def _assert_unachieved(services: _Composed, goal_uid: str) -> None:
    """0 of 1, 0%, no longer COMPLETED, and no achievement date left behind."""
    stored = await _stored_goal(services, goal_uid)
    assert (stored.current_value, stored.target_value) == (0, 1)
    assert stored.progress_percentage == pytest.approx(0.0)
    assert stored.status == EntityStatus.ACTIVE
    assert stored.achieved_date is None


@pytest.mark.asyncio(loop_scope="session")
async def test_reopening_the_only_task_through_update_task_unachieves_its_goal(
    services: _Composed,
) -> None:
    """Complete a goal's only task (100%, COMPLETED), then reopen it through ``update_task``."""
    goal = await _create_goal(services, "reopen_app", MeasurementType.TASK_BASED)
    created = await services.tasks.create(
        Task(
            uid=f"{_PREFIX}task_reopen_app",
            user_uid=_USER_UID,
            title="Only task",
            priority=Priority.MEDIUM,
            status=EntityStatus.SCHEDULED,
            fulfills_goal_uid=goal.uid,
        )
    )
    assert created.is_ok, created
    task_uid = created.value.uid

    done = await services.tasks.update_task(
        task_uid, TaskUpdateIntent(status=EntityStatus.COMPLETED.value)
    )
    assert done.is_ok, done
    achieved = await _stored_goal(services, goal.uid)
    assert achieved.status == EntityStatus.COMPLETED
    assert achieved.progress_percentage == pytest.approx(100.0)

    reopened = await services.tasks.update_task(
        task_uid, TaskUpdateIntent(status=EntityStatus.SCHEDULED.value)
    )
    assert reopened.is_ok, reopened

    await _assert_unachieved(services, goal.uid)


def _vault_task_file(directory: Path, goal_uid: str, status_lines: str) -> Path:
    path = directory / "gpc-vault-reopen.md"
    path.write_text(
        f"---\ntype: task\nuid: {_VAULT_TASK_PREFIX}vault-reopen\ntitle: Vault task\n"
        f"user_uid: {_USER_UID}\n{status_lines}"
        f"connections:\n  fulfills_goal:\n    - {goal_uid}\n---\n\nBody.\n"
    )
    return path


@pytest.mark.asyncio(loop_scope="session")
async def test_reopening_the_only_task_in_the_vault_unachieves_its_goal(
    services: _Composed, tmp_path: Path
) -> None:
    """A task file completed, then edited back open, through the vault ingest door.

    The door classifies the reopen from the prior status its upsert returned, and
    publishes ``TaskReopened`` so goal progress hears the vault's reopens as it hears
    the app's. Built over the COMPOSED event bus, so the subscriber is the one the app
    wires; built here rather than taken from the composition because the composed door
    resolves a file's owner from the vault it sits in, and a temp directory is in none.
    """
    goal = await _create_goal(services, "reopen_vault", MeasurementType.TASK_BASED)
    door = make_unified_ingestion_service(
        services.neo4j_driver, event_bus=services.event_bus, default_user_uid=_USER_UID
    )

    completed_file = _vault_task_file(
        tmp_path, goal.uid, "status: completed\ncompletion_date: 2026-09-01\n"
    )
    assert (await door.ingest_file(completed_file)).is_ok
    achieved = await _stored_goal(services, goal.uid)
    assert achieved.status == EntityStatus.COMPLETED
    assert achieved.progress_percentage == pytest.approx(100.0)

    reopened_file = _vault_task_file(tmp_path, goal.uid, "status: in_progress\n")
    assert (await door.ingest_file(reopened_file)).is_ok

    await _assert_unachieved(services, goal.uid)
