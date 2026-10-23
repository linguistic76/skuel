"""How a chunk and a :Content node are identified, on a real Neo4j.

- A :Content node has no uid. It is one per entity and is reached only through the
  entity's ``HAS_CONTENT`` edge, so no node shares its entity's uid.
- A chunk's uid is ``chunk_uid(store, parent, index)``: in the uid grammar, and the
  same on every re-chunk of the same body, so a queued ``ChunkEmbeddingRequested``
  still names the chunks a later re-ingest re-creates.
- Every read of a body reaches its Content through the entity: the batch re-chunk
  (which stores under the entity's uid) and the vector search's parent scope; the
  embedding worker stores by chunk uid, which a re-chunk re-creates.
- The app creates a uniqueness constraint on each chunk label; the store's
  delete-then-recreate of the same uids passes it, a second node on a uid does not.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncDriver, Record
from neo4j.exceptions import ConstraintError

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.batch_chunking_backend import BatchChunkingBackend
from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager
from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
from core.constants import EmbeddingGeometry
from core.events import ChunkEmbeddingRequested
from core.models.enums.neo_labels import NeoLabel
from core.models.ps_content.content import CurriculumContent
from core.models.ps_content.content_chunks import ChunkStore, chunk_uid
from core.services.background.embedding_worker import EmbeddingBackgroundWorker
from core.services.chunks.batch_chunking_service import BatchChunkingService
from core.services.entity_chunking_service import EntityChunkingService
from core.utils.result_simplified import Result
from core.utils.uid_grammar import UidVerdict, classify

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

STEP = "ps.zzzchunkid.first"
OTHER_STEP = "ps.zzzchunkid.second"
_UIDS = [STEP, OTHER_STEP]

_BODY = """# Breath

Breath awareness begins with noticing the breath as it is.

## Practice

Sit, notice three breaths, and name each one without changing it.

## Why

Attention that rests on the breath has somewhere to return to.
"""
_OTHER_BODY = """# Posture

An upright, relaxed posture supports a steady attention through the session.
"""
_EMBEDDING = [1.0] + [0.0] * (EmbeddingGeometry.DIMENSION - 1)


class _DriverConnection:
    """The ``execute_query(query, params) -> list[Record]`` shape the adapters take."""

    def __init__(self, driver: AsyncDriver) -> None:
        self.driver = driver

    # boundary: cypher-params — Cypher parameters are genuinely heterogeneous.
    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Record]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return [record async for record in result]


class _FakeEmbeddings:
    model = "test-embedder"

    async def create_batch_embeddings(
        self, texts: list[str], metadata_list: list[dict[str, Any]] | None = None
    ) -> Result[list[list[float]]]:
        return Result.ok([_EMBEDDING for _ in texts])


async def _rows(
    driver: AsyncDriver, query: str, **params: Any
) -> list[Record]:  # boundary: cypher-params
    async with driver.session() as session:
        result = await session.run(query, params)
        return [record async for record in result]


async def _clean(driver: AsyncDriver) -> None:
    await _rows(
        driver,
        """
        MATCH (e:Entity) WHERE e.uid IN $uids
        OPTIONAL MATCH (e)-[:HAS_CONTENT]->(c:Content)
        OPTIONAL MATCH (c)-[:HAS_CHUNK]->(k:ContentChunk)
        DETACH DELETE k, c, e
        """,
        uids=_UIDS,
    )


async def _store(adapter: Neo4jContentAdapter, uid: str, body: str) -> CurriculumContent:
    content = CurriculumContent.create(unit_uid=uid, body=body)
    assert await adapter.store_content_with_chunks(uid, content), f"store failed for {uid}"
    return content


async def _chunk_uids(driver: AsyncDriver, uid: str) -> list[str]:
    rows = await _rows(
        driver,
        """
        MATCH (:Entity {uid: $uid})-[:HAS_CONTENT]->(:Content)-[r:HAS_CHUNK]->(k:ContentChunk)
        RETURN k.uid AS uid ORDER BY r.sequence
        """,
        uid=uid,
    )
    return [str(row["uid"]) for row in rows]


@pytest_asyncio.fixture(loop_scope="session")
async def steps(neo4j_driver: AsyncDriver):
    """Two published-shape PathSteps with no body yet."""
    await _clean(neo4j_driver)
    await _rows(
        neo4j_driver,
        """
        UNWIND $uids AS uid
        CREATE (:Entity:PathStep {uid: uid, title: uid, entity_type: 'path_step'})
        """,
        uids=_UIDS,
    )
    yield Neo4jContentAdapter(_DriverConnection(neo4j_driver))
    await _clean(neo4j_driver)


class TestContentAndChunkUids:
    async def test_content_has_no_uid_and_one_node_per_entity(
        self, neo4j_driver: AsyncDriver, steps: Neo4jContentAdapter
    ) -> None:
        await _store(steps, STEP, _BODY)
        await _store(steps, STEP, _BODY + "\nOne more line.\n")

        rows = await _rows(
            neo4j_driver,
            "MATCH (:Entity {uid: $uid})-[:HAS_CONTENT]->(c:Content) RETURN c.uid AS uid",
            uid=STEP,
        )
        assert [row["uid"] for row in rows] == [None]
        shared = await _rows(neo4j_driver, "MATCH (n {uid: $uid}) RETURN count(n) AS n", uid=STEP)
        assert shared[0]["n"] == 1

    async def test_chunk_uids_are_minted_in_the_grammar_and_re_minted_by_a_re_chunk(
        self, neo4j_driver: AsyncDriver, steps: Neo4jContentAdapter
    ) -> None:
        content = await _store(steps, STEP, _BODY)
        first = await _chunk_uids(neo4j_driver, STEP)
        assert first == [chunk_uid(ChunkStore.CONTENT, STEP, i) for i in range(len(content.chunks))]
        assert all(classify(uid) is UidVerdict.FITS for uid in first)

        await _store(steps, STEP, _BODY)
        assert await _chunk_uids(neo4j_driver, STEP) == first


class TestReadersStartAtTheEntity:
    async def test_the_worker_stores_by_uid_after_a_re_ingest(
        self, neo4j_driver: AsyncDriver, steps: Neo4jContentAdapter
    ) -> None:
        """An event published before a re-chunk still names the re-created chunks."""
        bus = InMemoryEventBus()
        worker = EmbeddingBackgroundWorker(
            event_bus=bus, embeddings_service=_FakeEmbeddings(), content_adapter=steps
        )
        bus.subscribe(ChunkEmbeddingRequested, worker._queue_chunk_request)
        content = await _store(steps, STEP, _BODY)
        await bus.publish_async(
            ChunkEmbeddingRequested(
                parent_uid=STEP,
                chunk_uids=tuple(c.chunk_id for c in content.chunks),
                chunk_texts=tuple(c.context_window for c in content.chunks),
                requested_at=datetime.now(),
            )
        )
        for _ in range(20):
            if worker._pending_chunk_requests:
                break
            await asyncio.sleep(0.05)
        assert worker._pending_chunk_requests, "the worker never queued the event"

        await _store(steps, STEP, _BODY)  # the re-ingest lands while the event waits

        batch = list(worker._pending_chunk_requests)
        worker._pending_chunk_requests.clear()
        await worker._process_chunk_batch(batch)

        rows = await _rows(
            neo4j_driver,
            """
            MATCH (:Entity {uid: $uid})-[:HAS_CONTENT]->(:Content)-[:HAS_CHUNK]->(k:ContentChunk)
            RETURN count(k) AS total, count(k.embedding) AS embedded
            """,
            uid=STEP,
        )
        assert rows[0]["total"] == len(content.chunks)
        assert rows[0]["embedded"] == len(content.chunks)

    async def test_the_batch_re_chunk_stores_under_the_entity_uid(
        self, neo4j_driver: AsyncDriver, steps: Neo4jContentAdapter
    ) -> None:
        content = await _store(steps, STEP, _BODY)
        await _store(steps, OTHER_STEP, _OTHER_BODY)
        await _rows(
            neo4j_driver,
            """
            MATCH (:Entity {uid: $uid})-[:HAS_CONTENT]->(:Content)-[:HAS_CHUNK]->(k:ContentChunk)
            SET k.chunking_version = 'v0_stale'
            """,
            uid=STEP,
        )
        service = BatchChunkingService(
            backend=BatchChunkingBackend(neo4j_driver),
            chunking_service=EntityChunkingService(),
            content_adapter=steps,
            event_bus=None,
        )

        regenerated = await service.regenerate_chunks(parent_uids=[STEP], force=False)

        assert regenerated.is_ok, regenerated
        assert regenerated.value.total_candidates == 1
        assert regenerated.value.succeeded == 1
        assert await _chunk_uids(neo4j_driver, STEP) == [
            chunk_uid(ChunkStore.CONTENT, STEP, i) for i in range(len(content.chunks))
        ]
        stale = await _rows(
            neo4j_driver,
            """
            MATCH (:Entity {uid: $uid})-[:HAS_CONTENT]->(:Content)-[:HAS_CHUNK]->(k:ContentChunk)
            WHERE k.chunking_version = 'v0_stale'
            RETURN count(k) AS n
            """,
            uid=STEP,
        )
        assert stale[0]["n"] == 0
        contents = await _rows(
            neo4j_driver,
            "MATCH (:Entity {uid: $uid})-[:HAS_CONTENT]->(c:Content) RETURN count(c) AS n",
            uid=STEP,
        )
        assert contents[0]["n"] == 1

    async def test_the_vector_parent_filter_still_scopes(
        self, neo4j_driver: AsyncDriver, steps: Neo4jContentAdapter
    ) -> None:
        await _store(steps, STEP, _BODY)
        await _store(steps, OTHER_STEP, _OTHER_BODY)
        index = await Neo4jSchemaManager(neo4j_driver).create_vector_index(NeoLabel.CONTENT_CHUNK)
        assert index.is_ok, index
        await _rows(
            neo4j_driver,
            """
            MATCH (e:Entity)-[:HAS_CONTENT]->(:Content)-[:HAS_CHUNK]->(k:ContentChunk)
            WHERE e.uid IN $uids
            CALL db.create.setNodeVectorProperty(k, 'embedding', $embedding)
            """,
            uids=_UIDS,
            embedding=_EMBEDDING,
        )
        await _rows(neo4j_driver, "CALL db.awaitIndexes(120)")
        backend = VectorSearchBackend(executor=Neo4jQueryExecutor(neo4j_driver))

        async def parents(parent_uid: str | None) -> set[str]:
            found = await backend.semantic_search_chunks(
                query_embedding=_EMBEDDING, limit=50, threshold=0.5, parent_uid=parent_uid
            )
            assert found.is_ok, found
            return {hit["parent_uid"] for hit in found.value if hit["parent_uid"] in _UIDS}

        assert await parents(None) == set(_UIDS)  # control: both parents are retrievable
        assert await parents(STEP) == {STEP}
        assert await parents(OTHER_STEP) == {OTHER_STEP}


class TestChunkUidConstraints:
    async def test_the_app_constrains_chunk_uids_and_a_re_chunk_passes(self, skuel_app) -> None:
        driver: AsyncDriver = skuel_app.state.services.neo4j_driver
        constraints = await _rows(
            driver,
            "SHOW CONSTRAINTS YIELD labelsOrTypes, properties, type "
            "WHERE type = 'NODE_PROPERTY_UNIQUENESS' RETURN labelsOrTypes, properties",
        )
        constrained = {
            (tuple(row["labelsOrTypes"]), tuple(row["properties"])) for row in constraints
        }
        assert (("ContentChunk",), ("uid",)) in constrained
        assert (("ReferenceChunk",), ("uid",)) in constrained

        adapter = Neo4jContentAdapter(_DriverConnection(driver))
        await _rows(
            driver, "CREATE (:Entity:PathStep {uid: $uid, entity_type: 'path_step'})", uid=STEP
        )
        try:
            content = await _store(adapter, STEP, _BODY)
            await _store(adapter, STEP, _BODY)  # delete-then-recreate of the same uids
            assert await _chunk_uids(driver, STEP) == [c.chunk_id for c in content.chunks]
            with pytest.raises(ConstraintError):
                await _rows(
                    driver, "CREATE (:ContentChunk {uid: $uid})", uid=content.chunks[0].chunk_id
                )
        finally:
            await _clean(driver)
