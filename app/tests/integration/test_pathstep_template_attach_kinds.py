"""A template is attached only to a PathStep, and only a template of the door's own kind.

``POST /api/pathstep-{domain}-templates/attach`` writes ``(PathStep)-[:HAS_*_TEMPLATE]->
(template)``; ``/detach`` removes it; ``GET /list-by-ps`` reads it back with every
property of the far node. The attach door is the one place a request names both ends,
so the service that writes the edge admits both: the source is a PathStep and the far
end carries the template label of the door it came through. Anything else — another
user's Goal, a Task posing as the PathStep, a template of another kind, a uid that names
nothing — is refused as not-found, alike, and writes nothing. Detach refuses the same
pairs; a right-kind pair that is not attached detaches as a no-op.

The reader binds the same two labels, so an edge written past the door (by raw Cypher
here) never hands ``list-by-ps`` another node's properties.

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.integration._activity_link_rig import (
    create,
    edges_between,
    seed_published_path_step,
    signed_in_client,
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

MARK = "zzztplattach"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark,
# so neither may carry the other's.
TEACHER_MARK = f"{MARK}t"
OTHER_MARK = f"{MARK}o"
TEACHER = f"user_{TEACHER_MARK}"
OTHER = f"user_{OTHER_MARK}"
PATH_STEP = f"ps.{MARK}.step"
MISSING = f"gtpl_{MARK}_missing"
FOREIGN_TITLE = f"{MARK}-foreign-goal"
GOAL_TEMPLATE_DOOR = "/api/pathstep-goal-templates"


async def _make_teacher(driver: AsyncDriver, uid: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $uid})
            SET u.username = $uid, u.display_name = $uid, u.email = $uid + '@example.com',
                u.role = 'teacher', u.created_at = datetime(), u.updated_at = datetime()
            """,
            uid=uid,
        )


async def _delete_nodes(driver: AsyncDriver, uids: list[str]) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=uids)


def _uidless(body: str, *uids: str) -> str:
    for uid in uids:
        body = body.replace(uid, "<uid>")
    return re.sub(r'"timestamp":"[^"]*"', '"timestamp":"<t>"', body)


class World:
    """The teacher's client and the nodes the doors are asked about."""

    def __init__(
        self,
        driver: AsyncDriver,
        teacher: httpx.AsyncClient,
        goal_template: str,
        task_template: str,
        foreign_goal: str,
        foreign_task: str,
    ) -> None:
        self.driver = driver
        self.teacher = teacher
        self.goal_template = goal_template
        self.task_template = task_template
        self.foreign_goal = foreign_goal
        self.foreign_task = foreign_task

    async def attach(self, ps_uid: str, template_uid: str) -> httpx.Response:
        return await self.teacher.post(
            f"{GOAL_TEMPLATE_DOOR}/attach", params={"ps_uid": ps_uid, "template_uid": template_uid}
        )

    async def detach(self, ps_uid: str, template_uid: str) -> httpx.Response:
        return await self.teacher.post(
            f"{GOAL_TEMPLATE_DOOR}/detach", params={"ps_uid": ps_uid, "template_uid": template_uid}
        )

    async def listed(self, ps_uid: str) -> httpx.Response:
        return await self.teacher.get(f"{GOAL_TEMPLATE_DOOR}/list-by-ps", params={"ps_uid": ps_uid})

    async def edge_types(self, source: str, target: str) -> list[str]:
        return [
            e.type for e in await edges_between(self.driver, source, target) if e.source == source
        ]


@pytest_asyncio.fixture(loop_scope="session")
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, OTHER, OTHER_MARK) as other,
        signed_in_client(skuel_app, TEACHER, TEACHER_MARK) as teacher,
    ):
        await _make_teacher(driver, TEACHER)
        await seed_published_path_step(driver, PATH_STEP, f"{MARK}-step")
        foreign_goal = await create(other, "goals", FOREIGN_TITLE)
        foreign_task = await create(other, "tasks", f"{MARK}-foreign-task")
        goal_template = await create(teacher, "pathstep-goal-templates", f"{MARK}-goal-template")
        task_template = await create(teacher, "pathstep-task-templates", f"{MARK}-task-template")
        try:
            yield World(driver, teacher, goal_template, task_template, foreign_goal, foreign_task)
        finally:
            await _delete_nodes(driver, [PATH_STEP, goal_template, task_template])


async def test_attach_refuses_a_far_end_that_is_not_this_doors_template(world: World) -> None:
    """Another user's Goal and a Task template are refused at the Goal-template door."""
    for far in (world.foreign_goal, world.task_template):
        response = await world.attach(PATH_STEP, far)
        assert response.status_code == 404, (far, response.text)
        assert await world.edge_types(PATH_STEP, far) == []


async def test_attach_refuses_a_source_that_is_not_a_pathstep(world: World) -> None:
    """Another user's Task posing as the PathStep is refused; nothing hangs off it."""
    response = await world.attach(world.foreign_task, world.goal_template)
    assert response.status_code == 404, response.text
    assert await world.edge_types(world.foreign_task, world.goal_template) == []


async def test_a_wrong_kind_answers_exactly_as_a_missing_uid(world: World) -> None:
    """No refusal confirms that a node exists: missing ≡ wrong kind, on both doors."""
    for door in (world.attach, world.detach):
        missing = await door(PATH_STEP, MISSING)
        foreign = await door(PATH_STEP, world.foreign_goal)
        assert missing.status_code == foreign.status_code == 404
        assert _uidless(missing.text, MISSING) == _uidless(foreign.text, world.foreign_goal)


async def test_attach_and_detach_a_real_template(world: World) -> None:
    """Positive control: the door's own template attaches, lists, and detaches."""
    attached = await world.attach(PATH_STEP, world.goal_template)
    assert attached.status_code == 200, attached.text
    assert await world.edge_types(PATH_STEP, world.goal_template) == ["HAS_GOAL_TEMPLATE"]

    listed = await world.listed(PATH_STEP)
    assert listed.status_code == 200, listed.text
    assert world.goal_template in listed.text

    detached = await world.detach(PATH_STEP, world.goal_template)
    assert detached.status_code == 200, detached.text
    assert await world.edge_types(PATH_STEP, world.goal_template) == []

    again = await world.detach(PATH_STEP, world.goal_template)
    assert again.status_code == 200, again.text


async def test_detach_refuses_a_wrong_kind_pair_and_leaves_its_edge(world: World) -> None:
    """A stray edge to another user's Goal is no business of the template door."""
    await write_edge(world.driver, PATH_STEP, "HAS_GOAL_TEMPLATE", world.foreign_goal)
    try:
        response = await world.detach(PATH_STEP, world.foreign_goal)
        assert response.status_code == 404, response.text
    finally:
        async with world.driver.session() as session:
            await session.run(
                "MATCH (:PathStep {uid: $ps})-[r:HAS_GOAL_TEMPLATE]->(:Goal {uid: $g}) DELETE r",
                ps=PATH_STEP,
                g=world.foreign_goal,
            )


async def test_list_by_ps_never_reads_a_stray_edges_far_node(world: World) -> None:
    """An edge written past the door does not hand the reader another user's Goal."""
    assert (await world.attach(PATH_STEP, world.goal_template)).status_code == 200
    await write_edge(world.driver, PATH_STEP, "HAS_GOAL_TEMPLATE", world.foreign_goal)
    try:
        listed = await world.listed(PATH_STEP)
        assert listed.status_code == 200, listed.text
        assert world.goal_template in listed.text
        assert FOREIGN_TITLE not in listed.text
        assert world.foreign_goal not in listed.text
    finally:
        async with world.driver.session() as session:
            await session.run(
                "MATCH (:PathStep {uid: $ps})-[r:HAS_GOAL_TEMPLATE]->() DELETE r", ps=PATH_STEP
            )
