"""A PERSONAL exercise anchored to a published PathStep is the step's: any learner reads it.

A teacher who attaches their PERSONAL exercise to a shared PathStep
(``Exercise.path_step_uid`` + ``(PathStep)-[:HAS_EXERCISE]->(Exercise)``, dual-written at
the create door) contributes it to that step. The step page lists it to every learner,
and a learner in progress on the step may turn in against it, so the learner's read
surface — ``/exercises/get`` → ``/exercises/get/content`` (and the ``.md`` download) —
must open it too, or every link the listing renders lands on "not found".

The anchor admits only while the step is published: a draft step publishes nothing.
An unanchored PERSONAL exercise stays its owner's, and its refusal reads the same as a
uid naming nothing. The owner's own read, CURRICULUM's open read, and the ASSIGNED
group read are unchanged; the anchor admits PERSONAL scope alone.

The exercises are made at the real create door, as the teacher; the learner has no tie
to the teacher.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import ExerciseScope
from core.models.type_hints import UserUID
from tests.integration._activity_link_rig import (
    create,
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

MARK = "zzzanchorex"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
TEACHER_MARK = f"{MARK}t"
LEARNER_MARK = f"{MARK}l"
TEACHER = f"user_{TEACHER_MARK}"
LEARNER = f"user_{LEARNER_MARK}"  # a member with no tie to the teacher
PS_PUBLISHED = f"ps.{TEACHER_MARK}.published"
PS_DRAFT = f"ps.{TEACHER_MARK}.draft"
CURRICULUM_EX = f"ex.{TEACHER_MARK}.curriculum"
ASSIGNED_EX = f"ex.{TEACHER_MARK}.assigned"
MISSING_EX = f"ex.{TEACHER_MARK}.missing"

FRAGMENT = "/exercises/get/content"
MD = "/api/exercises/md"


async def _set_role(driver: AsyncDriver, uid: str, role: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $uid})
            SET u.username = $uid, u.display_name = $uid, u.email = $uid + '@example.com',
                u.role = $role, u.created_at = datetime(), u.updated_at = datetime()
            """,
            uid=uid,
            role=role,
        )


async def _seed_draft_path_step(driver: AsyncDriver, uid: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (s:Entity:PathStep {uid: $uid})
            SET s.title = $uid, s.entity_type = 'path_step', s.status = 'active',
                s.publication_state = 'draft'
            """,
            uid=uid,
        )


async def _seed_exercise(driver: AsyncDriver, uid: str, scope: ExerciseScope) -> None:
    """An exercise the create door cannot make (CURRICULUM is vault-only) or one shaped
    by hand (an ASSIGNED exercise hanging from a step)."""
    async with driver.session() as session:
        await session.run(
            """
            MERGE (ex:Entity:Exercise {uid: $uid})
            SET ex.title = $uid, ex.entity_type = 'exercise', ex.scope = $scope,
                ex.instructions = $uid + ' instructions', ex.status = 'active'
            """,
            uid=uid,
            scope=scope.value,
        )


async def _delete_owned(driver: AsyncDriver, users: list[str]) -> None:
    """Exercises carry no mark in their generated uids — remove them by owner."""
    async with driver.session() as session:
        await session.run(
            "MATCH (u:User)-[:OWNS]->(n) WHERE u.uid IN $users DETACH DELETE n", users=users
        )


def _normalised(body: str, uid: str) -> str:
    return re.sub(r"-[0-9a-f]{8}\b", "-<id>", body.replace(uid, "<uid>"))


class World:
    def __init__(
        self,
        skuel_app: Any,  # boundary: fasthtml-app
        clients: dict[str, httpx.AsyncClient],
        anchored: str,
        unanchored: str,
        draft_anchored: str,
    ) -> None:
        self.skuel_app = skuel_app
        self.driver: AsyncDriver = skuel_app.state.services.neo4j_driver
        self.clients = clients
        self.anchored = anchored  # PERSONAL, anchored to the published step
        self.unanchored = unanchored  # PERSONAL, no anchor
        self.draft_anchored = draft_anchored  # PERSONAL, anchored to the draft step

    async def read(self, caller: str, uid: str) -> httpx.Response:
        return await self.clients[caller].get(FRAGMENT, params={"uid": uid})


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, TEACHER, TEACHER_MARK) as teacher,
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
    ):
        await _set_role(driver, TEACHER, "teacher")
        await _set_role(driver, LEARNER, "member")
        await seed_published_path_step(driver, PS_PUBLISHED, f"{MARK} published step")
        await _seed_draft_path_step(driver, PS_DRAFT)
        await _seed_exercise(driver, CURRICULUM_EX, ExerciseScope.CURRICULUM)
        await _seed_exercise(driver, ASSIGNED_EX, ExerciseScope.ASSIGNED)
        await write_edge(driver, PS_PUBLISHED, "HAS_EXERCISE", ASSIGNED_EX)
        try:
            anchored = await create(
                teacher,
                "exercises",
                f"{MARK}-anchored",
                name=f"{MARK}-anchored",
                instructions=f"{MARK} anchored instructions",
                path_step_uid=PS_PUBLISHED,
            )
            unanchored = await create(
                teacher,
                "exercises",
                f"{MARK}-unanchored",
                name=f"{MARK}-unanchored",
                instructions=f"{MARK} unanchored instructions",
            )
            draft_anchored = await create(
                teacher,
                "exercises",
                f"{MARK}-draftanchored",
                name=f"{MARK}-draftanchored",
                instructions=f"{MARK} draftanchored instructions",
                path_step_uid=PS_DRAFT,
            )
            yield World(
                skuel_app,
                {TEACHER: teacher, LEARNER: learner},
                anchored,
                unanchored,
                draft_anchored,
            )
        finally:
            await _delete_owned(driver, [TEACHER, LEARNER])


async def test_the_create_door_anchors_the_exercise_to_the_step(world: World) -> None:
    """The anchor the read admits is the one the create door writes."""
    async with world.driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (ex:Entity {uid: $uid})
                RETURN ex.scope AS scope, ex.path_step_uid AS anchor,
                       [(s)-[:HAS_EXERCISE]->(ex) | s.uid] AS steps,
                       [(u:User)-[:OWNS]->(ex) | u.uid] AS owners
                """,
                uid=world.anchored,
            )
        ).single()
    assert record is not None
    assert record["scope"] == ExerciseScope.PERSONAL.value
    assert record["anchor"] == PS_PUBLISHED
    assert record["steps"] == [PS_PUBLISHED]
    assert record["owners"] == [TEACHER]


async def test_the_step_listing_links_the_learner_to_the_detail_read(world: World) -> None:
    """The learner's step page lists the exercise and links it to ``/exercises/get``."""
    listing = await world.clients[LEARNER].get(f"/learning-loop/ps/{PS_PUBLISHED}/exercises")
    assert listing.status_code == 200
    assert f"/exercises/get?uid={world.anchored}" in listing.text


async def test_a_learner_reads_an_anchored_exercise_before_starting_the_step(
    world: World,
) -> None:
    response = await world.read(LEARNER, world.anchored)
    assert response.status_code == 200, response.text
    assert f"{MARK}-anchored" in response.text
    assert f"{MARK} anchored instructions" in response.text


async def test_a_learner_reads_an_anchored_exercise_after_starting_the_step(
    world: World,
) -> None:
    started = await world.clients[LEARNER].post(
        f"/explore/ps/{PS_PUBLISHED}/progress", data={"state": "learning", "review": "true"}
    )
    assert started.status_code == 200, started.text
    response = await world.read(LEARNER, world.anchored)
    assert response.status_code == 200, response.text
    assert f"{MARK} anchored instructions" in response.text


async def test_the_markdown_download_reads_the_same_audience(world: World) -> None:
    anchored = await world.clients[LEARNER].get(MD, params={"uid": world.anchored})
    unanchored = await world.clients[LEARNER].get(MD, params={"uid": world.unanchored})
    assert anchored.status_code == 200, anchored.text
    assert f"{MARK} anchored instructions" in anchored.text
    assert unanchored.status_code == 404
    assert f"{MARK} unanchored instructions" not in unanchored.text


async def test_an_unanchored_personal_exercise_stays_its_owners(world: World) -> None:
    refused = await world.read(LEARNER, world.unanchored)
    missing = await world.read(LEARNER, MISSING_EX)
    assert refused.status_code == missing.status_code == 404
    assert f"{MARK}-unanchored" not in refused.text
    assert _normalised(refused.text, world.unanchored) == _normalised(missing.text, MISSING_EX)


async def test_a_draft_step_admits_no_one(world: World) -> None:
    refused = await world.read(LEARNER, world.draft_anchored)
    assert refused.status_code == 404
    assert f"{MARK} draftanchored instructions" not in refused.text


async def test_the_anchor_admits_personal_scope_alone(world: World) -> None:
    """An ASSIGNED exercise hanging from the same step stays its group's."""
    refused = await world.read(LEARNER, ASSIGNED_EX)
    assert refused.status_code == 404
    assert f"{ASSIGNED_EX} instructions" not in refused.text


async def test_curriculum_stays_open_to_every_learner(world: World) -> None:
    response = await world.read(LEARNER, CURRICULUM_EX)
    assert response.status_code == 200, response.text
    assert f"{CURRICULUM_EX} instructions" in response.text


async def test_the_owner_still_reads_each_of_their_exercises(world: World) -> None:
    for uid in (world.anchored, world.unanchored, world.draft_anchored):
        response = await world.read(TEACHER, uid)
        assert response.status_code == 200, (uid, response.text)


async def test_exercise_search_agrees_with_the_detail_read(world: World) -> None:
    """One audience for search and the by-uid read: the learner finds the anchored
    exercise and none of the others."""
    exercises = world.skuel_app.state.services.exercises
    result = await exercises.search(MARK, user_uid=UserUID(LEARNER), limit=50)
    assert result.is_ok, result.expect_error()
    found = {e.uid for e in result.value}
    assert world.anchored in found
    assert not found & {world.unanchored, world.draft_anchored, ASSIGNED_EX}


async def test_a_search_with_no_user_is_floored_at_curriculum(world: World) -> None:
    """The anchor admits a signed-in learner: a null user finds curriculum alone."""
    exercises = world.skuel_app.state.services.exercises
    result = await exercises.search(MARK, user_uid=None, limit=50)
    assert result.is_ok, result.expect_error()
    found = {e.uid for e in result.value}
    assert CURRICULUM_EX in found
    assert world.anchored not in found
