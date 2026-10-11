"""The two context integrations act on the caller's own goal or habit, over real HTTP.

``POST /api/context/goal/tasks`` creates tasks from a goal and
``POST /api/context/habit/complete`` completes a habit. Each route verifies the
caller owns the uid it names before the service behind it runs (ADR-085 — the
route mediates, the service holds no owner compare of its own).

The goal → task generator the first route (and ``POST /goals/generate-tasks``)
runs reads the goal's required knowledge and supporting habits, and links each
created knowledge task to the knowledge it names through the Tasks facade, whose
far-end admission runs first.

The contract:

- another user's goal or habit is answered exactly as a uid that names nothing —
  same status, same body, same toast — and nothing is written for either user;
- the caller's own goal is answered 201 with tasks the caller owns, and the
  caller's own habit 200;
- a created "Learn" task APPLIES_KNOWLEDGE its subject (a learning opportunity)
  and REQUIRES_KNOWLEDGE each unmet prerequisite of it; a "Practice habit" task
  REINFORCES_HABIT the habit that supports the goal.

The entities are created at the domains' real create doors, so each carries the
label, the ``entity_type`` and the ownership edge the app itself writes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.lateral_routes_client import without_timestamp
from tests.integration._activity_link_rig import create, signed_in_client, write_edge

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

CALLER = "user_ctxdoor_caller"
OTHER = "user_ctxdoor_other"  # owns the foreign goal and habit
CALLER_MARK = "ctxdoor-caller"
OTHER_MARK = "ctxdoor-other"

# Shared knowledge: the subject a goal requires, and a prerequisite of that subject.
KU_SUBJECT = "ku_ctxdoor-caller_subject"
KU_PREREQ = "ku_ctxdoor-caller_prereq"

MISSING_GOAL = "goal_ctxdoor-caller_missing"
MISSING_HABIT = "habit_ctxdoor-caller_missing"

# Text only the foreign entities carry — it must reach no response.
FOREIGN_TEXT = "ctxdoor-foreign-private"


class World(NamedTuple):
    client: httpx.AsyncClient
    driver: AsyncDriver
    own_goal: str
    own_habit: str
    foreign_goal: str
    foreign_habit: str


async def _seed_shared_ku(driver: AsyncDriver, uid: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (k:Entity:Ku {uid: $uid})
            SET k.title = $uid, k.entity_type = 'ku', k.status = 'active'
            """,
            uid=uid,
        )


@pytest_asyncio.fixture(loop_scope="session")
async def world(skuel_app) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, OTHER, OTHER_MARK) as other:
        foreign_goal = await create(other, "goals", f"{FOREIGN_TEXT} goal")
        foreign_habit = await create(other, "habits", f"{FOREIGN_TEXT} habit")
        async with signed_in_client(skuel_app, CALLER, CALLER_MARK) as client:
            await _seed_shared_ku(driver, KU_SUBJECT)
            await _seed_shared_ku(driver, KU_PREREQ)
            await write_edge(driver, KU_SUBJECT, "REQUIRES_KNOWLEDGE", KU_PREREQ)
            await write_edge(driver, CALLER, "IN_PROGRESS", KU_SUBJECT, {"progress": 0.3})
            own_habit = await create(client, "habits", f"{CALLER_MARK} habit")
            own_goal = await create(
                client,
                "goals",
                f"{CALLER_MARK} goal",
                required_knowledge_uids=[KU_SUBJECT],
                supporting_habit_uids=[own_habit],
            )
            yield World(client, driver, own_goal, own_habit, foreign_goal, foreign_habit)


async def _owned_tasks(driver: AsyncDriver, user_uid: str) -> set[str]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (:User {uid: $user})-[:OWNS]->(t:Task) RETURN t.uid AS uid", user=user_uid
        )
        return {row["uid"] async for row in result}


async def _node(driver: AsyncDriver, uid: str) -> dict[str, object]:
    async with driver.session() as session:
        record = await (
            await session.run("MATCH (n:Entity {uid: $uid}) RETURN properties(n) AS p", uid=uid)
        ).single()
    assert record is not None, uid
    return dict(record["p"])


async def _task_edges(
    driver: AsyncDriver, task_uids: set[str]
) -> set[tuple[str, str, str, object]]:
    """``(task title, edge, far uid, is_learning_opportunity)`` for each knowledge or
    habit edge out of the tasks."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (t:Task)-[r:APPLIES_KNOWLEDGE|REQUIRES_KNOWLEDGE|REINFORCES_HABIT]->(far)
            WHERE t.uid IN $uids
            RETURN t.title AS title, type(r) AS edge, far.uid AS far,
                   r.is_learning_opportunity AS learning
            """,
            uids=list(task_uids),
        )
        return {(row["title"], row["edge"], row["far"], row["learning"]) async for row in result}


def _parity(response: httpx.Response, uid: str) -> tuple[int, str, str]:
    """A refusal with its timestamp removed and the requested uid masked."""
    body = str(without_timestamp(response)).replace(uid, "<uid>")
    toast = response.headers.get("X-Toast-Message", "").replace(uid, "<uid>")
    return response.status_code, body, toast


async def test_another_users_goal_answers_as_missing_and_writes_nothing(world: World) -> None:
    before = {u: await _owned_tasks(world.driver, u) for u in (CALLER, OTHER)}

    foreign = await world.client.post(
        f"/api/context/goal/tasks?goal_uid={world.foreign_goal}", json={"auto_create": True}
    )
    missing = await world.client.post(
        f"/api/context/goal/tasks?goal_uid={MISSING_GOAL}", json={"auto_create": True}
    )

    assert foreign.status_code == 404, foreign.text
    assert _parity(foreign, world.foreign_goal) == _parity(missing, MISSING_GOAL)
    assert FOREIGN_TEXT not in foreign.text
    assert {u: await _owned_tasks(world.driver, u) for u in (CALLER, OTHER)} == before


async def test_another_users_habit_answers_as_missing_and_is_not_completed(
    world: World,
) -> None:
    before = await _node(world.driver, world.foreign_habit)

    foreign = await world.client.post(
        f"/api/context/habit/complete?habit_uid={world.foreign_habit}", json={"quality": "good"}
    )
    missing = await world.client.post(
        f"/api/context/habit/complete?habit_uid={MISSING_HABIT}", json={"quality": "good"}
    )

    assert foreign.status_code == 404, foreign.text
    assert _parity(foreign, world.foreign_habit) == _parity(missing, MISSING_HABIT)
    assert FOREIGN_TEXT not in foreign.text
    assert await _node(world.driver, world.foreign_habit) == before


async def test_own_habit_is_completed(world: World) -> None:
    response = await world.client.post(
        f"/api/context/habit/complete?habit_uid={world.own_habit}", json={"quality": "good"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["uid"] == world.own_habit


async def test_own_goal_tasks_are_linked_to_the_knowledge_and_habit_they_name(
    world: World,
) -> None:
    """The context door builds the rich context, so the subject's unmet prerequisite is
    known: the Learn task requires it."""
    before = await _owned_tasks(world.driver, CALLER)

    response = await world.client.post(
        f"/api/context/goal/tasks?goal_uid={world.own_goal}", json={"auto_create": True}
    )

    assert response.status_code == 201, response.text
    created = await _owned_tasks(world.driver, CALLER) - before
    assert {task["uid"] for task in response.json()} == created
    assert await _owned_tasks(world.driver, OTHER) == set()
    edges = await _task_edges(world.driver, created)
    learn = f"Learn: {KU_SUBJECT}"
    practice = f"Practice habit: {world.own_habit}"
    assert edges == {
        (learn, "APPLIES_KNOWLEDGE", KU_SUBJECT, True),
        (learn, "REQUIRES_KNOWLEDGE", KU_PREREQ, None),
        (practice, "REINFORCES_HABIT", world.own_habit, None),
    }


async def test_generate_tasks_links_the_learn_task_to_its_subject(world: World) -> None:
    """``POST /goals/generate-tasks`` runs the same generator with a bare context: no
    prerequisite is known, so the Learn task applies its subject and requires nothing."""
    before = await _owned_tasks(world.driver, CALLER)

    response = await world.client.post(
        f"/goals/generate-tasks?uid={world.own_goal}&auto_create=true"
    )

    assert response.status_code == 200, response.text
    created = await _owned_tasks(world.driver, CALLER) - before
    assert created
    knowledge_edges = {
        edge for edge in await _task_edges(world.driver, created) if edge[1] != "REINFORCES_HABIT"
    }
    assert knowledge_edges == {(f"Learn: {KU_SUBJECT}", "APPLIES_KNOWLEDGE", KU_SUBJECT, True)}
