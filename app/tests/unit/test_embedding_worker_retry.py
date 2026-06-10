"""
Unit tests for EmbeddingBackgroundWorker's bounded retry policy.

Covers the hardening on top of ADR-068:
- Per-item generation: one poison text fails alone, batchmates still store
- Attempt cap: a persistently failing request drops after MAX_GENERATION_ATTEMPTS
- Queue overflow: re-queueing at MAX_QUEUE_SIZE drops instead of growing
- Chunk requests get the same bounded policy per parent

No event bus loop, no Neo4j — _process_batch / _process_chunk_batch are
driven directly with mock services.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events import ChunkEmbeddingRequested, TaskEmbeddingRequested
from core.services.background.embedding_worker import (
    MAX_GENERATION_ATTEMPTS,
    MAX_QUEUE_SIZE,
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
        user_uid="user_test",
        requested_at=datetime.now(),
    )


def _worker(service: MagicMock) -> EmbeddingBackgroundWorker:
    bus = MagicMock()
    bus.publish_async = AsyncMock()  # awaited by publish_event on chunk completion
    return EmbeddingBackgroundWorker(
        event_bus=bus,
        embeddings_service=service,
        batch_size=25,
        batch_interval_seconds=1,
    )


def _service() -> MagicMock:
    service = MagicMock()
    service.create_embedding = AsyncMock(return_value=Result.ok(VECTOR))
    service.store_embedding_with_metadata = AsyncMock(return_value=Result.ok(None))
    return service


@pytest.mark.asyncio
async def test_poison_item_fails_alone_batchmates_store():
    """One failing text re-queues alone; the other items store successfully."""

    async def embed(text: str) -> Result[list[float]]:
        if text == "poison":
            return Result.fail(Errors.integration(service="OpenAI", message="boom"))
        return Result.ok(VECTOR)

    service = _service()
    service.create_embedding = AsyncMock(side_effect=embed)
    worker = _worker(service)

    batch = [
        _PendingRequest(_event(0)),
        _PendingRequest(_event(1, "poison")),
        _PendingRequest(_event(2)),
    ]
    await worker._process_batch(batch)

    # Two good items stored
    assert service.store_embedding_with_metadata.await_count == 2
    # Poison item re-queued alone, with one attempt spent
    assert len(worker._pending_requests) == 1
    assert worker._pending_requests[0].event.embedding_text == "poison"
    assert worker._pending_requests[0].attempts == 1
    assert worker._total_success == 2
    assert worker._total_dropped == 0


@pytest.mark.asyncio
async def test_raising_item_degrades_like_a_failure():
    """An exception from create_embedding is captured per item, not batch-fatal."""

    async def embed(text: str) -> Result[list[float]]:
        if text == "raiser":
            raise ConnectionError("network down")
        return Result.ok(VECTOR)

    service = _service()
    service.create_embedding = AsyncMock(side_effect=embed)
    worker = _worker(service)

    batch = [_PendingRequest(_event(0, "raiser")), _PendingRequest(_event(1))]
    await worker._process_batch(batch)

    assert service.store_embedding_with_metadata.await_count == 1
    assert len(worker._pending_requests) == 1
    assert worker._pending_requests[0].attempts == 1


@pytest.mark.asyncio
async def test_persistent_failure_drops_after_attempt_cap():
    """A request that always fails is dropped after MAX_GENERATION_ATTEMPTS — no infinite loop."""
    service = _service()
    service.create_embedding = AsyncMock(
        return_value=Result.fail(Errors.integration(service="OpenAI", message="always fails"))
    )
    worker = _worker(service)

    worker._pending_requests = [_PendingRequest(_event(0))]
    for cycle in range(MAX_GENERATION_ATTEMPTS):
        batch = worker._pending_requests
        worker._pending_requests = []
        await worker._process_batch(batch)
        if cycle < MAX_GENERATION_ATTEMPTS - 1:
            assert len(worker._pending_requests) == 1, f"should still retry after cycle {cycle}"

    # Exhausted: dropped, not re-queued
    assert worker._pending_requests == []
    assert worker._total_dropped == 1
    assert service.create_embedding.await_count == MAX_GENERATION_ATTEMPTS
    assert worker.get_metrics()["total_dropped"] == 1


@pytest.mark.asyncio
async def test_full_queue_drops_instead_of_growing():
    """Re-queueing respects MAX_QUEUE_SIZE — overflow drops with a count."""
    service = _service()
    service.create_embedding = AsyncMock(
        return_value=Result.fail(Errors.integration(service="OpenAI", message="boom"))
    )
    worker = _worker(service)
    worker._pending_requests = [_PendingRequest(_event(i)) for i in range(MAX_QUEUE_SIZE)]

    await worker._process_batch([_PendingRequest(_event(9999))])

    assert len(worker._pending_requests) == MAX_QUEUE_SIZE  # did not grow
    assert worker._total_dropped == 1


@pytest.mark.asyncio
async def test_storage_failure_is_not_requeued():
    """Neo4j-side storage failures are logged and counted, not retried."""
    service = _service()
    service.store_embedding_with_metadata = AsyncMock(
        return_value=Result.fail(Errors.not_found(resource="Node", identifier="Task:gone"))
    )
    worker = _worker(service)

    await worker._process_batch([_PendingRequest(_event(0))])

    assert worker._pending_requests == []
    assert worker._total_success == 0
    assert worker._total_failed == 1


@pytest.mark.asyncio
async def test_chunk_request_drops_after_attempt_cap():
    """Chunk requests get the same bounded policy, per parent."""
    service = _service()
    service.model = "test-embedder"
    service.create_batch_embeddings = AsyncMock(
        return_value=Result.fail(Errors.integration(service="OpenAI", message="always fails"))
    )
    worker = _worker(service)
    worker.content_adapter = MagicMock()

    chunk_event = ChunkEmbeddingRequested(
        parent_uid="ps:test:one",
        chunk_uids=("chunk1", "chunk2"),
        chunk_texts=("a", "b"),
        requested_at=datetime.now(),
    )

    worker._pending_chunk_requests = [_PendingChunkRequest(chunk_event)]
    for _ in range(MAX_GENERATION_ATTEMPTS):
        batch = worker._pending_chunk_requests
        worker._pending_chunk_requests = []
        await worker._process_chunk_batch(batch)

    assert worker._pending_chunk_requests == []
    assert worker._total_dropped == 1


@pytest.mark.asyncio
async def test_chunk_batchmates_survive_one_bad_parent():
    """One failing parent re-queues alone; the other parent's chunks store and complete."""

    async def batch_embed(texts: list[str]) -> Result[list[list[float]]]:
        if "bad" in texts:
            return Result.fail(Errors.integration(service="OpenAI", message="boom"))
        return Result.ok([VECTOR for _ in texts])

    service = _service()
    service.model = "test-embedder"
    service.create_batch_embeddings = AsyncMock(side_effect=batch_embed)
    worker = _worker(service)
    worker.content_adapter = MagicMock()
    worker.content_adapter.store_chunk_embeddings = AsyncMock(return_value=True)

    good = ChunkEmbeddingRequested(
        parent_uid="ps:test:good",
        chunk_uids=("g1",),
        chunk_texts=("fine",),
        requested_at=datetime.now(),
    )
    bad = ChunkEmbeddingRequested(
        parent_uid="ps:test:bad",
        chunk_uids=("b1",),
        chunk_texts=("bad",),
        requested_at=datetime.now(),
    )

    await worker._process_chunk_batch([_PendingChunkRequest(bad), _PendingChunkRequest(good)])

    worker.content_adapter.store_chunk_embeddings.assert_awaited_once()
    assert len(worker._pending_chunk_requests) == 1
    assert worker._pending_chunk_requests[0].event.parent_uid == "ps:test:bad"
    assert worker._pending_chunk_requests[0].attempts == 1
