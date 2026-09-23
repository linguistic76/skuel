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

``GoalsProgressService`` subscribes to both events and reads the links back through
``GoalsBackend``. A reader that matches a shape no writer produces returns no goals, the
handler logs at DEBUG and returns, and the goal never moves — so these tests assert on the
goal the handler writes, not on the handler being called.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import Domain, EntityStatus, Priority
from core.models.enums.entity_enums import EntityType
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent
from core.services.user.unified_user_context import UserContext

pytestmark = pytest.mark.skipif(
    IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
    reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
)

_USER_UID = "user_goal_progress_cascade"
_PREFIX = "gpc_"


@pytest_asyncio.fixture(loop_scope="session")
async def services(skuel_app) -> AsyncIterator[Any]:
    """The composed services, with this module's user seeded and its entities swept after.

    ``skuel_app``'s graph is session-scoped and shared, so every entity here carries the
    ``gpc_`` prefix and is removed on teardown.
    """
    services = skuel_app.state.services
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


async def _create_goal(services: Any, slug: str, measurement: MeasurementType) -> Goal:
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


async def _stored_goal(services: Any, goal_uid: str) -> Goal:
    result = await services.goals.backend.get(goal_uid)
    assert result.is_ok and result.value is not None, result
    return result.value


@pytest.mark.asyncio(loop_scope="session")
async def test_completing_a_linked_task_moves_its_goal(services: Any) -> None:
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
async def test_completing_a_linked_habit_moves_its_goal(services: Any) -> None:
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
async def test_achievement_context_reads_the_written_links(services: Any) -> None:
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
