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
domain: technology
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
        chunks_result = await chunking_service.get_chunks_for_knowledge(ku_uid)

        assert chunks_result.is_ok, "Should be able to retrieve chunks"
        chunks = chunks_result.value
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
async def test_chunking_failure_does_not_fail_ingestion(neo4j_driver):
    """Test that chunking failure doesn't prevent successful ingestion"""
    # Given: A KU file
    ku_content = """---
type: Lesson
title: Short KU
domain: technology
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
domain: technology
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
        chunks_result = await chunking_service.get_chunks_for_knowledge(ku_uid)
        assert chunks_result.is_ok, "Should be able to retrieve chunks"
        chunks = chunks_result.value
        assert len(chunks) >= 1, "Should have at least one chunk for minimal content"

    finally:
        # Cleanup
        temp_path.unlink()
