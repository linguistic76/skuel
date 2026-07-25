"""
Background Embedding Worker
============================

Listens for EmbeddingRequested events and generates embeddings in batches.

Architecture:
- Event-driven: Subscribes to all *EmbeddingRequested events
- Batch processing: Processes entities in groups every 30-60s
- Zero latency impact: User creation returns immediately
- Graceful degradation: Errors don't block entity creation
- Content-hash idempotency (ADR-074 §8): stored embedding_text_hash (entities)
  / embedding_source_text (chunks) is checked BEFORE generation — unchanged
  text is skipped, so force re-ingests don't re-embed the corpus. Fails OPEN.

Performance:
- Batch size: 25 entities per batch
- Interval: 30 seconds between batches
- Concurrency: items in a batch embed concurrently (the inference clients
  are single-text, so "batching" is concurrency, not a batch endpoint)

Retry policy (bounded — no infinite loops):
- Generation failures are PER ITEM: one poison text never fails its batchmates
- Each request retries up to MAX_GENERATION_ATTEMPTS, then is dropped with an
  error log (and a Prometheus `status="dropped"` count)
- Re-queueing respects MAX_QUEUE_SIZE; overflow drops instead of growing
- Storage failures (Neo4j-side) are not re-queued — they are logged and counted

Implementation:
- Queue pending requests in memory (wrapped with an attempt counter)
- Process batches on timer (asyncio.sleep loop)
- Update Neo4j nodes with embeddings
- Log success/failures for debugging

Two run modes:
- App process: start() — subscribe + timer loop (dev bootstrap background task)
- Script process: subscribe() before the sync, then drain() once after — so a
  one-shot sync's embedding events are processed in-process instead of
  evaporating with the script (ADR-074 script-mode freshness)
"""

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.models.type_hints import EntityUID

if TYPE_CHECKING:
    from datetime import datetime

    from core.services.embeddings_service import EmbeddingsService

from core.events import (
    ChoiceEmbeddingRequested,
    ChunkEmbeddingRequested,
    EventEmbeddingRequested,
    ExerciseEmbeddingRequested,
    GoalEmbeddingRequested,
    HabitEmbeddingRequested,
    KuEmbeddingRequested,
    LearningPathEmbeddingRequested,
    PathStepEmbeddingRequested,
    PrincipleEmbeddingRequested,
    ReferenceChunkEmbeddingRequested,
    ResourceEmbeddingRequested,
    RevisedExerciseEmbeddingRequested,
    TaskEmbeddingRequested,
    UserEntryEmbeddingRequested,
)
from core.events.embedding_events import EmbeddingRequested
from core.ports.infrastructure_protocols import EventBusOperations
from core.services.embeddings_service import EMBEDDING_VERSION
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

_EMBEDDING_EXCEPTIONS = (*NEO4J_EXCEPTIONS, ConnectionError, TimeoutError)

# Generation attempts per request before the worker gives up on it.
MAX_GENERATION_ATTEMPTS = 5
# Re-queue overflow guard — beyond this, failed requests drop instead of growing the queue.
MAX_QUEUE_SIZE = 1000


@dataclass
class _PendingRequest:
    """A queued entity-embedding request with its retry budget."""

    event: EmbeddingRequested
    attempts: int = field(default=0)


@dataclass
class _PendingChunkRequest:
    """A queued chunk-embedding request with its retry budget.

    Carries either a curriculum ``ChunkEmbeddingRequested`` or a canon
    ``ReferenceChunkEmbeddingRequested`` — the batch selects the matching
    adapter per request by the event's concrete type.
    """

    event: ChunkEmbeddingRequested | ReferenceChunkEmbeddingRequested
    attempts: int = field(default=0)


class EmbeddingBackgroundWorker:
    """
    Background worker that listens for embedding events and processes in batches.

    Zero-latency async embedding generation for all activity domains.

    Metrics Tracking:
    - Total entities processed
    - Success/failure counts
    - Average batch size
    - Processing time per batch
    """

    def __init__(
        self,
        event_bus: EventBusOperations,
        embeddings_service: "EmbeddingsService",
        content_adapter: Any | None = None,  # Neo4jContentAdapter for chunk storage
        reference_chunk_adapter: Any | None = None,  # Neo4jReferenceChunkAdapter for canon chunks
        batch_size: int = 25,
        batch_interval_seconds: int = 30,
        prometheus_metrics: Any | None = None,  # PrometheusMetrics for real-time instrumentation
    ) -> None:
        """
        Initialize background worker.

        Args:
            event_bus: Event bus for subscribing to embedding requests
            embeddings_service: EmbeddingsService for generating + storing embeddings
                (owns version/model metadata — the worker never writes those itself)
            content_adapter: Neo4jContentAdapter for chunk embedding storage (optional)
            reference_chunk_adapter: Neo4jReferenceChunkAdapter for canon
                reference-chunk embedding storage (optional; parallel to
                content_adapter, selected by event type)
            batch_size: Number of entities to process per batch
            batch_interval_seconds: Seconds between batch processing runs
            prometheus_metrics: PrometheusMetrics for exposing metrics
        """
        self.event_bus = event_bus
        self.embeddings_service = embeddings_service
        self.content_adapter = content_adapter
        self.reference_chunk_adapter = reference_chunk_adapter
        self.batch_size = batch_size
        self.batch_interval = batch_interval_seconds
        self.prometheus_metrics = prometheus_metrics
        self._pending_requests: list[_PendingRequest] = []
        self._pending_chunk_requests: list[_PendingChunkRequest] = []
        self.logger = get_logger("skuel.background.embeddings")
        self._queue_lock: asyncio.Lock = asyncio.Lock()

        # Internal counters behind get_metrics() (unit-test introspection);
        # the external surface is Prometheus (skuel_embedding_* series).
        self._total_processed = 0
        self._total_success = 0
        self._total_failed = 0
        self._total_dropped = 0
        self._total_skipped = 0
        self._batches_processed = 0
        self._started_at: datetime | None = None

    def subscribe(self) -> None:
        """
        Register this worker's queue callbacks on the event bus.

        Split from ``start()`` so one-shot script callers (``vault_bridge_sync``)
        can subscribe BEFORE their sync publishes embedding events, then
        ``drain()`` the queues once — without the timer loop. In the app process,
        ``start()`` calls this and then loops.
        """
        # Subscribe to all embedding request events — Activity domains
        self.event_bus.subscribe(TaskEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(GoalEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(HabitEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(EventEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(ChoiceEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(PrincipleEmbeddingRequested, self._queue_request)

        # Subscribe to all embedding request events — Curriculum types
        self.event_bus.subscribe(KuEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(ResourceEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(ExerciseEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(PathStepEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(LearningPathEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(RevisedExerciseEmbeddingRequested, self._queue_request)

        # UserEntry — pipeline-scoped at the publisher (UserEntryService gates
        # on pipeline=knowledge), so everything that arrives here embeds.
        self.event_bus.subscribe(UserEntryEmbeddingRequested, self._queue_request)

        # Subscribe to chunk embedding requests (separate queue). Both the
        # curriculum and canon reference variants share the queue and the
        # _PendingChunkRequest wrapper — the batch routes each to its adapter
        # by event type.
        self.event_bus.subscribe(ChunkEmbeddingRequested, self._queue_chunk_request)
        self.event_bus.subscribe(ReferenceChunkEmbeddingRequested, self._queue_chunk_request)

    async def start(self) -> Result[None]:
        """
        Start listening for embedding events.

        Subscribes to all domain embedding request events and starts batch processing loop.
        """
        self.subscribe()

        # Track start time for metrics
        from datetime import datetime

        self._started_at = datetime.now()

        self.logger.info(
            f"🔄 Embedding background worker started (batch_size={self.batch_size}, "
            f"interval={self.batch_interval}s)"
        )

        # Start batch processing loop
        await self._process_batches_loop()
        return Result.ok(None)

    async def drain(  # skuel-lint: disable=SKUEL005 -- script-mode drain returns processed counts; failures re-queue with bounded retries (fail-soft worker)
        self,
    ) -> dict[str, int]:
        """
        Process both queues until empty, once — no timer loop.

        The script-mode counterpart to ``start()`` (ADR-074 script-mode
        freshness): a one-shot sync (``vault_bridge_sync``) calls
        ``subscribe()`` before ingesting, then drains after, so the embedding
        events its ingest published are processed in the same process instead
        of evaporating when the script exits. Terminates: per-request retries
        are bounded by MAX_GENERATION_ATTEMPTS, so re-queued failures cannot
        loop forever.

        Returns:
            Counts of dequeued work: ``entity_requests`` and ``chunk_parents``
            (bounded retries re-dequeue, so counts include retry passes).
        """
        entity_requests = 0
        chunk_parents = 0
        while self._pending_requests or self._pending_chunk_requests:
            if self._pending_requests:
                batch = await self._dequeue_entity_batch()
                entity_requests += len(batch)
                await self._process_batch(batch)
            if self._pending_chunk_requests:
                chunk_batch = await self._dequeue_chunk_batch()
                chunk_parents += len(chunk_batch)
                await self._process_chunk_batch(chunk_batch)
        return {"entity_requests": entity_requests, "chunk_parents": chunk_parents}

    async def _queue_request(self, event: EmbeddingRequested) -> None:
        """
        Add embedding request to pending queue.

        Args:
            event: EmbeddingRequested event from entity creation
        """
        async with self._queue_lock:
            self._pending_requests.append(_PendingRequest(event))
        self.logger.debug(
            f"Queued embedding request for {event.entity_type} {event.entity_uid} "
            f"(queue size: {len(self._pending_requests)})"
        )

    async def _queue_chunk_request(
        self, event: ChunkEmbeddingRequested | ReferenceChunkEmbeddingRequested
    ) -> None:
        """
        Add chunk embedding request to pending queue.

        Args:
            event: ChunkEmbeddingRequested (curriculum) or
                ReferenceChunkEmbeddingRequested (canon) event from ingestion or
                regeneration
        """
        async with self._queue_lock:
            self._pending_chunk_requests.append(_PendingChunkRequest(event))
        self.logger.debug(
            f"Queued chunk embedding request for {event.parent_uid} "
            f"({len(event.chunk_uids)} chunks, queue size: {len(self._pending_chunk_requests)})"
        )

    async def _dequeue_entity_batch(self) -> list[_PendingRequest]:
        """Slice up to batch_size entity requests off the queue, under the lock."""
        async with self._queue_lock:
            batch = self._pending_requests[: self.batch_size]
            self._pending_requests = self._pending_requests[self.batch_size :]
        return batch

    async def _dequeue_chunk_batch(self) -> list[_PendingChunkRequest]:
        """Slice up to batch_size chunk requests off the queue, under the lock."""
        async with self._queue_lock:
            batch = self._pending_chunk_requests[: self.batch_size]
            self._pending_chunk_requests = self._pending_chunk_requests[self.batch_size :]
        return batch

    async def _process_batches_loop(self) -> None:
        """
        Process pending embedding requests in batches every N seconds.

        Infinite loop that runs batch processing at regular intervals.
        Processes both entity embeddings and chunk embeddings.

        Exposes queue sizes to Prometheus in real-time.
        """
        while True:
            await asyncio.sleep(self.batch_interval)

            # Update Prometheus queue size gauges
            if self.prometheus_metrics:
                self.prometheus_metrics.ai.embedding_queue_size.labels(queue_type="entity").set(
                    len(self._pending_requests)
                )

                self.prometheus_metrics.ai.embedding_queue_size.labels(queue_type="chunk").set(
                    len(self._pending_chunk_requests)
                )

            # Process entity embeddings
            if self._pending_requests:
                batch = await self._dequeue_entity_batch()

                self.logger.info(
                    f"Processing batch of {len(batch)} embedding requests "
                    f"({len(self._pending_requests)} remaining in queue)"
                )

                await self._process_batch(batch)

            # Process chunk embeddings
            if self._pending_chunk_requests:
                chunk_batch = await self._dequeue_chunk_batch()

                self.logger.info(
                    f"Processing batch of {len(chunk_batch)} chunk embedding requests "
                    f"({len(self._pending_chunk_requests)} remaining in queue)"
                )

                await self._process_chunk_batch(chunk_batch)

    async def _process_batch(self, batch: list[_PendingRequest]) -> None:
        """
        Generate and store embeddings for a batch, per item.

        Items embed concurrently but succeed or fail INDIVIDUALLY — one poison
        text re-queues (or drops) alone instead of failing its batchmates.
        Generation failures go through _retry_or_drop (bounded retries);
        storage failures are logged and counted but not re-queued.

        Args:
            batch: Pending requests sliced off the queue by the timer loop
        """
        import time

        batch_start = time.time()

        try:
            # Content-hash idempotency: drop requests whose stored embedding
            # already matches the event text BEFORE any generation spend — force
            # re-ingests publish for every re-processed file, changed or not.
            # Inside the safety net: an unexpected raise here (fail-open covers
            # Result errors, not bugs) must not kill the timer loop.
            batch = await self._drop_fresh_requests(batch)
            if not batch:
                return

            # Concurrent per-item generation; exceptions are captured per item
            # so a raising call degrades exactly like a Result failure.
            results = await asyncio.gather(
                *(self.embeddings_service.create_embedding(p.event.embedding_text) for p in batch),
                return_exceptions=True,
            )

            success_count = 0
            entity_type_stats: dict[str, dict[str, int]] = {}

            for pending, result in zip(batch, results, strict=True):
                event = pending.event
                stats = entity_type_stats.setdefault(
                    event.entity_type, {"success": 0, "failed": 0, "dropped": 0}
                )

                if isinstance(result, BaseException):
                    self.logger.warning(
                        f"Embedding generation raised for {event.entity_type} "
                        f"{event.entity_uid}: {result}"
                    )
                    self._retry_or_drop(pending, stats)
                    continue

                if result.is_error:
                    self.logger.warning(
                        f"Embedding generation failed for {event.entity_type} "
                        f"{event.entity_uid}: {result.expect_error().message}"
                    )
                    self._retry_or_drop(pending, stats)
                    continue

                stored = await self._store_embedding(
                    event.entity_uid, event.entity_type, result.value, event.embedding_text
                )
                if stored:
                    success_count += 1
                    stats["success"] += 1
                else:
                    # Neo4j-side failure: logged in _store_embedding, not re-queued
                    stats["failed"] += 1

            # Track internal metrics (backward compatibility)
            failed_count = len(batch) - success_count
            self._total_processed += len(batch)
            self._total_success += success_count
            self._total_failed += failed_count
            self._batches_processed += 1

            # Track Prometheus metrics
            if self.prometheus_metrics:
                # Per-entity-type counters
                for entity_type, stats in entity_type_stats.items():
                    for status in ("success", "failed", "dropped"):
                        if stats[status] > 0:
                            self.prometheus_metrics.ai.embeddings_processed_total.labels(
                                entity_type=entity_type, status=status
                            ).inc(stats[status])

                # Batch size histogram
                self.prometheus_metrics.ai.embedding_batch_size.observe(len(batch))

            batch_duration = time.time() - batch_start

            self.logger.info(
                f"✅ Generated {success_count}/{len(batch)} embeddings successfully "
                f"(took {batch_duration:.2f}s, total: {self._total_success}/{self._total_processed})"
            )

        except Exception as e:  # safety-net: a bug here must not kill the timer loop
            self.logger.error(f"Batch processing exception: {e}")
            self._total_failed += len(batch)
            for pending in batch:
                self._retry_or_drop(pending, {"failed": 0, "dropped": 0})

    async def _drop_fresh_requests(self, batch: list[_PendingRequest]) -> list[_PendingRequest]:
        """
        Drop requests whose stored embedding already matches the event text.

        One batched freshness read (EmbeddingsService.verify_fresh_embeddings
        owns the skip semantics — version-current + text-hash match, with the
        timestamp touch); the skip sits BEFORE generation because a skip at
        store time saves nothing. Fails OPEN: a freshness-read error embeds
        the full batch — correctness over savings. Same fail-open rule for a
        uid queued with CONFLICTING texts in one batch (two updates whose bus
        dispatch may not match persistence order): ambiguity never skips —
        only uids with exactly one distinct text are hash-check candidates.
        """
        texts_by_uid: dict[str, set[str]] = {}
        for pending in batch:
            texts_by_uid.setdefault(pending.event.entity_uid, set()).add(
                pending.event.embedding_text
            )
        candidates: dict[str, str] = {
            uid: next(iter(texts)) for uid, texts in texts_by_uid.items() if len(texts) == 1
        }
        fresh_result = await self.embeddings_service.verify_fresh_embeddings(candidates)
        if fresh_result.is_error:
            self.logger.warning(
                f"Embedding freshness pre-check failed — embedding full batch: "
                f"{fresh_result.expect_error().message}"
            )
            return batch

        fresh = fresh_result.value
        if not fresh:
            return batch

        kept = [p for p in batch if p.event.entity_uid not in fresh]
        skipped = len(batch) - len(kept)
        self._total_skipped += skipped

        if self.prometheus_metrics:
            skipped_by_type: dict[str, int] = {}
            for p in batch:
                if p.event.entity_uid in fresh:
                    skipped_by_type[p.event.entity_type] = (
                        skipped_by_type.get(p.event.entity_type, 0) + 1
                    )
            for entity_type, count in skipped_by_type.items():
                self.prometheus_metrics.ai.embeddings_processed_total.labels(
                    entity_type=entity_type, status="skipped"
                ).inc(count)

        self.logger.info(
            f"⏭️ Skipped {skipped}/{len(batch)} embedding requests (text unchanged — "
            f"hash match, total skipped: {self._total_skipped})"
        )
        return kept

    def _retry_or_drop(self, pending: _PendingRequest, stats: dict[str, int]) -> None:
        """Spend one retry attempt: re-queue the request, or drop it at the caps.

        Drops when the attempt budget (MAX_GENERATION_ATTEMPTS) is exhausted or
        the queue is at MAX_QUEUE_SIZE — a persistently failing request must
        not retry forever, and a full queue must not grow unbounded.
        """
        event = pending.event
        pending.attempts += 1
        stats["failed"] = stats.get("failed", 0) + 1

        if pending.attempts >= MAX_GENERATION_ATTEMPTS:
            self._total_dropped += 1
            stats["dropped"] = stats.get("dropped", 0) + 1
            self.logger.error(
                f"🗑️ Dropping embedding request for {event.entity_type} {event.entity_uid} "
                f"after {pending.attempts} failed attempts"
            )
        elif len(self._pending_requests) >= MAX_QUEUE_SIZE:
            self._total_dropped += 1
            stats["dropped"] = stats.get("dropped", 0) + 1
            self.logger.error(
                f"🗑️ Queue full ({MAX_QUEUE_SIZE}) — dropping embedding request for "
                f"{event.entity_type} {event.entity_uid}"
            )
        else:
            self._pending_requests.append(pending)
            self.logger.debug(
                f"Re-queued embedding request for {event.entity_type} {event.entity_uid} "
                f"(attempt {pending.attempts}/{MAX_GENERATION_ATTEMPTS})"
            )

    async def _store_embedding(
        self, entity_uid: EntityUID, entity_type: str, embedding: list[float], text: str
    ) -> bool:
        """
        Store embedding in Neo4j node with version tracking.

        Args:
            entity_uid: UID of entity
            entity_type: Type of entity (task, goal, etc.)
            embedding: Embedding vector
            text: The embedded text (the service hashes it for freshness checks)

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            # Resolve the Neo4j label through the one shared map (the events
            # carry EntityType.value strings). Fallback mirrors the old local
            # map's behavior for any string that isn't a known EntityType.
            from core.events.embedding_publisher import EMBEDDING_NODE_LABELS
            from core.models.enums.entity_enums import EntityType

            entity_type_enum = EntityType.from_string(entity_type)
            label = (
                EMBEDDING_NODE_LABELS.get(entity_type_enum, entity_type.capitalize())
                if entity_type_enum
                else entity_type.capitalize()
            )

            # Storage goes through the service — it owns label validation and
            # the version/model metadata (single source of truth).
            result = await self.embeddings_service.store_embedding_with_metadata(
                uid=entity_uid,
                label=label,
                embedding=embedding,
                text=text,
            )

            if result.is_error:
                self.logger.warning(
                    f"Failed to store embedding for {entity_type} {entity_uid}: "
                    f"{result.expect_error().message}"
                )
                return False

            self.logger.debug(f"Stored embedding for {entity_type} {entity_uid}")
            return True

        except _EMBEDDING_EXCEPTIONS as e:
            self.logger.error(f"Failed to store embedding for {entity_uid}: {e}")
            return False
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Failed to store embedding for {entity_uid}: {e}")
            return False

    async def _process_chunk_batch(self, batch: list[_PendingChunkRequest]) -> None:
        """
        Generate embeddings for a batch of chunk requests, per request.

        Each request carries all chunks of one parent and succeeds or fails
        as a unit (chunk storage is an all-chunks-of-parent write), but
        requests fail INDIVIDUALLY — one bad parent re-queues (or drops)
        alone via _retry_or_drop_chunks instead of failing its batchmates.

        Args:
            batch: Pending chunk requests sliced off the queue by the timer loop
        """
        import time

        batch_start = time.time()
        total_chunks = sum(len(p.event.chunk_uids) for p in batch)
        self.logger.info(f"Processing {total_chunks} chunks from {len(batch)} parents")

        success_chunks = 0
        skipped_chunks = 0
        for pending in batch:
            event = pending.event
            try:
                # Route to the adapter matching the event kind: canon reference
                # chunks land on :ReferenceChunk (own index), curriculum chunks
                # on :ContentChunk. Both adapters expose the same method names,
                # so this is a one-object swap. A missing adapter (tier/wiring)
                # skips just this parent, not the batch.
                adapter = (
                    self.reference_chunk_adapter
                    if isinstance(event, ReferenceChunkEmbeddingRequested)
                    else self.content_adapter
                )
                if adapter is None:
                    self.logger.warning(
                        f"No chunk adapter configured for {type(event).__name__} — "
                        f"skipping parent {event.parent_uid}"
                    )
                    continue

                # Content idempotency: a force re-chunk of an unchanged body
                # recreates identical chunks with their embeddings preserved
                # (store_*_chunks) but still publishes an event — skip the
                # chunks whose stored source text matches BEFORE generation.
                pairs = list(zip(event.chunk_uids, event.chunk_texts, strict=True))
                fresh = await self._fresh_chunk_uids(pairs, adapter)
                todo = [(uid, text) for uid, text in pairs if uid not in fresh]
                if fresh:
                    skipped_chunks += len(fresh)
                    self._total_skipped += len(fresh)
                if not todo:
                    self.logger.debug(
                        f"All {len(pairs)} chunks fresh for parent {event.parent_uid} — skipped"
                    )
                    continue

                embeddings_result = await self.embeddings_service.create_batch_embeddings(
                    [text for _, text in todo]
                )

                if embeddings_result.is_error:
                    self.logger.warning(
                        f"Chunk embedding generation failed for parent {event.parent_uid}: "
                        f"{embeddings_result.expect_error().message}"
                    )
                    self._retry_or_drop_chunks(pending)
                    continue

                stored = await adapter.store_chunk_embeddings(
                    chunk_uids=[uid for uid, _ in todo],
                    embeddings=embeddings_result.value,
                    version=EMBEDDING_VERSION,
                    model=self.embeddings_service.model,
                    texts=[text for _, text in todo],
                )

                if not stored:
                    self.logger.warning(
                        f"Failed to store chunk embeddings for parent {event.parent_uid}"
                    )
                    self._retry_or_drop_chunks(pending)
                    continue

                success_chunks += len(todo)

            except Exception as e:  # safety-net: one parent's bug must not kill the loop
                self.logger.error(f"Chunk processing exception for parent {event.parent_uid}: {e}")
                self._retry_or_drop_chunks(pending)

        batch_duration = time.time() - batch_start
        self.logger.info(
            f"✅ Generated {success_chunks}/{total_chunks} chunk embeddings "
            f"({skipped_chunks} skipped: text unchanged; took {batch_duration:.2f}s)"
        )

    async def _fresh_chunk_uids(self, pairs: list[tuple[str, str]], adapter: Any) -> set[str]:
        """
        Chunk uids whose stored embedding already covers the event's text.

        Fresh = embedding present, version current, and the stored
        ``embedding_source_text`` (written by store_chunk_embeddings at embed
        time) equals the event's context window — chunks compare raw text, no
        hash field needed. Version outranks the text match, so a model
        migration re-embeds every chunk. Fails OPEN: the adapter returns no
        rows on a read failure, so nothing is skipped.

        Args:
            pairs: (chunk_uid, context_window_text) pairs from the event
            adapter: the chunk adapter selected for this event kind
                (content or reference) — same freshness contract on both
        """
        if adapter is None:  # _process_chunk_batch already skipped; belt for direct callers
            return set()
        rows = await adapter.get_chunk_embedding_freshness([uid for uid, _ in pairs])
        by_uid = {row["uid"]: row for row in rows}
        fresh: set[str] = set()
        for uid, text in pairs:
            row = by_uid.get(uid)
            if (
                row
                and row.get("has_embedding")
                and row.get("version") == EMBEDDING_VERSION
                and row.get("source_text") == text
            ):
                fresh.add(uid)
        return fresh

    def _retry_or_drop_chunks(self, pending: _PendingChunkRequest) -> None:
        """Spend one retry attempt on a chunk request; drop at the caps.

        Same bounded-retry policy as _retry_or_drop, on the chunk queue.
        """
        pending.attempts += 1

        if pending.attempts >= MAX_GENERATION_ATTEMPTS:
            self._total_dropped += 1
            self.logger.error(
                f"🗑️ Dropping chunk embedding request for parent {pending.event.parent_uid} "
                f"({len(pending.event.chunk_uids)} chunks) after {pending.attempts} failed attempts"
            )
        elif len(self._pending_chunk_requests) >= MAX_QUEUE_SIZE:
            self._total_dropped += 1
            self.logger.error(
                f"🗑️ Chunk queue full ({MAX_QUEUE_SIZE}) — dropping request for parent "
                f"{pending.event.parent_uid}"
            )
        else:
            self._pending_chunk_requests.append(pending)
            self.logger.debug(
                f"Re-queued chunk embedding request for parent {pending.event.parent_uid} "
                f"(attempt {pending.attempts}/{MAX_GENERATION_ATTEMPTS})"
            )

    def get_metrics(self) -> dict[str, Any]:
        """
        Get worker performance metrics.

        Returns:
            Dictionary with worker statistics:
            - total_processed: Total entities processed
            - total_success: Successfully embedded entities
            - total_failed: Failed embedding attempts (retried ones count per attempt)
            - total_dropped: Requests abandoned after exhausting retries (or queue overflow)
            - total_skipped: Requests/chunks skipped pre-generation (stored embedding
              already matches the text — content-hash idempotency)
            - batches_processed: Number of batches processed
            - queue_size: Current pending requests count
            - chunk_queue_size: Current pending chunk requests count
            - uptime_seconds: Worker uptime in seconds
            - success_rate: Percentage of successful embeddings
            - avg_batch_size: Average entities per batch
        """
        from datetime import datetime

        uptime = (datetime.now() - self._started_at).total_seconds() if self._started_at else 0

        success_rate = (
            (self._total_success / self._total_processed * 100)
            if self._total_processed > 0
            else 0.0
        )

        avg_batch = (
            (self._total_processed / self._batches_processed)
            if self._batches_processed > 0
            else 0.0
        )

        return {
            "total_processed": self._total_processed,
            "total_success": self._total_success,
            "total_failed": self._total_failed,
            "total_dropped": self._total_dropped,
            "total_skipped": self._total_skipped,
            "batches_processed": self._batches_processed,
            "queue_size": len(self._pending_requests),
            "chunk_queue_size": len(self._pending_chunk_requests),
            "uptime_seconds": uptime,
            "success_rate": round(success_rate, 2),
            "avg_batch_size": round(avg_batch, 2),
        }
