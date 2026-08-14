"""
Integration test: force re-ingestion against real Neo4j (force ≠ full).

Proves the sanctioned re-chunk/migration path end-to-end through the batch
door (``ingest_directory``):

- A smart sync ingests a PathStep and creates :Content/:ContentChunk nodes
  plus an IngestionMetadata tracker row.
- A second smart sync SKIPS the unchanged file (hash/mtime match) — the
  control that the ADR-074 migration had to work around with manual
  tracker-row invalidation.
- A ``force=True`` sync re-processes the unchanged file: chunks are
  regenerated (delete-then-create — count stable, all-new nodes, no
  duplicates) and the tracker row is re-stamped.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.services.entity_chunking_service import EntityChunkingService
from core.services.ingestion.types import IncrementalStats

_PS_UID = "ps.test.force-reingest"

_PS_FIXTURE = """---
type: path_step
uid: ps.test.force-reingest
title: Force Reingest Fixture
domain: knowledge
---

# Heading One

First body paragraph for the force re-ingestion integration fixture.

## Definitions

A chunk is a semantic unit of content used by retrieval.

## Examples

Here is an example paragraph that gives the chunker enough body to split.
"""


class _DriverConnection:
    """Adapter so Neo4jContentAdapter can use the integration neo4j_driver fixture."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return [record async for record in result]


@pytest_asyncio.fixture
async def force_ingestion_service(neo4j_driver):
    """UnifiedIngestionService with tracker + chunking wired (smart/force modes)."""
    from adapters.persistence.neo4j.ingestion_backend import IngestionBackend

    executor = Neo4jQueryExecutor(neo4j_driver)
    service = make_unified_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=IngestionBackend(executor=executor),
        chunking_service=EntityChunkingService(),
        content_adapter=Neo4jContentAdapter(_DriverConnection(neo4j_driver)),
    )
    yield service
    # Session-scoped container — clean up this test's nodes so other tests
    # never see them.
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (c:Content {uid: $uid})
            OPTIONAL MATCH (c)-[:HAS_CHUNK]->(chunk:ContentChunk)
            DETACH DELETE c, chunk
            """,
            {"uid": _PS_UID},
        )
        await session.run("MATCH (p:Entity {uid: $uid}) DETACH DELETE p", {"uid": _PS_UID})
        await session.run(
            "MATCH (s:IngestionMetadata) WHERE s.entity_uid = $uid DELETE s", {"uid": _PS_UID}
        )


async def _chunk_counts(neo4j_driver) -> tuple[int, int]:
    """(total chunks, chunks still carrying the pre-force test marker)."""
    async with neo4j_driver.session() as session:
        res = await session.run(
            """
            MATCH (:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
            RETURN count(chunk) AS total,
                   count(chunk.force_test_marker) AS marked
            """,
            {"uid": _PS_UID},
        )
        record = await res.single()
        return record["total"], record["marked"]


async def _mark_chunks(neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
            SET chunk.force_test_marker = true
            """,
            {"uid": _PS_UID},
        )


@pytest.mark.asyncio
async def test_force_reprocesses_unchanged_path_step_and_regenerates_chunks(
    neo4j_driver, force_ingestion_service, tmp_path: Path
) -> None:
    vault = tmp_path / "force_vault"
    vault.mkdir()
    (vault / "force-reingest.md").write_text(_PS_FIXTURE, encoding="utf-8")

    # 1. Initial smart sync: file ingests, chunks + tracker row created.
    first = await force_ingestion_service.ingest_directory(vault, ingestion_mode="smart")
    assert first.is_ok, f"initial ingest failed: {first}"
    first_stats = cast("IncrementalStats", first.value)
    assert first_stats.files_ingested == 1

    initial_total, _ = await _chunk_counts(neo4j_driver)
    assert initial_total > 0, "initial ingest should create :ContentChunk nodes"

    # Stamp the current chunk nodes so regeneration is observable: fresh nodes
    # won't carry the marker.
    await _mark_chunks(neo4j_driver)

    # 2. Control: an unchanged file is skipped by a plain smart sync — this is
    #    the gap force closes (no admin door re-processes a hash/mtime match).
    second = await force_ingestion_service.ingest_directory(vault, ingestion_mode="smart")
    assert second.is_ok, f"control ingest failed: {second}"
    second_stats = cast("IncrementalStats", second.value)
    assert second_stats.files_ingested == 0
    assert second_stats.files_skipped == 1
    total, marked = await _chunk_counts(neo4j_driver)
    assert (total, marked) == (initial_total, initial_total), (
        "a skipped file must leave its chunk nodes untouched"
    )

    # 3. Force: the unchanged file re-processes and its chunks regenerate.
    forced = await force_ingestion_service.ingest_directory(
        vault, ingestion_mode="smart", force=True
    )
    assert forced.is_ok, f"force ingest failed: {forced}"
    forced_stats = cast("IncrementalStats", forced.value)
    assert forced_stats.files_ingested == 1
    assert forced_stats.files_skipped == 0

    total, marked = await _chunk_counts(neo4j_driver)
    # Delete-then-create idempotency: same chunk count (no duplicates), and
    # every chunk node is new (none carries the pre-force marker).
    assert total == initial_total, f"expected {initial_total} chunks (no duplication), got {total}"
    assert marked == 0, "force must regenerate chunks (delete-then-create), not keep the old nodes"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
