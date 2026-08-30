"""Chunk (RAG) retrieval honours the audience on a real Neo4j (ADR-085 chunk twin).

The `:ContentChunk` index mixes two audiences: shared curriculum bodies (Ku /
PathStep) and user-owned knowledge notes (non-private UserEntries, canon P3).
Until 2026-08-30 ``SearchRouter.retrieve_scoped_chunks`` discarded its
``user_uid``, and the backend applied no audience clause at all — Askesis
grounding for any user could draw on any other user's notes. The measured
corpus that day held 303 such chunks from two users.

Nothing is mocked between the ends: the REAL content adapter writes the chunks
and the REAL vector-search backend reads them back through the real vector
index. The control query runs first — a scoped assertion means nothing unless
the whole fixture is provably retrievable without the audience clause.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncDriver, Record

from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager
from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
from core.constants import EmbeddingGeometry
from core.models.enums.curriculum_enums import PublicationState
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.ps_content.content import CurriculumContent
from core.models.ps_content.content_chunks import ContentChunk, ContentChunkType

# A scalar property every seeded parent carries, used as a facet so the
# assertions see THIS fixture only even if another test's chunks coexist.
_FIXTURE_KEY = "fixture"
_FIXTURE_VALUE = "chunk_visibility"

_ALICE = "user_alice"
_BOB = "user_bob"

_PUBLISHED_PS = "ps.test.visibility.published"
_DRAFT_PS = "ps.test.visibility.draft"
_ALICE_NOTE = "ue.test.visibility.alice"
_ALICE_PRIVATE_NOTE = "ue.test.visibility.alice-private"
_BOB_NOTE = "ue.test.visibility.bob"

# uid → node properties. Writer shapes: ingestion writes no publication_state
# for finished content (NULL-tolerant gate), a draft PathStep carries the
# PublicationState value, and a UserEntry carries its owner's ``user_uid``
# (the ``:OWNS`` invariant's property half) plus ``private`` when flagged.
_PARENTS: dict[str, dict[str, Any]] = {
    _PUBLISHED_PS: {"entity_type": EntityType.PATH_STEP.value},
    _DRAFT_PS: {
        "entity_type": EntityType.PATH_STEP.value,
        "publication_state": PublicationState.DRAFT.value,
    },
    _ALICE_NOTE: {"entity_type": EntityType.USER_ENTRY.value, "user_uid": _ALICE},
    _ALICE_PRIVATE_NOTE: {
        "entity_type": EntityType.USER_ENTRY.value,
        "user_uid": _ALICE,
        "private": True,
    },
    _BOB_NOTE: {"entity_type": EntityType.USER_ENTRY.value, "user_uid": _BOB},
}

# One unit vector for every chunk: cosine similarity is 1.0 across the board,
# so ranking never decides what survives — only the audience clause does.
_EMBEDDING = [1.0] + [0.0] * (EmbeddingGeometry.DIMENSION - 1)

_DELETE_FIXTURE = """
MATCH (e:Entity {fixture: $fixture})
OPTIONAL MATCH (e)-[:HAS_CONTENT]->(c:Content)
OPTIONAL MATCH (c)-[:HAS_CHUNK]->(chunk:ContentChunk)
DETACH DELETE chunk, c, e
"""


class _DriverConnection:
    """Adapts the driver fixture to the Neo4jConnection shape the adapter wants."""

    def __init__(self, driver: AsyncDriver) -> None:
        self.driver = driver

    # boundary: cypher-params — mirrors the real execute_query signature this
    # double substitutes for; Cypher params are genuinely heterogeneous.
    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Record]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return [record async for record in result]


@pytest_asyncio.fixture
async def seeded_audiences(neo4j_driver):
    """Seed one chunk under each of the five parents via the REAL content adapter."""
    async with neo4j_driver.session() as session:
        await session.run(_DELETE_FIXTURE, {"fixture": _FIXTURE_VALUE})
        for uid, props in _PARENTS.items():
            await session.run(
                "CREATE (e:Entity) SET e = $props",
                {"props": {"uid": uid, "title": uid, _FIXTURE_KEY: _FIXTURE_VALUE, **props}},
            )

    index_result = await Neo4jSchemaManager(neo4j_driver).create_vector_index(
        NeoLabel.CONTENT_CHUNK
    )
    assert index_result.is_ok, f"vector index setup failed: {index_result}"

    adapter = Neo4jContentAdapter(_DriverConnection(neo4j_driver))
    for uid in _PARENTS:
        chunk = ContentChunk(
            parent_uid=uid,
            chunk_index=0,
            chunk_type=ContentChunkType.EXPLANATION,
            text=f"A passage about breath awareness under {uid}.",
            context_before="",
            context_after="",
        )
        stored = await adapter.store_content_with_chunks(
            uid, CurriculumContent(unit_uid=uid, body="Breath awareness body.", chunks=(chunk,))
        )
        assert stored, f"content adapter failed to persist the chunk under {uid}"

    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (:Entity {fixture: $fixture})-[:HAS_CONTENT]->(:Content)
                  -[:HAS_CHUNK]->(chunk:ContentChunk)
            CALL db.create.setNodeVectorProperty(chunk, 'embedding', $embedding)
            """,
            {"fixture": _FIXTURE_VALUE, "embedding": _EMBEDDING},
        )
        await session.run("CALL db.awaitIndexes(120)")

    yield

    async with neo4j_driver.session() as session:
        await session.run(_DELETE_FIXTURE, {"fixture": _FIXTURE_VALUE})


async def _visible_parents(neo4j_driver: AsyncDriver, viewer_uid: str | None) -> set[str]:
    backend = VectorSearchBackend(executor=Neo4jQueryExecutor(neo4j_driver))
    result = await backend.semantic_search_chunks(
        query_embedding=_EMBEDDING,
        limit=10,
        threshold=0.5,
        parent_filters={_FIXTURE_KEY: _FIXTURE_VALUE},
        viewer_uid=viewer_uid,
    )
    assert result.is_ok, f"chunk search failed: {result}"
    return {hit["parent_uid"] for hit in result.value}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_control_every_seeded_chunk_is_in_the_index(neo4j_driver, seeded_audiences):
    """Control: the raw index returns all five chunks — what the clause then narrows.

    Proves an absent parent below is the audience clause's doing, not a broken
    fixture, a missing index, or an unwritten embedding.
    """
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            CALL db.index.vector.queryNodes('contentchunk_embedding_idx', 50, $embedding)
            YIELD node AS chunk
            MATCH (chunk)<-[:HAS_CHUNK]-(:Content)<-[:HAS_CONTENT]-(parent:Entity {fixture: $fixture})
            RETURN collect(DISTINCT parent.uid) AS parents
            """,
            {"embedding": _EMBEDDING, "fixture": _FIXTURE_VALUE},
        )
        record = await result.single()
    assert record is not None
    assert set(record["parents"]) == set(_PARENTS)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_viewer_reads_published_curriculum_only(neo4j_driver, seeded_audiences):
    """Anonymous / viewer-less: the published PathStep, and nothing anyone owns."""
    assert await _visible_parents(neo4j_driver, viewer_uid=None) == {_PUBLISHED_PS}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_viewer_reads_curriculum_plus_their_own_notes_only(neo4j_driver, seeded_audiences):
    """Each user sees the published PathStep plus their own non-private note.

    FAILS on the pre-fix backend, which returned all five parents to everyone.
    """
    assert await _visible_parents(neo4j_driver, viewer_uid=_ALICE) == {_PUBLISHED_PS, _ALICE_NOTE}
    assert await _visible_parents(neo4j_driver, viewer_uid=_BOB) == {_PUBLISHED_PS, _BOB_NOTE}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_draft_curriculum_and_private_notes_never_surface(neo4j_driver, seeded_audiences):
    """The publication gate and the private gate hold for every audience."""
    for viewer in (None, _ALICE, _BOB):
        visible = await _visible_parents(neo4j_driver, viewer_uid=viewer)
        assert _DRAFT_PS not in visible, f"draft PathStep leaked to viewer={viewer!r}"
        assert _ALICE_PRIVATE_NOTE not in visible, f"private note leaked to viewer={viewer!r}"
