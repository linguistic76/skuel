"""
Integration Test: Chunk Embedding Pipeline (Stage 2)
======================================================

Verifies the end-to-end flow:
  PathStep ingestion → :ContentChunk persistence → ChunkEmbeddingRequested event
  → EmbeddingBackgroundWorker → :ContentChunk.embedding populated in Neo4j.

The HuggingFace embeddings service is replaced with a deterministic fake so the
test does not depend on HF_API_TOKEN or external network. The fake mirrors the
two methods the worker calls (`create_batch_embeddings`, `.model`).

The worker's `start()` method spins an infinite asyncio loop with a 30s
sleep; we avoid that by subscribing the worker's handler manually and then
draining the queue via `_process_chunk_batch()` directly.
"""

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from core.events import ChunkEmbeddingRequested
from core.services.background.embedding_worker import EmbeddingBackgroundWorker
from core.services.entity_chunking_service import EntityChunkingService
from core.utils.result_simplified import Result


class _DriverConnection:
    """Adapts the integration test driver fixture to the Neo4jConnection
    `execute_query(query, params) -> list[Record]` shape expected by
    Neo4jContentAdapter."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return [record async for record in result]


class _FakeEmbeddingsService:
    """Deterministic stand-in for EmbeddingsService.

    Returns a fixed-length unit vector per input text so the worker can persist
    something to `ContentChunk.embedding` without touching the network.
    """

    model = "test-embedder-1d"

    async def create_batch_embeddings(
        self, texts: list[str], metadata_list: list[dict[str, Any]] | None = None
    ) -> Result[list[list[float]]]:
        # Embedding dimension is irrelevant for the wiring test — what matters
        # is that store_chunk_embeddings receives one vector per chunk_uid.
        return Result.ok([[float(len(t) % 7) / 7.0] * 4 for t in texts])


@pytest.mark.asyncio
async def test_chunk_embedding_pipeline_end_to_end(neo4j_driver):
    """A PathStep ingestion produces chunks with embeddings in Neo4j."""
    ku_content = """---
type: Lesson
title: Stage 2 Pipeline
domain: tech
---

# Embedding Pipeline

Stage 2 wires the chunk embedding flow.

## Why

Without this stage the worker never sees the events.

## How

Ingestion publishes ChunkEmbeddingRequested and the worker drains the queue.
"""

    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(ku_content)
        temp_path = Path(f.name)

    try:
        event_bus = InMemoryEventBus()
        content_adapter = Neo4jContentAdapter(_DriverConnection(neo4j_driver))
        embeddings = _FakeEmbeddingsService()

        # Wire the worker: we subscribe its queue handler directly rather than
        # calling start(), since start() runs an infinite 30s-tick loop.
        worker = EmbeddingBackgroundWorker(
            event_bus=event_bus,
            embeddings_service=embeddings,
            content_adapter=content_adapter,
        )
        event_bus.subscribe(ChunkEmbeddingRequested, worker._queue_chunk_request)

        ingestion = make_unified_ingestion_service(
            driver=neo4j_driver,
            chunking_service=EntityChunkingService(),
            content_adapter=content_adapter,
            event_bus=event_bus,
        )

        result = await ingestion.ingest_file(temp_path)
        assert result.is_ok, (
            f"Ingestion failed: {result.expect_error() if result.is_error else 'unknown'}"
        )
        ps_uid = result.value["uid"]
        assert result.value["chunks_generated"] is True

        # The publish path is async and spawns a background task on the bus.
        # Yield once so the subscriber's handler appends to the queue before we
        # drain it.
        import asyncio

        await asyncio.sleep(0)
        # Some event bus implementations defer dispatch to a task — give it a tick.
        for _ in range(5):
            if worker._pending_chunk_requests:
                break
            await asyncio.sleep(0.05)

        assert worker._pending_chunk_requests, (
            "Expected at least one ChunkEmbeddingRequested in the worker queue"
        )

        # Drain directly — bypasses the 30s sleep in _process_batches_loop.
        batch = list(worker._pending_chunk_requests)
        worker._pending_chunk_requests.clear()
        await worker._process_chunk_batch(batch)

        async with neo4j_driver.session() as session:
            cypher_result = await session.run(
                """
                MATCH (c:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
                WHERE chunk.embedding IS NOT NULL
                RETURN count(chunk) AS embedded
                """,
                {"uid": ps_uid},
            )
            record = await cypher_result.single()

        assert record is not None and record["embedded"] > 0, (
            f"Expected embedded chunks in Neo4j, got {record}"
        )

    finally:
        temp_path.unlink()
