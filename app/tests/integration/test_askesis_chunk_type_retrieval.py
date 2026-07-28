"""Askesis intent-filtered chunk retrieval actually returns rows (real Neo4j).

End-to-end proof for the silent-zero bug fixed 2026-07-27: the intent→chunk-type
map spelled chunk types in UPPERCASE while ``Neo4jContentAdapter`` persists
``chunk.chunk_type = chunk_type.value`` (lowercase). ``semantic_search_chunks``
filters with a bare ``AND chunk.chunk_type IN $chunk_types``, and Neo4j matches
ZERO rows on a value no node carries — no error, no warning, just an empty
answer for five of eight ``QueryIntent``s.

Nothing here is mocked between the two ends: the REAL content adapter writes the
chunks and the REAL vector-search backend reads them back through the real
vector index. The unfiltered control query runs first — a green filtered
assertion means nothing unless the corpus is provably retrievable without the
filter.

Unit-level sibling (no Docker): tests/unit/test_askesis_chunk_type_writer_parity.py
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager
from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
from core.constants import EmbeddingGeometry
from core.models.enums.neo_labels import NeoLabel
from core.models.ps_content.content import CurriculumContent
from core.models.ps_content.content_chunks import ContentChunk, ContentChunkType
from core.models.query_types import QueryIntent
from core.services.askesis.context_retriever import _intent_to_chunk_types

_PARENT_UID = "ps.test.chunk_type_retrieval"

# One chunk per type the PRACTICE intent asks for, plus one it must exclude —
# so the filter has something to both find and reject.
_SEEDED_TYPES = (
    ContentChunkType.EXERCISE,
    ContentChunkType.EXAMPLE,
    ContentChunkType.DEFINITION,
)

# Every chunk gets the same unit vector, so cosine similarity is 1.0 for all of
# them and ranking never decides what survives — only the chunk_type filter does.
_EMBEDDING = [1.0] + [0.0] * (EmbeddingGeometry.DIMENSION - 1)


class _DriverConnection:
    """Adapts the driver fixture to the Neo4jConnection shape the adapter wants."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return [record async for record in result]


@pytest_asyncio.fixture
async def seeded_chunks(neo4j_driver):
    """Seed one :ContentChunk per _SEEDED_TYPES via the REAL content adapter."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (e:Entity {uid: $uid})
            OPTIONAL MATCH (e)-[:HAS_CONTENT]->(c:Content)
            OPTIONAL MATCH (c)-[:HAS_CHUNK]->(chunk:ContentChunk)
            DETACH DELETE chunk, c, e
            """,
            {"uid": _PARENT_UID},
        )
        await session.run(
            "CREATE (:Entity {uid: $uid, title: 'Chunk casing fixture', entity_type: 'path_step'})",
            {"uid": _PARENT_UID},
        )

    # The vector index the backend queries by name. Created through the real
    # schema manager so its name/geometry can never drift from production's.
    index_result = await Neo4jSchemaManager(neo4j_driver).create_vector_index(
        NeoLabel.CONTENT_CHUNK
    )
    assert index_result.is_ok, f"vector index setup failed: {index_result}"

    chunks = tuple(
        ContentChunk(
            parent_uid=_PARENT_UID,
            chunk_index=index,
            chunk_type=chunk_type,
            text=f"A {chunk_type.value} passage about breath awareness.",
            context_before="",
            context_after="",
        )
        for index, chunk_type in enumerate(_SEEDED_TYPES)
    )
    stored = await Neo4jContentAdapter(_DriverConnection(neo4j_driver)).store_content_with_chunks(
        _PARENT_UID,
        CurriculumContent(unit_uid=_PARENT_UID, body="Breath awareness body.", chunks=chunks),
    )
    assert stored, "content adapter failed to persist the fixture chunks"

    # The adapter leaves embedding NULL (the worker fills it, ADR-074); the
    # vector index needs one to return the chunk at all.
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
            CALL db.create.setNodeVectorProperty(chunk, 'embedding', $embedding)
            """,
            {"uid": _PARENT_UID, "embedding": _EMBEDDING},
        )
        await session.run("CALL db.awaitIndexes(120)")

    yield

    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (e:Entity {uid: $uid})
            OPTIONAL MATCH (e)-[:HAS_CONTENT]->(c:Content)
            OPTIONAL MATCH (c)-[:HAS_CHUNK]->(chunk:ContentChunk)
            DETACH DELETE chunk, c, e
            """,
            {"uid": _PARENT_UID},
        )


async def _search(neo4j_driver, chunk_types: list[str] | None) -> list[dict[str, Any]]:
    backend = VectorSearchBackend(executor=Neo4jQueryExecutor(neo4j_driver))
    result = await backend.semantic_search_chunks(
        query_embedding=_EMBEDDING,
        limit=10,
        threshold=0.5,
        chunk_types=chunk_types,
        parent_uid=_PARENT_UID,
    )
    assert result.is_ok, f"chunk search failed: {result}"
    return list(result.value)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unfiltered_search_retrieves_the_seeded_chunks(neo4j_driver, seeded_chunks):
    """Control: without a chunk_type filter every seeded chunk comes back.

    This is what makes the filtered test below meaningful — it proves an empty
    filtered result would be the filter's doing, not a broken fixture, a missing
    index, or an unwritten embedding.
    """
    hits = await _search(neo4j_driver, chunk_types=None)

    assert {hit["chunk_type"] for hit in hits} == {t.value for t in _SEEDED_TYPES}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_practice_intent_filter_matches_persisted_chunk_types(neo4j_driver, seeded_chunks):
    """The PRACTICE intent's filter retrieves rows instead of silently matching zero.

    FAILS on the pre-fix code: ``_intent_to_chunk_types`` returned
    ``["EXERCISE", "EXAMPLE"]``, no chunk carries those values, and the search
    returned [] with no error.
    """
    chunk_types = _intent_to_chunk_types(QueryIntent.PRACTICE)
    assert chunk_types is not None

    hits = await _search(neo4j_driver, chunk_types=chunk_types)

    assert hits, (
        f"PRACTICE requested {chunk_types} and Neo4j matched zero rows — the filter "
        f"does not speak the vocabulary the content adapter writes"
    )
    assert {hit["chunk_type"] for hit in hits} == {
        ContentChunkType.EXERCISE.value,
        ContentChunkType.EXAMPLE.value,
    }


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "intent",
    [
        QueryIntent.PREREQUISITE,
        QueryIntent.PRACTICE,
        QueryIntent.HIERARCHICAL,
        QueryIntent.EXPLORATORY,
        QueryIntent.RELATIONSHIP,
    ],
)
async def test_every_mapped_intent_retrieves_something(neo4j_driver, seeded_chunks, intent):
    """No mapped intent is a silent zero.

    Each of the five mapped intents includes at least one seeded type, so an
    empty result can only mean the filter and the writer disagree.
    """
    chunk_types = _intent_to_chunk_types(intent)
    assert chunk_types is not None

    hits = await _search(neo4j_driver, chunk_types=chunk_types)

    assert hits, f"{intent.name} requested {chunk_types} and retrieved nothing"
