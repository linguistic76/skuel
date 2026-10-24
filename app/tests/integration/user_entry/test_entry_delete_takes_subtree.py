"""Every door that deletes a UserEntry takes its chunk subtree with it.

A knowledge entry's body is chunked into ``(entry)-[:HAS_CONTENT]->(:Content)
-[:HAS_CHUNK]->(:ContentChunk)`` by the real content adapter (the chunk step's
``clear_inline_body=False`` call). Deleting the entry — by its owner, by the
teacher it asks for feedback, or by an admin's erasure of the owner — must leave
neither the Content nor a chunk behind: an orphaned chunk still answers vector
searches and re-chunk scans, with nothing left to say whose it was.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from adapters.persistence.neo4j.user_backend import UserBackend
from core.models.ps_content.content import CurriculumContent
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from tests.helpers.seed_uids import seed_user_uid

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from neo4j import AsyncDriver, Record

    from core.services.user_entry.user_entry_service import UserEntryService

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

OWNER = seed_user_uid("zzzdelsub_owner")
TEACHER = seed_user_uid("zzzdelsub_teacher")
_BODY = """# A note

Breath awareness came easier today than it did last week.

## What changed

Naming each breath, without changing it, gave attention somewhere to rest.
"""


class _DriverConnection:
    """The ``execute_query(query, params) -> list[Record]`` shape the adapter takes."""

    def __init__(self, driver: AsyncDriver) -> None:
        self.driver = driver

    # boundary: cypher-params — Cypher parameters are genuinely heterogeneous.
    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Record]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return [record async for record in result]


async def _count(driver: AsyncDriver, query: str, **params: Any) -> int:  # boundary: cypher-params
    async with driver.session() as session:
        record = await (await session.run(query, params)).single()
    assert record is not None
    return int(record[0])


async def _entry_with_subtree(
    driver: AsyncDriver, service: UserEntryService, owner: str
) -> tuple[str, list[str]]:
    """Create an entry through the service and chunk its body with the real adapter."""
    created = await service.create_entry(
        request=UserEntryCreateRequest(title="Breath note", content=_BODY), user_uid=owner
    )
    assert created.is_ok, created
    entry, _share = created.value
    content = CurriculumContent.create(unit_uid=entry.uid, body=_BODY)
    stored = await Neo4jContentAdapter(_DriverConnection(driver)).store_content_with_chunks(
        entry.uid, content, clear_inline_body=False
    )
    assert stored
    chunk_uids = [chunk.chunk_id for chunk in content.chunks]
    # Control: the subtree is really there, so "nothing left" below means deleted.
    assert await _subtree_size(driver, entry.uid, chunk_uids) == 1 + len(chunk_uids)
    return entry.uid, chunk_uids


async def _subtree_size(driver: AsyncDriver, entry_uid: str, chunk_uids: list[str]) -> int:
    """The entry's Content and chunks — found by edge while attached, by uid once orphaned."""
    contents = await _count(
        driver,
        """
        MATCH (c:Content)-[:HAS_CHUNK]->(k:ContentChunk)
        WHERE k.uid IN $chunk_uids
        RETURN count(DISTINCT c)
        """,
        chunk_uids=chunk_uids,
    )
    chunks = await _count(
        driver,
        "MATCH (k:ContentChunk) WHERE k.uid IN $chunk_uids RETURN count(k)",
        chunk_uids=chunk_uids,
    )
    attached = await _count(
        driver,
        "MATCH (:Entity {uid: $uid})-[:HAS_CONTENT]->(c:Content) RETURN count(c)",
        uid=entry_uid,
    )
    return max(contents, attached) + chunks


@pytest.fixture
async def people(seed_user: Callable[..., Awaitable[str]], neo4j_driver: AsyncDriver):
    await seed_user(OWNER, name="Owner")
    await seed_user(TEACHER, name="Teacher")
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (u:User) WHERE u.uid IN $uids
            OPTIONAL MATCH (u)-[:OWNS]->(e:Entity)
            OPTIONAL MATCH (e)-[:HAS_CONTENT]->(c:Content)
            OPTIONAL MATCH (c)-[:HAS_CHUNK]->(k:ContentChunk)
            DETACH DELETE k, c, e, u
            """,
            uids=[OWNER, TEACHER],
        )


@pytest.mark.usefixtures("people")
class TestEveryDeleteDoorTakesTheSubtree:
    async def test_the_owner_deletes_the_entry(
        self, neo4j_driver: AsyncDriver, user_entry_service: UserEntryService
    ) -> None:
        uid, chunk_uids = await _entry_with_subtree(neo4j_driver, user_entry_service, OWNER)

        deleted = await user_entry_service.delete_entry(uid, UserUID(OWNER))

        assert deleted.is_ok and deleted.value, deleted
        assert await _subtree_size(neo4j_driver, uid, chunk_uids) == 0

    async def test_the_teacher_the_entry_asks_deletes_it(
        self, neo4j_driver: AsyncDriver, user_entry_service: UserEntryService
    ) -> None:
        uid, chunk_uids = await _entry_with_subtree(neo4j_driver, user_entry_service, OWNER)
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (e:Entity:UserEntry {uid: $uid}), (t:User {uid: $teacher})
                MERGE (e)-[:SUBMITTED_TO_TEACHER {submitted_at: datetime()}]->(t)
                """,
                uid=uid,
                teacher=TEACHER,
            )

        deleted = await user_entry_service.delete_entry_as_teacher(uid, UserUID(TEACHER))

        assert deleted.is_ok and deleted.value, deleted
        assert await _subtree_size(neo4j_driver, uid, chunk_uids) == 0

    async def test_an_admin_erases_the_owner(
        self, neo4j_driver: AsyncDriver, user_entry_service: UserEntryService
    ) -> None:
        uid, chunk_uids = await _entry_with_subtree(neo4j_driver, user_entry_service, OWNER)

        erased = await UserBackend(neo4j_driver).hard_delete_user(UserUID(OWNER))

        assert erased.is_ok and erased.value >= 2, erased  # the user and the entry
        assert (
            await _count(neo4j_driver, "MATCH (e:Entity {uid: $uid}) RETURN count(e)", uid=uid) == 0
        )
        assert await _subtree_size(neo4j_driver, uid, chunk_uids) == 0
