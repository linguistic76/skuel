"""
Unit tests for EmbeddingBackgroundWorker.subscribe() + drain() — script mode.

ADR-074 script-mode freshness: a one-shot sync (vault_bridge_sync) subscribes
the worker before ingesting, then drains both queues once after persistence,
so its embedding events are processed in-process instead of evaporating with
the script. Covers:

- drain() empties both queues across multiple batch slices
- drain() terminates on a persistently failing request (bounded retries)
- subscribe() → publish → drain() round-trips through a real InMemoryEventBus

Mock embeddings service + content adapter — no Neo4j, no timer loop.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from core.events import ChunkEmbeddingRequested, TaskEmbeddingRequested
from core.services.background.embedding_worker import (
    MAX_GENERATION_ATTEMPTS,
    EmbeddingBackgroundWorker,
    _PendingChunkRequest,
    _PendingRequest,
)
from core.utils.result_simplified import Errors, Result

VECTOR = [0.1] * 1024


def _event(i: int, text: str | None = None) -> TaskEmbeddingRequested:
    return TaskEmbeddingRequested(
        entity_uid=f"task.test{i}",
        entity_type="task",
        embedding_text=text if text is not None else f"text {i}",
        requested_at=datetime.now(),
    )


def _chunk_event(parent: str) -> ChunkEmbeddingRequested:
    return ChunkEmbeddingRequested(
        parent_uid=parent,
        chunk_uids=(f"{parent}:c1", f"{parent}:c2"),
        chunk_texts=("alpha", "beta"),
        requested_at=datetime.now(),
    )


def _service() -> MagicMock:
    service = MagicMock()
    service.model = "test-embedder"
    service.create_embedding = AsyncMock(return_value=Result.ok(VECTOR))
    service.create_batch_embeddings = AsyncMock(return_value=Result.ok([VECTOR, VECTOR]))
    service.store_embedding_with_metadata = AsyncMock(return_value=Result.ok(None))
    return service


def _chunk_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.store_chunk_embeddings = AsyncMock(return_value=True)
    return adapter


def _worker(service: MagicMock, batch_size: int = 25) -> EmbeddingBackgroundWorker:
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    return EmbeddingBackgroundWorker(
        event_bus=bus,
        embeddings_service=service,
        batch_size=batch_size,
        batch_interval_seconds=1,
    )


@pytest.mark.asyncio
async def test_drain_processes_both_queues_across_batches():
    """drain() slices both queues batch by batch until empty — no timer loop."""
    service = _service()
    worker = _worker(service, batch_size=2)
    adapter = _chunk_adapter()
    worker.content_adapter = adapter

    worker._pending_requests = [_PendingRequest(_event(i)) for i in range(5)]
    worker._pending_chunk_requests = [_PendingChunkRequest(_chunk_event("ps:test:one"))]

    drained = await worker.drain()

    assert drained == {"entity_requests": 5, "chunk_parents": 1}
    assert worker._pending_requests == []
    assert worker._pending_chunk_requests == []
    assert service.store_embedding_with_metadata.await_count == 5
    adapter.store_chunk_embeddings.assert_awaited_once()


@pytest.mark.asyncio
async def test_drain_on_empty_queues_is_a_noop():
    """Nothing queued (e.g. a sync that changed nothing) → immediate return."""
    service = _service()
    worker = _worker(service)

    drained = await worker.drain()

    assert drained == {"entity_requests": 0, "chunk_parents": 0}
    assert service.create_embedding.await_count == 0


@pytest.mark.asyncio
async def test_drain_terminates_on_persistent_failure():
    """A request that always fails re-queues within drain until the attempt
    cap drops it — drain returns instead of looping forever."""
    service = _service()
    service.create_embedding = AsyncMock(
        return_value=Result.fail(Errors.integration(service="OpenAI", message="always fails"))
    )
    worker = _worker(service)
    worker._pending_requests = [_PendingRequest(_event(0))]

    drained = await worker.drain()

    assert worker._pending_requests == []
    assert worker._total_dropped == 1
    # Each retry pass re-dequeues the request, so the count includes retries.
    assert drained["entity_requests"] == MAX_GENERATION_ATTEMPTS
    assert service.create_embedding.await_count == MAX_GENERATION_ATTEMPTS


@pytest.mark.asyncio
async def test_subscribe_publish_drain_round_trip():
    """The script-mode sequence end-to-end on a real InMemoryEventBus:
    subscribe() → ingest publishes → drain() embeds and stores."""
    service = _service()
    bus = InMemoryEventBus()
    worker = EmbeddingBackgroundWorker(
        event_bus=bus,
        embeddings_service=service,
        batch_size=25,
        batch_interval_seconds=1,
    )
    adapter = _chunk_adapter()
    worker.content_adapter = adapter

    worker.subscribe()
    await bus.publish_async(_event(0))
    await bus.publish_async(_chunk_event("ps:test:round-trip"))

    assert len(worker._pending_requests) == 1
    assert len(worker._pending_chunk_requests) == 1

    drained = await worker.drain()

    assert drained == {"entity_requests": 1, "chunk_parents": 1}
    service.store_embedding_with_metadata.assert_awaited_once_with(
        uid="task.test0", label="Task", embedding=VECTOR
    )
    adapter.store_chunk_embeddings.assert_awaited_once()
