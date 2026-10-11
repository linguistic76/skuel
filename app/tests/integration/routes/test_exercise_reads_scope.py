"""The two teacher reads of an exercise's knowledge links show a teacher only what they
may read — ``GET /api/exercises/required-knowledge`` and ``GET /api/exercises/for-curriculum``.

Readable exercises are defined in one place, the SCOPE_AWARE audience
(``build_search_visibility_clause``): CURRICULUM for everyone; the caller's own; what
is shared with them or their groups; a PERSONAL exercise anchored to a published
PathStep. Both reads compose it — the by-UID read as ``get_exercise_for_user`` does,
the listing as a search does — so another teacher's unanchored PERSONAL exercise is
a 404 identical to a uid naming nothing on the one, and absent from the other. An
ADMIN has no arm of their own in that audience: the reads answer an admin exactly as
they answer any other teacher.

The exercises are made at the real create door and their requirements through the
real require door; the ownerless CURRICULUM exercise and the Ku are seeded, since
neither has an HTTP create door.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.integration._activity_link_rig import create, signed_in_client

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

MARK = "zzzexreads"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
OWNER_MARK = f"{MARK}o"
STRANGER_MARK = f"{MARK}s"
ADMIN_MARK = f"{MARK}a"
OWNER = f"user_{OWNER_MARK}"  # a teacher with a PERSONAL exercise requiring the Ku
STRANGER = f"user_{STRANGER_MARK}"  # another teacher, with one of their own
ADMIN = f"user_{ADMIN_MARK}"
ROLES = {OWNER: "teacher", STRANGER: "teacher", ADMIN: "admin"}
KU = f"ku.{OWNER_MARK}.required"
CURRICULUM_EXERCISE = f"ex_{OWNER_MARK}_curriculum"
MISSING_EXERCISE = f"ex_{MARK}_missing"
REQUIRED_KNOWLEDGE = "/api/exercises/required-knowledge"
FOR_CURRICULUM = "/api/exercises/for-curriculum"
REQUIRE = "/api/exercises/require-knowledge"


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
        await session.run("CREATE (:Entity:Ku {uid: $uid, entity_type: 'ku', title: $uid})", uid=KU)
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
        clients: dict[str, httpx.AsyncClient],
        exercise: str,
        stranger_exercise: str,
    ) -> None:
        self.clients = clients
        self.exercise = exercise  # the owner's PERSONAL exercise, requiring KU
        self.stranger_exercise = stranger_exercise  # the stranger's, also requiring KU

    async def required(self, caller: str, exercise: str) -> httpx.Response:
        return await self.clients[caller].get(REQUIRED_KNOWLEDGE, params={"uid": exercise})

    async def listed_for_ku(self, caller: str) -> set[str]:
        response = await self.clients[caller].get(FOR_CURRICULUM, params={"curriculum_uid": KU})
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
            # Each requirement through the real require door, by a caller it admits:
            # the owner on their own exercise, the admin on the ownerless one.
            for client, target in (
                (owner, exercise),
                (stranger, stranger_exercise),
                (admin, CURRICULUM_EXERCISE),
            ):
                required = await client.post(
                    REQUIRE, json={"exercise_uid": target, "curriculum_uid": KU}
                )
                assert required.status_code == 200, required.text
            yield World(
                {OWNER: owner, STRANGER: stranger, ADMIN: admin}, exercise, stranger_exercise
            )
        finally:
            await _delete_owned(driver, list(ROLES))


async def test_the_owner_lists_what_their_exercise_requires(world: World) -> None:
    response = await world.required(OWNER, world.exercise)

    assert response.status_code == 200, response.text
    assert [row["uid"] for row in response.json()] == [KU]


@pytest.mark.parametrize("caller", [STRANGER, ADMIN])
async def test_another_users_exercise_answers_as_a_missing_one(world: World, caller: str) -> None:
    """Another teacher — or an admin, who has no arm of their own in the audience —
    cannot tell the owner's exercise from a uid naming nothing."""
    refused = await world.required(caller, world.exercise)
    missing = await world.required(caller, MISSING_EXERCISE)

    assert refused.status_code == 404, refused.text
    assert KU not in refused.text
    assert _uidless(refused.text, world.exercise) == _uidless(missing.text, MISSING_EXERCISE)


async def test_the_stranger_still_reads_their_own(world: World) -> None:
    """The control for the refusal above: the same door, the caller's own exercise."""
    response = await world.required(STRANGER, world.stranger_exercise)

    assert response.status_code == 200, response.text
    assert [row["uid"] for row in response.json()] == [KU]


async def test_a_curriculum_exercises_requirements_are_everyones(world: World) -> None:
    response = await world.required(STRANGER, CURRICULUM_EXERCISE)

    assert response.status_code == 200, response.text
    assert [row["uid"] for row in response.json()] == [KU]


async def test_the_ku_lookup_lists_each_caller_only_what_they_may_open(world: World) -> None:
    """Three exercises require the Ku; each caller sees the shared one plus their own."""
    assert await world.listed_for_ku(OWNER) == {world.exercise, CURRICULUM_EXERCISE}
    assert await world.listed_for_ku(STRANGER) == {world.stranger_exercise, CURRICULUM_EXERCISE}
    assert await world.listed_for_ku(ADMIN) == {CURRICULUM_EXERCISE}
