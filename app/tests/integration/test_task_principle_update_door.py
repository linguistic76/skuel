"""A task update replaces the task's principles — through ``POST /api/tasks/update``.

A task is aligned with a principle through ``(Task)-[:ALIGNED_WITH_PRINCIPLE]->(Principle)``.
The update door's ``aligned_principle_uids`` is a FULL REPLACE of those edges: a list
replaces the set, ``[]`` clears it, and an update without the field leaves it alone. Each
new edge is admitted as task create admits it — the far end must be a principle the
caller owns — and the uids never land as a node property. An update carrying only the
list is an edge-only update, and still announces ``TaskUpdated``.

Each test reads the stored edges and the task's own property keys after real HTTP
requests to the generated CRUD update route, over the composed app
(``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.events import TaskUpdated
from core.models.relationship_names import RelationshipName
from tests.integration._activity_link_rig import (
    create,
    published,
    signed_in_client,
    wipe,
    write_edge,
)

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

MARK = "zzztaskprin"
CALLER = f"user_{MARK}"
OTHER = f"user_{MARK}_other"

ALIGNED_WITH_PRINCIPLE = RelationshipName.ALIGNED_WITH_PRINCIPLE.value


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    services: Any  # boundary: the composed Services container
    driver: AsyncDriver


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[Env]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        yield Env(client=client, services=skuel_app.state.services, driver=driver)
    await wipe(driver, OTHER, MARK)


async def _task(env: Env, name: str) -> str:
    return await create(env.client, "tasks", f"{MARK} {name}")


async def _principle(env: Env, name: str) -> str:
    return await create(env.client, "principles", f"{MARK} {name}")


async def _update(env: Env, task: str, **body: Any) -> None:  # boundary: JSON body
    response = await env.client.post(f"/api/tasks/update?uid={task}", json=body)
    assert response.status_code == 200, response.text[:500]


async def _principles_of(env: Env, task: str) -> set[str]:
    async with env.driver.session() as session:
        result = await session.run(
            f"MATCH (:Task {{uid: $uid}})-[:{ALIGNED_WITH_PRINCIPLE}]->(p) RETURN p.uid AS uid",
            uid=task,
        )
        return {row["uid"] async for row in result}


async def _property_keys(env: Env, task: str) -> set[str]:
    async with env.driver.session() as session:
        record = await (
            await session.run("MATCH (t:Task {uid: $uid}) RETURN keys(t) AS keys", uid=task)
        ).single()
    assert record is not None, task
    return set(record["keys"])


async def test_a_list_writes_one_edge_per_principle_and_no_property(env: Env) -> None:
    task = await _task(env, "list")
    first = await _principle(env, "list first")
    second = await _principle(env, "list second")

    await _update(env, task, aligned_principle_uids=[first, second])

    assert await _principles_of(env, task) == {first, second}
    assert "aligned_principle_uids" not in await _property_keys(env, task)


async def test_a_list_replaces_the_stored_set_and_an_empty_list_clears(env: Env) -> None:
    """The task's two edges are written straight into the graph, so the update is the one
    thing that can change them."""
    task = await _task(env, "replace")
    first = await _principle(env, "replace first")
    second = await _principle(env, "replace second")
    for principle in (first, second):
        await write_edge(env.driver, task, ALIGNED_WITH_PRINCIPLE, principle)

    await _update(env, task, aligned_principle_uids=[second])
    assert await _principles_of(env, task) == {second}

    await _update(env, task, aligned_principle_uids=[])
    assert await _principles_of(env, task) == set()
    assert "aligned_principle_uids" not in await _property_keys(env, task)


async def test_an_update_without_the_field_leaves_the_principles(env: Env) -> None:
    task = await _task(env, "absent")
    principle = await _principle(env, "absent kept")
    await write_edge(env.driver, task, ALIGNED_WITH_PRINCIPLE, principle)

    await _update(env, task, title=f"{MARK} absent renamed")

    assert await _principles_of(env, task) == {principle}


async def test_another_users_principle_and_a_non_principle_are_refused(env: Env) -> None:
    """Three uids in one list differ only in what they name: the caller's principle is
    linked; another user's principle and the caller's own goal are not."""
    task = await _task(env, "refused")
    mine = await _principle(env, "refused mine")
    goal = await create(env.client, "goals", f"{MARK} refused goal")
    theirs = f"principle.{MARK}.theirs"
    async with env.driver.session() as session:
        await session.run(
            """
            MERGE (u:User {uid: $other}) SET u.title = $other
            CREATE (p:Entity:Principle {uid: $uid, entity_type: 'principle', title: $uid,
                                        status: 'active', user_uid: $other})
            CREATE (u)-[:OWNS]->(p)
            """,
            other=OTHER,
            uid=theirs,
        )

    await _update(env, task, aligned_principle_uids=[mine, theirs, goal])

    assert await _principles_of(env, task) == {mine}
    assert "aligned_principle_uids" not in await _property_keys(env, task)


async def test_an_update_carrying_only_principles_succeeds_and_announces_task_updated(
    env: Env,
) -> None:
    task = await _task(env, "edge only")
    principle = await _principle(env, "edge only")

    with published(env.services.event_bus, TaskUpdated) as seen:
        await _update(env, task, aligned_principle_uids=[principle])

    assert await _principles_of(env, task) == {principle}
    [announced] = [event for event in seen if event.task_uid == task]
    assert "aligned_principle_uids" in announced.updated_fields
