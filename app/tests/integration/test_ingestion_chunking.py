"""
Integration Test: Automatic Chunking During Ingestion
=======================================================

Tests that KU entities automatically generate chunks during ingestion
without requiring explicit chunking calls.

Implementation (January 2026) - Automatic Chunking
"""

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pytest

from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from core.services.entity_chunking_service import EntityChunkingService


class _DriverConnection:
    """Thin shim adapting an AsyncDriver to the Neo4jConnection.execute_query shape
    expected by Neo4jContentAdapter, so tests can use the integration neo4j_driver
    fixture directly without spinning up a separate Neo4jConnection singleton.
    """

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return [record async for record in result]


@pytest.mark.asyncio
async def test_ingest_file_creates_chunks(neo4j_driver):
    """Test that ingesting a KU file automatically creates chunks AND persists them to Neo4j."""
    # Given: A markdown file with curriculum content
    ku_content = """---
type: Lesson
title: Python Basics
domain: tech
---

# Introduction to Python

Python is a high-level programming language.

## Variables

Variables store data values. You can create a variable like this:

```python
x = 5
name = "John"
```

## Functions

Functions are reusable blocks of code:

```python
def greet(name):
    return f"Hello, {name}!"
```

## Summary

Python is easy to learn and powerful.
"""

    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(ku_content)
        temp_path = Path(f.name)

    try:
        # Given: UnifiedIngestionService with chunking enabled AND a content adapter
        # so chunks persist to Neo4j (Stage 1 of the chunk-retrieval pipeline).
        chunking_service = EntityChunkingService()
        content_adapter = Neo4jContentAdapter(_DriverConnection(neo4j_driver))
        ingestion_service = make_unified_ingestion_service(
            driver=neo4j_driver,
            chunking_service=chunking_service,
            content_adapter=content_adapter,
        )

        # When: Ingesting the file
        result = await ingestion_service.ingest_file(temp_path)

        # Then: Ingestion succeeds
        assert result.is_ok, (
            f"Ingestion failed: {result.expect_error() if result.is_error else 'unknown'}"
        )
        ingestion_data = result.value

        # Then: Chunks were generated
        assert ingestion_data["chunks_generated"] is True, "Chunks should be generated for KU"
        assert ingestion_data["entity_type"] == "path_step", "Entity type should be path_step"

        # Then: Chunks are in the chunking service cache
        ku_uid = ingestion_data["uid"]
        cached_content = chunking_service._content_cache.get(ku_uid)

        assert cached_content is not None, "Should be able to retrieve cached content"
        chunks = list(cached_content.chunks)
        assert len(chunks) > 0, "Should have at least one chunk"

        # Verify chunk types detected
        chunk_types = {chunk.chunk_type for chunk in chunks}
        assert len(chunk_types) > 0, "Should have detected chunk types"

        # Verify content was chunked (should have multiple chunks for this content)
        assert len(chunks) >= 3, f"Expected at least 3 chunks, got {len(chunks)}"

        # Then: Chunks were persisted to Neo4j (this is the gap Stage 1 closes).
        # Embeddings are populated later by the background worker — at this point
        # we only assert the nodes and HAS_CHUNK edges exist.
        async with neo4j_driver.session() as session:
            cypher_result = await session.run(
                """
                MATCH (c:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
                RETURN count(chunk) AS n, collect(DISTINCT chunk.chunk_type) AS types
                """,
                {"uid": ku_uid},
            )
            record = await cypher_result.single()

        assert record is not None, "Content node should exist with chunks"
        assert record["n"] > 0, f"Expected ContentChunk nodes in Neo4j, got {record['n']}"
        assert len(record["types"]) > 0, "Persisted chunks should have chunk_type set"

    finally:
        # Cleanup
        temp_path.unlink()


@pytest.mark.asyncio
async def test_batch_door_ingest_directory_creates_chunks(neo4j_driver, tmp_path: Path):
    """The batch door (ingest_directory) must produce the same PathStep content
    shape as the single-file door: content popped off the :Entity node (word_count
    in its place), :Content + :ContentChunk persisted, and a single
    ChunkEmbeddingRequested carrying every persisted chunk id (ADR-074 PR 2)."""
    from core.events.chunk_events import ChunkEmbeddingRequested

    ps_uid = "ps.test.batch-chunk-unification"
    body = """# Batch Chunk Unification

PathSteps ingested through the directory door get the same chunk treatment
as the single-file door.

## Why

Body-content semantics live in CHUNK embeddings; the entity vector covers
frontmatter fields only.

## Summary

One shared chunk step, two doors.
"""
    ps_file = tmp_path / "batch-chunk-unification.md"
    ps_file.write_text(
        f"---\ntype: path_step\nuid: {ps_uid}\ntitle: Batch Chunk Unification\n---\n\n{body}"
    )

    class _CapturingBus:
        def __init__(self) -> None:
            self.published: list[Any] = []

        async def publish_async(self, event: Any) -> None:
            self.published.append(event)

    bus = _CapturingBus()
    chunking_service = EntityChunkingService()
    content_adapter = Neo4jContentAdapter(_DriverConnection(neo4j_driver))
    ingestion_service = make_unified_ingestion_service(
        driver=neo4j_driver,
        chunking_service=chunking_service,
        content_adapter=content_adapter,
        event_bus=bus,
    )

    result = await ingestion_service.ingest_directory(tmp_path)
    assert result.is_ok, (
        f"Batch ingestion failed: {result.expect_error() if result.is_error else 'unknown'}"
    )

    normalized_uid = ps_uid  # authored = stored, verbatim (colon alias deleted 2026-08-14)

    async with neo4j_driver.session() as session:
        cypher_result = await session.run(
            """
            MATCH (ps:PathStep {uid: $uid})
            OPTIONAL MATCH (c:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
            RETURN ps.content AS entity_content,
                   ps.word_count AS word_count,
                   count(chunk) AS chunk_count,
                   collect(chunk.uid) AS chunk_uids
            """,
            {"uid": normalized_uid},
        )
        record = await cypher_result.single()

    assert record is not None, "Batch-ingested PathStep should exist"
    # content never lands on the :Entity node — same shape as the single-file door
    assert record["entity_content"] is None, "content must not be a node property"
    assert record["word_count"] == len(body.split()), "word_count set from popped content"
    assert record["chunk_count"] > 0, "Expected persisted :ContentChunk nodes"

    # one ChunkEmbeddingRequested carrying every persisted chunk id
    chunk_events = [e for e in bus.published if isinstance(e, ChunkEmbeddingRequested)]
    assert len(chunk_events) == 1, f"Expected 1 chunk event, got {len(chunk_events)}"
    assert chunk_events[0].parent_uid == normalized_uid
    assert set(chunk_events[0].chunk_uids) == set(record["chunk_uids"])


@pytest.mark.asyncio
async def test_empty_body_reingest_clears_content_subtree(neo4j_driver, tmp_path: Path):
    """A PathStep re-ingested with its body emptied must not keep the previous
    body's :Content/:ContentChunk subtree or word_count — the
    explicit clear path (ADR-074). The bulk upsert alone can't do it: `n +=
    props` never removes omitted keys, and orphaned chunks would keep serving
    stale vectors from the chunk index."""
    ps_uid = "ps.test.empty-body-clear"
    ps_file = tmp_path / "empty-body-clear.md"
    ps_file.write_text(
        f"---\ntype: path_step\nuid: {ps_uid}\ntitle: Empty Body Clear\n---\n\n"
        "# Original\n\nThis body exists on first ingest and is removed on the second.\n"
    )

    chunking_service = EntityChunkingService()
    content_adapter = Neo4jContentAdapter(_DriverConnection(neo4j_driver))
    ingestion_service = make_unified_ingestion_service(
        driver=neo4j_driver,
        chunking_service=chunking_service,
        content_adapter=content_adapter,
    )

    result = await ingestion_service.ingest_directory(tmp_path)
    assert result.is_ok

    normalized_uid = ps_uid  # authored = stored, verbatim (colon alias deleted 2026-08-14)
    subtree_query = """
        MATCH (ps:PathStep {uid: $uid})
        OPTIONAL MATCH (ps)-[:HAS_CONTENT]->(c:Content)
        OPTIONAL MATCH (c)-[:HAS_CHUNK]->(chunk:ContentChunk)
        RETURN ps.word_count AS word_count,
               count(DISTINCT c) AS content_nodes,
               count(DISTINCT chunk) AS chunk_nodes
    """

    async with neo4j_driver.session() as session:
        record = await (await session.run(subtree_query, {"uid": normalized_uid})).single()
    assert record is not None
    assert record["word_count"] > 0, "First ingest should set a non-zero word_count"
    assert record["content_nodes"] == 1, "First ingest should persist the :Content node"
    assert record["chunk_nodes"] > 0, "First ingest should persist :ContentChunk nodes"

    # Re-ingest the same uid with the body emptied
    ps_file.write_text(f"---\ntype: path_step\nuid: {ps_uid}\ntitle: Empty Body Clear\n---\n")
    result = await ingestion_service.ingest_directory(tmp_path)
    assert result.is_ok

    async with neo4j_driver.session() as session:
        record = await (await session.run(subtree_query, {"uid": normalized_uid})).single()
    assert record is not None
    assert record["word_count"] == 0, "Emptied body must overwrite word_count with 0"
    assert record["content_nodes"] == 0, "Stale :Content must be deleted"
    assert record["chunk_nodes"] == 0, "Stale :ContentChunk nodes must be deleted"


@pytest.mark.asyncio
async def test_chunking_failure_does_not_fail_ingestion(neo4j_driver):
    """Test that chunking failure doesn't prevent successful ingestion"""
    # Given: A KU file
    ku_content = """---
type: Lesson
title: Short KU
domain: tech
---

Just a short piece of content.
"""

    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(ku_content)
        temp_path = Path(f.name)

    try:
        # Given: UnifiedIngestionService WITHOUT chunking service (None)
        ingestion_service = make_unified_ingestion_service(
            driver=neo4j_driver,
            chunking_service=None,  # No chunking service
        )

        # When: Ingesting the file
        result = await ingestion_service.ingest_file(temp_path)

        # Then: Ingestion still succeeds
        assert result.is_ok, "Ingestion should succeed even without chunking"
        ingestion_data = result.value

        # Then: Chunks were NOT generated (graceful degradation)
        assert ingestion_data["chunks_generated"] is False, "No chunks should be generated"
        assert ingestion_data["success"] is True, "Ingestion itself should succeed"

    finally:
        # Cleanup
        temp_path.unlink()


@pytest.mark.asyncio
async def test_non_ku_entities_skip_chunking(neo4j_driver):
    """Test that non-KU entities don't attempt chunking"""
    # Given: A Task file (not KU)
    task_content = """---
type: task
title: Complete project
status: active
---

This is a task description.
"""

    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(task_content)
        temp_path = Path(f.name)

    try:
        # Given: UnifiedIngestionService with chunking enabled
        chunking_service = EntityChunkingService()
        ingestion_service = make_unified_ingestion_service(
            driver=neo4j_driver,
            chunking_service=chunking_service,
        )

        # When: Ingesting a non-KU file
        result = await ingestion_service.ingest_file(temp_path)

        # Then: Ingestion succeeds
        assert result.is_ok, "Ingestion should succeed"
        ingestion_data = result.value

        # Then: Chunks were NOT generated (only for KU entities)
        assert ingestion_data["chunks_generated"] is False, "Tasks should not be chunked"
        assert ingestion_data["entity_type"] == "task", "Entity type should be task"

    finally:
        # Cleanup
        temp_path.unlink()


@pytest.mark.asyncio
async def test_ku_with_minimal_content_generates_chunks(neo4j_driver):
    """Test that KU with minimal content still generates chunks"""
    # Given: A KU file with minimal content (just one sentence)
    ku_content = """---
type: Lesson
title: Minimal KU
domain: tech
---

Python is a programming language.
"""

    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(ku_content)
        temp_path = Path(f.name)

    try:
        # Given: UnifiedIngestionService with chunking enabled
        chunking_service = EntityChunkingService()
        ingestion_service = make_unified_ingestion_service(
            driver=neo4j_driver,
            chunking_service=chunking_service,
        )

        # When: Ingesting a KU with minimal content
        result = await ingestion_service.ingest_file(temp_path)

        # Then: Ingestion succeeds
        assert result.is_ok, "Ingestion should succeed"
        ingestion_data = result.value

        # Then: Chunks were generated even for minimal content
        assert ingestion_data["chunks_generated"] is True, (
            "Should generate chunks for minimal content"
        )

        # Verify at least one chunk exists
        ku_uid = ingestion_data["uid"]
        cached_content = chunking_service._content_cache.get(ku_uid)
        assert cached_content is not None, "Should have cached content after ingestion"
        assert cached_content.chunk_count >= 1, "Should have at least one chunk for minimal content"

    finally:
        # Cleanup
        temp_path.unlink()
