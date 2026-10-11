"""An exercise's owner may turn in an entry against it — ``POST /api/user-entries``
with ``fulfills_exercise_uid``.

The submit door admits a ``fulfills_exercise_uid`` only for a user with a tie to the
exercise (``SharingBackend.query_user_can_use_exercise``): its owner, a member of a
group it is shared with, a learner in progress on the PathStep it hangs from, or the
student a revision names. An exercise's owner is the user who ``:OWNS`` it — Exercise
carries ``owner_uid``, never ``user_uid`` (ADR-086) — so the owner's tie is read from
that edge.

A user with no tie is refused, and the refusal reads the same as an exercise uid
naming nothing; neither writes an entry or a ``FULFILLS_EXERCISE`` edge.

The exercises are made at the real create door.
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

MARK = "zzzexowner"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
OWNER_MARK = f"{MARK}o"
STRANGER_MARK = f"{MARK}s"
OWNER = f"user_{OWNER_MARK}"  # a teacher who owns the exercise
STRANGER = f"user_{STRANGER_MARK}"  # another user, with an exercise of their own
MISSING_EXERCISE = f"ex_{MARK}_missing"
SUBMIT = "/api/user-entries"


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


async def _delete_owned(driver: AsyncDriver, users: list[str]) -> None:
    """Exercises and entries carry no mark in their generated uids — remove them by owner."""
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
        self.exercise = exercise  # the owner's PERSONAL exercise
        self.stranger_exercise = stranger_exercise  # the stranger's own PERSONAL exercise

    async def submit(self, caller: str, exercise: str, title: str) -> httpx.Response:
        return await self.clients[caller].post(
            SUBMIT,
            json={
                "title": title,
                "content": f"{title} content",
                "fulfills_exercise_uid": exercise,
                "pipeline": "extract_activities",
            },
        )

    async def fulfillers(self, exercise: str) -> set[tuple[str, str]]:
        """``(entry owner, entry title)`` for every entry that ``FULFILLS_EXERCISE`` it."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (u:User)-[:OWNS]->(e:Entity)-[:FULFILLS_EXERCISE]->(:Entity {uid: $uid})
                RETURN u.uid AS owner, e.title AS title
                """,
                uid=exercise,
            )
            return {(row["owner"], row["title"]) async for row in result}

    async def entries_titled(self, title: str) -> int:
        async with self.driver.session() as session:
            record = await (
                await session.run(
                    "MATCH (e:Entity {entity_type: 'user_entry', title: $title}) "
                    "RETURN count(e) AS n",
                    title=title,
                )
            ).single()
        assert record is not None
        return int(record["n"])


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, OWNER, OWNER_MARK) as owner,
        signed_in_client(skuel_app, STRANGER, STRANGER_MARK) as stranger,
    ):
        await _set_role(driver, OWNER, "teacher")
        await _set_role(driver, STRANGER, "teacher")
        try:
            exercise = await create(
                owner, "exercises", f"{MARK}-essay", name=f"{MARK}-essay", instructions="essay"
            )
            stranger_exercise = await create(
                stranger, "exercises", f"{MARK}-quiz", name=f"{MARK}-quiz", instructions="quiz"
            )
            yield World(driver, {OWNER: owner, STRANGER: stranger}, exercise, stranger_exercise)
        finally:
            await _delete_owned(driver, [OWNER, STRANGER])


async def test_the_create_door_records_the_owner_on_the_owns_edge(world: World) -> None:
    """The tie the submit door reads is the one the create door writes."""
    async with world.driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (ex:Entity {uid: $uid})
                RETURN [(u:User)-[:OWNS]->(ex) | u.uid] AS owners,
                       ex.owner_uid AS owner_uid, ex.user_uid AS user_uid
                """,
                uid=world.exercise,
            )
        ).single()
    assert record is not None
    assert record["owners"] == [OWNER]
    assert record["owner_uid"] == OWNER
    assert record["user_uid"] is None  # Exercise is an owner_uid domain (ADR-086)


async def test_the_owner_turns_in_an_entry_against_their_own_exercise(world: World) -> None:
    title = f"{MARK}-owner-turn-in"
    response = await world.submit(OWNER, world.exercise, title)

    assert response.status_code == 201, response.text
    assert (OWNER, title) in await world.fulfillers(world.exercise)


async def test_each_owner_is_admitted_to_their_own_exercise(world: World) -> None:
    """Positive control on the second exercise: the tie is per owner, not per role."""
    title = f"{MARK}-stranger-own-turn-in"
    response = await world.submit(STRANGER, world.stranger_exercise, title)

    assert response.status_code == 201, response.text
    assert (STRANGER, title) in await world.fulfillers(world.stranger_exercise)


async def test_a_user_with_no_tie_is_refused_and_nothing_is_written(world: World) -> None:
    title = f"{MARK}-stranger-intrusion"
    response = await world.submit(STRANGER, world.exercise, title)

    assert response.status_code == 403, response.text
    assert all(owner != STRANGER for owner, _ in await world.fulfillers(world.exercise))
    assert await world.entries_titled(title) == 0


async def test_a_foreign_exercise_reads_the_same_as_a_missing_one(world: World) -> None:
    foreign = await world.submit(STRANGER, world.exercise, f"{MARK}-oracle")
    missing = await world.submit(STRANGER, MISSING_EXERCISE, f"{MARK}-oracle")

    assert foreign.status_code == missing.status_code == 403
    assert _uidless(foreign.text, world.exercise) == _uidless(missing.text, MISSING_EXERCISE)
    assert await world.entries_titled(f"{MARK}-oracle") == 0
