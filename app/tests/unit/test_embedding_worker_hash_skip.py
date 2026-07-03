"""
Unit tests for the EmbeddingBackgroundWorker's content-hash idempotency.

Force re-ingests publish an embedding event for every re-processed file,
changed or not — the worker must drop requests whose stored embedding already
matches the event text BEFORE any generation spend (a skip at store time
saves nothing). Covers:

- Entity batches: fresh requests never reach create_embedding; stale ones
  embed and store WITH their text (so the hash lands)
- Fail-open: a freshness pre-check error embeds the full batch
- Chunk batches: fresh chunks (stored embedding_source_text == event text,
  version current) are excluded from generation and storage; a fully fresh
  parent skips both calls entirely

The skip SEMANTICS (version outranks hash, timestamp touch) live in
EmbeddingsService.verify_fresh_embeddings and are covered by
test_embedding_versioning.py — here the service is mocked and the worker's
plumbing around it is under test.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events import ChunkEmbeddingRequested, TaskEmbeddingRequested
from core.services.background.embedding_worker import (
    EmbeddingBackgroundWorker,
    _PendingChunkRequest,
    _PendingRequest,
)
from core.services.embeddings_service import EMBEDDING_VERSION
from core.utils.result_simplified import Errors, Result

VECTOR = [0.1] * 1024


def _event(i: int, text: str | None = None) -> TaskEmbeddingRequested:
    return TaskEmbeddingRequested(
        entity_uid=f"task.test{i}",
        entity_type="task",
        embedding_text=text if text is not None else f"text {i}",
        requested_at=datetime.now(),
    )


def _service() -> MagicMock:
    service = MagicMock()
    service.model = "test-embedder"
    service.create_embedding = AsyncMock(return_value=Result.ok(VECTOR))
    service.create_batch_embeddings = AsyncMock(return_value=Result.ok([VECTOR]))
    service.store_embedding_with_metadata = AsyncMock(return_value=Result.ok(None))
    service.verify_fresh_embeddings = AsyncMock(return_value=Result.ok(set()))
    return service


def _worker(service: MagicMock) -> EmbeddingBackgroundWorker:
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    return EmbeddingBackgroundWorker(
        event_bus=bus,
        embeddings_service=service,
        batch_size=25,
        batch_interval_seconds=1,
    )


def _chunk_row(uid: str, text: str, **overrides) -> dict:
    row = {
        "uid": uid,
        "has_embedding": True,
        "version": EMBEDDING_VERSION,
        "source_text": text,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_fresh_request_never_reaches_generation():
    """Hash match → the request is dropped before create_embedding."""
    service = _service()
    service.verify_fresh_embeddings = AsyncMock(return_value=Result.ok({"task.test0"}))
    worker = _worker(service)

    await worker._process_batch([_PendingRequest(_event(0))])

    service.create_embedding.assert_not_awaited()
    service.store_embedding_with_metadata.assert_not_awaited()
    assert worker._total_skipped == 1
    assert worker.get_metrics()["total_skipped"] == 1


@pytest.mark.asyncio
async def test_mixed_batch_embeds_only_stale_requests():
    """Fresh batchmates skip; the stale one embeds and stores WITH its text."""
    service = _service()
    service.verify_fresh_embeddings = AsyncMock(
        return_value=Result.ok({"task.test0", "task.test2"})
    )
    worker = _worker(service)

    batch = [_PendingRequest(_event(i)) for i in range(3)]
    await worker._process_batch(batch)

    service.create_embedding.assert_awaited_once_with("text 1")
    service.store_embedding_with_metadata.assert_awaited_once_with(
        uid="task.test1", label="Task", embedding=VECTOR, text="text 1"
    )
    assert worker._total_skipped == 2
    assert worker._total_success == 1


@pytest.mark.asyncio
async def test_freshness_precheck_failure_fails_open():
    """A freshness-read error must never block embedding — full batch embeds."""
    service = _service()
    service.verify_fresh_embeddings = AsyncMock(
        return_value=Result.fail(Errors.database(operation="freshness", message="boom"))
    )
    worker = _worker(service)

    await worker._process_batch([_PendingRequest(_event(0)), _PendingRequest(_event(1))])

    assert service.create_embedding.await_count == 2
    assert worker._total_skipped == 0


@pytest.mark.asyncio
async def test_precheck_passes_event_texts_as_candidates():
    """The pre-check sees uid → event text, so the hash compares against what
    WOULD be embedded now."""
    service = _service()
    worker = _worker(service)

    await worker._process_batch([_PendingRequest(_event(0, "current text"))])

    service.verify_fresh_embeddings.assert_awaited_once_with({"task.test0": "current text"})


@pytest.mark.asyncio
async def test_conflicting_duplicate_uid_never_skips():
    """Two requests for one uid with DIFFERENT texts (bus dispatch may not
    match persistence order) → ambiguity fails open: the uid is excluded from
    the hash-check candidates and both requests embed."""
    service = _service()
    service.verify_fresh_embeddings = AsyncMock(return_value=Result.ok(set()))
    worker = _worker(service)

    batch = [
        _PendingRequest(_event(0, "old text")),
        _PendingRequest(_event(0, "new text")),
    ]
    await worker._process_batch(batch)

    service.verify_fresh_embeddings.assert_awaited_once_with({})
    assert service.create_embedding.await_count == 2
    assert worker._total_skipped == 0


@pytest.mark.asyncio
async def test_same_text_duplicate_uid_skips_both():
    """Two requests for one uid with the SAME text are unambiguous — a hash
    match drops both."""
    service = _service()
    service.verify_fresh_embeddings = AsyncMock(return_value=Result.ok({"task.test0"}))
    worker = _worker(service)

    batch = [
        _PendingRequest(_event(0, "same text")),
        _PendingRequest(_event(0, "same text")),
    ]
    await worker._process_batch(batch)

    service.verify_fresh_embeddings.assert_awaited_once_with({"task.test0": "same text"})
    service.create_embedding.assert_not_awaited()
    assert worker._total_skipped == 2


def _chunk_event(parent: str, uids: tuple, texts: tuple) -> ChunkEmbeddingRequested:
    return ChunkEmbeddingRequested(
        parent_uid=parent,
        chunk_uids=uids,
        chunk_texts=texts,
        requested_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_fully_fresh_parent_skips_generation_and_storage():
    """All chunks fresh (source text + version match) → no API call, no store."""
    service = _service()
    worker = _worker(service)
    adapter = MagicMock()
    adapter.store_chunk_embeddings = AsyncMock(return_value=True)
    adapter.get_chunk_embedding_freshness = AsyncMock(
        return_value=[_chunk_row("c1", "alpha"), _chunk_row("c2", "beta")]
    )
    worker.content_adapter = adapter

    event = _chunk_event("ps:test:one", ("c1", "c2"), ("alpha", "beta"))
    await worker._process_chunk_batch([_PendingChunkRequest(event)])

    service.create_batch_embeddings.assert_not_awaited()
    adapter.store_chunk_embeddings.assert_not_awaited()
    assert worker._total_skipped == 2
    assert worker._pending_chunk_requests == []


@pytest.mark.asyncio
async def test_partially_fresh_parent_embeds_only_changed_chunks():
    """One changed chunk embeds alone; the fresh one is excluded from storage."""
    service = _service()
    worker = _worker(service)
    adapter = MagicMock()
    adapter.store_chunk_embeddings = AsyncMock(return_value=True)
    adapter.get_chunk_embedding_freshness = AsyncMock(
        return_value=[_chunk_row("c1", "alpha"), _chunk_row("c2", "OLD beta")]
    )
    worker.content_adapter = adapter

    event = _chunk_event("ps:test:one", ("c1", "c2"), ("alpha", "beta"))
    await worker._process_chunk_batch([_PendingChunkRequest(event)])

    service.create_batch_embeddings.assert_awaited_once_with(["beta"])
    adapter.store_chunk_embeddings.assert_awaited_once_with(
        chunk_uids=["c2"],
        embeddings=[VECTOR],
        version=EMBEDDING_VERSION,
        model="test-embedder",
        texts=["beta"],
    )
    assert worker._total_skipped == 1


@pytest.mark.asyncio
async def test_chunk_version_mismatch_reembeds_despite_text_match():
    """Version outranks the text match — a model migration re-embeds chunks."""
    service = _service()
    worker = _worker(service)
    adapter = MagicMock()
    adapter.store_chunk_embeddings = AsyncMock(return_value=True)
    adapter.get_chunk_embedding_freshness = AsyncMock(
        return_value=[_chunk_row("c1", "alpha", version="v2")]
    )
    worker.content_adapter = adapter

    event = _chunk_event("ps:test:one", ("c1",), ("alpha",))
    await worker._process_chunk_batch([_PendingChunkRequest(event)])

    service.create_batch_embeddings.assert_awaited_once_with(["alpha"])
    assert worker._total_skipped == 0


@pytest.mark.asyncio
async def test_chunk_freshness_read_failure_fails_open():
    """Adapter returns no rows on failure → nothing skipped, all embed."""
    service = _service()
    service.create_batch_embeddings = AsyncMock(return_value=Result.ok([VECTOR, VECTOR]))
    worker = _worker(service)
    adapter = MagicMock()
    adapter.store_chunk_embeddings = AsyncMock(return_value=True)
    adapter.get_chunk_embedding_freshness = AsyncMock(return_value=[])
    worker.content_adapter = adapter

    event = _chunk_event("ps:test:one", ("c1", "c2"), ("alpha", "beta"))
    await worker._process_chunk_batch([_PendingChunkRequest(event)])

    service.create_batch_embeddings.assert_awaited_once_with(["alpha", "beta"])
    assert worker._total_skipped == 0
