"""Who may change what an exercise requires — ``POST /api/exercises/require-knowledge``
and ``/unrequire-knowledge``.

An exercise's ``REQUIRES_KNOWLEDGE`` edges are part of the exercise: its owner's
``/exercises/{uid}/view`` lists them as the knowledge it asks for. So only the
exercise's owner — the user who ``:OWNS`` it — or an ADMIN may add or remove one
(``ExerciseService.admit_requirement_change``). A CURRICULUM exercise has no owner,
so only an ADMIN may.

Every refusal is a 404 that reads the same as an exercise uid naming nothing, and
writes nothing — a refused unrequire leaves the owner's edge in place.

The exercises are made at the real create door; the Kus and the ownerless
CURRICULUM exercise are seeded, since neither has an HTTP create door.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.integration._activity_link_rig import create, edges_between, signed_in_client

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

MARK = "zzzreqknow"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
OWNER_MARK = f"{MARK}o"
STRANGER_MARK = f"{MARK}s"
ADMIN_MARK = f"{MARK}a"
OWNER = f"user_{OWNER_MARK}"  # a teacher who owns the exercise
STRANGER = f"user_{STRANGER_MARK}"  # another teacher, with an exercise of their own
ADMIN = f"user_{ADMIN_MARK}"
ROLES = {OWNER: "teacher", STRANGER: "teacher", ADMIN: "admin"}
KU_KEPT = f"ku.{OWNER_MARK}.kept"  # the owner's own requirement, present from the start
KU_ADDED = f"ku.{OWNER_MARK}.added"
CURRICULUM_EXERCISE = f"ex_{OWNER_MARK}_curriculum"
MISSING_EXERCISE = f"ex_{MARK}_missing"
REQUIRE = "/api/exercises/require-knowledge"
UNREQUIRE = "/api/exercises/unrequire-knowledge"


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


async def _seed(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        for uid in (KU_KEPT, KU_ADDED):
            await session.run(
                "CREATE (:Entity:Ku {uid: $uid, entity_type: 'ku', title: $uid})", uid=uid
            )
        await session.run(
            """
            CREATE (:Entity:Exercise {uid: $uid, entity_type: 'exercise', scope: 'curriculum',
                                      title: $uid, instructions: 'shared'})
            """,
            uid=CURRICULUM_EXERCISE,
        )


async def _delete_owned(driver: AsyncDriver, users: list[str]) -> None:
    """Exercises carry no mark in their generated uids — remove them by owner."""
    async with driver.session() as session:
        await session.run(
            "MATCH (u:User)-[:OWNS]->(n) WHERE u.uid IN $users DETACH DELETE n", users=users
        )


def _uidless(body: str, *uids: str) -> str:
    for uid in uids:
        body = body.replace(uid, "<uid>")
    return re.sub(r'"timestamp":"[^"]*"', '"timestamp":"<t>"', body)


class World:
    def __init__(
        self,
        driver: AsyncDriver,
        clients: dict[str, httpx.AsyncClient],
        exercise: str,
        stranger_exercise: str,
    ) -> None:
        self.driver = driver
        self.clients = clients
        self.exercise = exercise  # the owner's PERSONAL exercise, requiring KU_KEPT
        self.stranger_exercise = stranger_exercise

    async def post(self, caller: str, door: str, exercise: str, ku: str) -> httpx.Response:
        return await self.clients[caller].post(
            door, json={"exercise_uid": exercise, "curriculum_uid": ku}
        )

    async def requires(self, exercise: str, ku: str) -> bool:
        edges = await edges_between(self.driver, exercise, ku)
        return any(
            e.type == "REQUIRES_KNOWLEDGE" and e.source == exercise and e.target == ku
            for e in edges
        )

    async def listed_to_owner(self) -> set[str]:
        response = await self.clients[OWNER].get(
            "/api/exercises/required-knowledge", params={"uid": self.exercise}
        )
        assert response.status_code == 200, response.text
        return {row["uid"] for row in response.json()}


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, OWNER, OWNER_MARK) as owner,
        signed_in_client(skuel_app, STRANGER, STRANGER_MARK) as stranger,
        signed_in_client(skuel_app, ADMIN, ADMIN_MARK) as admin,
    ):
        for uid, role in ROLES.items():
            await _set_role(driver, uid, role)
        try:
            await _seed(driver)
            exercise = await create(
                owner, "exercises", f"{MARK}-essay", name=f"{MARK}-essay", instructions="essay"
            )
            stranger_exercise = await create(
                stranger, "exercises", f"{MARK}-quiz", name=f"{MARK}-quiz", instructions="quiz"
            )
            world = World(
                driver,
                {OWNER: owner, STRANGER: stranger, ADMIN: admin},
                exercise,
                stranger_exercise,
            )
            kept = await world.post(OWNER, REQUIRE, exercise, KU_KEPT)
            assert kept.status_code == 200, kept.text
            yield world
        finally:
            await _delete_owned(driver, list(ROLES))


@pytest.fixture
async def clean(world: World) -> AsyncIterator[World]:
    """Each test starts from: the owner's exercise requires KU_KEPT and nothing else."""
    yield world
    async with world.driver.session() as session:
        await session.run(
            """
            MATCH (ex:Entity)-[r:REQUIRES_KNOWLEDGE]->(:Entity {uid: $added})
            WHERE ex.uid IN $exercises
            DELETE r
            """,
            added=KU_ADDED,
            exercises=[world.exercise, world.stranger_exercise, CURRICULUM_EXERCISE],
        )
        await session.run(
            """
            MATCH (ex:Entity {uid: $exercise}), (k:Entity {uid: $kept})
            MERGE (ex)-[:REQUIRES_KNOWLEDGE]->(k)
            """,
            exercise=world.exercise,
            kept=KU_KEPT,
        )


async def test_the_owner_changes_what_their_exercise_requires(clean: World) -> None:
    added = await clean.post(OWNER, REQUIRE, clean.exercise, KU_ADDED)
    assert added.status_code == 200, added.text
    assert await clean.listed_to_owner() == {KU_KEPT, KU_ADDED}

    removed = await clean.post(OWNER, UNREQUIRE, clean.exercise, KU_ADDED)
    assert removed.status_code == 200, removed.text
    assert await clean.listed_to_owner() == {KU_KEPT}


async def test_another_teacher_cannot_add_to_the_exercise(clean: World) -> None:
    refused = await clean.post(STRANGER, REQUIRE, clean.exercise, KU_ADDED)
    missing = await clean.post(STRANGER, REQUIRE, MISSING_EXERCISE, KU_ADDED)

    assert refused.status_code == 404, refused.text
    assert not await clean.requires(clean.exercise, KU_ADDED)
    assert await clean.listed_to_owner() == {KU_KEPT}
    assert _uidless(refused.text, clean.exercise) == _uidless(missing.text, MISSING_EXERCISE)

    own = await clean.post(STRANGER, REQUIRE, clean.stranger_exercise, KU_ADDED)
    assert own.status_code == 200, own.text
    assert await clean.requires(clean.stranger_exercise, KU_ADDED)


async def test_another_teacher_cannot_remove_the_owners_requirement(clean: World) -> None:
    refused = await clean.post(STRANGER, UNREQUIRE, clean.exercise, KU_KEPT)
    missing = await clean.post(STRANGER, UNREQUIRE, MISSING_EXERCISE, KU_KEPT)

    assert refused.status_code == 404, refused.text
    assert await clean.requires(clean.exercise, KU_KEPT)
    assert await clean.listed_to_owner() == {KU_KEPT}
    assert _uidless(refused.text, clean.exercise) == _uidless(missing.text, MISSING_EXERCISE)


async def test_an_admin_changes_any_exercises_requirements(clean: World) -> None:
    added = await clean.post(ADMIN, REQUIRE, clean.exercise, KU_ADDED)
    assert added.status_code == 200, added.text
    assert await clean.requires(clean.exercise, KU_ADDED)

    removed = await clean.post(ADMIN, UNREQUIRE, clean.exercise, KU_ADDED)
    assert removed.status_code == 200, removed.text
    assert not await clean.requires(clean.exercise, KU_ADDED)


async def test_an_ownerless_curriculum_exercise_is_changed_by_an_admin_only(
    clean: World,
) -> None:
    refused = await clean.post(OWNER, REQUIRE, CURRICULUM_EXERCISE, KU_ADDED)
    missing = await clean.post(OWNER, REQUIRE, MISSING_EXERCISE, KU_ADDED)

    assert refused.status_code == 404, refused.text
    assert not await clean.requires(CURRICULUM_EXERCISE, KU_ADDED)
    assert _uidless(refused.text, CURRICULUM_EXERCISE) == _uidless(missing.text, MISSING_EXERCISE)

    added = await clean.post(ADMIN, REQUIRE, CURRICULUM_EXERCISE, KU_ADDED)
    assert added.status_code == 200, added.text
    assert await clean.requires(CURRICULUM_EXERCISE, KU_ADDED)

    refused_removal = await clean.post(OWNER, UNREQUIRE, CURRICULUM_EXERCISE, KU_ADDED)
    assert refused_removal.status_code == 404, refused_removal.text
    assert await clean.requires(CURRICULUM_EXERCISE, KU_ADDED)


async def test_an_admin_is_refused_an_exercise_that_does_not_exist(clean: World) -> None:
    response = await clean.post(ADMIN, REQUIRE, MISSING_EXERCISE, KU_ADDED)

    assert response.status_code == 404, response.text
