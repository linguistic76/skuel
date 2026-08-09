"""
Integration test: BatchChunkingService end-to-end against real Neo4j.

Covers:
- Ingest a PathStep with body content (creates :ContentChunk nodes via existing pipeline)
- Mutate one chunk's chunking_version to simulate a stale algorithm version
- Run BatchChunkingService.regenerate_chunks() with force=False
- Verify: stale chunks replaced with fresh ones (same parent, no duplicates),
  current CHUNKING_ALGORITHM_VERSION present on every chunk.

Mirrors the test_ingestion_chunking.py fixture pattern.
"""

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pytest

from adapters.persistence.neo4j.batch_chunking_backend import BatchChunkingBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from core.models.ps_content.content_chunks import CHUNKING_ALGORITHM_VERSION
from core.services.chunks.batch_chunking_service import BatchChunkingService
from core.services.entity_chunking_service import EntityChunkingService


class _DriverConnection:
    """Adapter so Neo4jContentAdapter can use the integration neo4j_driver fixture."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return [record async for record in result]


_FIXTURE_BODY = """---
type: Lesson
title: Regeneration Test
domain: tech
---

# Heading One

This is the first body paragraph used by the regeneration test fixture.

## Definitions

A chunk is a semantic unit of content used by retrieval.

## Examples

Here is an example chunk.

```python
def example():
    return 42
```
"""


@pytest.mark.asyncio
async def test_regenerate_chunks_replaces_stale_chunks(neo4j_driver):
    """Stale chunks (older chunking_version) are replaced, not duplicated."""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(_FIXTURE_BODY)
        temp_path = Path(f.name)

    try:
        chunking_service = EntityChunkingService()
        content_adapter = Neo4jContentAdapter(_DriverConnection(neo4j_driver))
        ingestion_service = make_unified_ingestion_service(
            driver=neo4j_driver,
            chunking_service=chunking_service,
            content_adapter=content_adapter,
        )

        result = await ingestion_service.ingest_file(temp_path)
        assert result.is_ok
        parent_uid = result.value["uid"]

        # Count chunks after initial ingest
        async with neo4j_driver.session() as session:
            res = await session.run(
                """
                MATCH (c:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
                RETURN count(chunk) AS n
                """,
                {"uid": parent_uid},
            )
            record = await res.single()
            chunks_after_ingest = record["n"]

        assert chunks_after_ingest > 0

        # Mark all chunks for this parent as stale (older version)
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
                SET chunk.chunking_version = 'v0_stale'
                """,
                {"uid": parent_uid},
            )

        # Regenerate with force=False — version mismatch should pick this parent up
        service = BatchChunkingService(
            backend=BatchChunkingBackend(neo4j_driver),
            chunking_service=chunking_service,
            content_adapter=content_adapter,
            event_bus=None,  # skip embedding event in test
        )

        regen_result = await service.regenerate_chunks(parent_uids=[parent_uid], force=False)
        assert regen_result.is_ok
        stats = regen_result.value
        assert stats.total_candidates == 1
        assert stats.processed == 1
        assert stats.succeeded == 1
        assert stats.failed == 0

        # Verify chunks were replaced — count is consistent with re-chunking the
        # same body (NOT doubled), and every chunk has the current version
        async with neo4j_driver.session() as session:
            res = await session.run(
                """
                MATCH (c:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
                RETURN count(chunk) AS n,
                       collect(DISTINCT chunk.chunking_version) AS versions
                """,
                {"uid": parent_uid},
            )
            record = await res.single()

        assert record["n"] == chunks_after_ingest, (
            f"Expected {chunks_after_ingest} chunks (no duplication), got {record['n']}"
        )
        assert record["versions"] == [CHUNKING_ALGORITHM_VERSION], (
            f"All chunks should be at current version, found {record['versions']}"
        )

    finally:
        temp_path.unlink()


@pytest.mark.asyncio
async def test_regenerate_chunks_skips_already_current_when_force_false(neo4j_driver):
    """A parent whose chunks already match CHUNKING_ALGORITHM_VERSION is skipped."""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(_FIXTURE_BODY)
        temp_path = Path(f.name)

    try:
        chunking_service = EntityChunkingService()
        content_adapter = Neo4jContentAdapter(_DriverConnection(neo4j_driver))
        ingestion_service = make_unified_ingestion_service(
            driver=neo4j_driver,
            chunking_service=chunking_service,
            content_adapter=content_adapter,
        )

        result = await ingestion_service.ingest_file(temp_path)
        assert result.is_ok
        parent_uid = result.value["uid"]

        # Chunks are at current version by default (no manual mutation).
        service = BatchChunkingService(
            backend=BatchChunkingBackend(neo4j_driver),
            chunking_service=chunking_service,
            content_adapter=content_adapter,
            event_bus=None,
        )

        regen_result = await service.regenerate_chunks(parent_uids=[parent_uid], force=False)
        assert regen_result.is_ok
        stats = regen_result.value
        assert stats.total_candidates == 0, (
            "Parent already at current version should not be a candidate when force=False"
        )
        assert stats.processed == 0

    finally:
        temp_path.unlink()
