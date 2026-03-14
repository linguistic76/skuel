"""
Background Embedding Worker
============================

Listens for EmbeddingRequested events and generates embeddings in batches.

Architecture:
- Event-driven: Subscribes to all *EmbeddingRequested events
- Batch processing: Processes entities in groups every 30-60s
- Zero latency impact: User creation returns immediately
- Graceful degradation: Errors don't block entity creation

Performance:
- Batch size: 25 entities per batch
- Interval: 30 seconds between batches
- API efficiency: Batch embedding calls reduce costs

Implementation:
- Queue pending requests in memory
- Process batches on timer (asyncio.sleep loop)
- Update Neo4j nodes with embeddings
- Log success/failures for debugging
"""

import asyncio
from typing import Any

from core.events import (
    LessonEmbeddingRequested,
    ChoiceEmbeddingRequested,
    ChunkEmbeddingRequested,
    ChunkEmbeddingsCompleted,
    EventEmbeddingRequested,
    ExerciseEmbeddingRequested,
    GoalEmbeddingRequested,
    HabitEmbeddingRequested,
    KuEmbeddingRequested,
    LearningPathEmbeddingRequested,
    LearningStepEmbeddingRequested,
    PrincipleEmbeddingRequested,
    ResourceEmbeddingRequested,
    RevisedExerciseEmbeddingRequested,
    TaskEmbeddingRequested,
    publish_event,
)
from core.events.embedding_events import EmbeddingRequested
from core.ports.infrastructure_protocols import EventBusOperations
from core.utils.logging import get_logger
from core.utils.result_simplified import Result


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
        embeddings_service: Any,  # HuggingFaceEmbeddingsService
        executor: Any,  # QueryExecutor
        config: Any,  # UnifiedConfig for embedding version
        content_adapter: Any | None = None,  # Neo4jContentAdapter for chunk storage
        batch_size: int = 25,
        batch_interval_seconds: int = 30,
        prometheus_metrics: Any | None = None,  # PrometheusMetrics for real-time instrumentation
    ) -> None:
        """
        Initialize background worker.

        Args:
            event_bus: Event bus for subscribing to embedding requests
            embeddings_service: HuggingFaceEmbeddingsService for generating embeddings
            executor: Query executor for updating nodes
            config: UnifiedConfig for accessing embedding version
            content_adapter: Neo4jContentAdapter for chunk embedding storage (optional)
            batch_size: Number of entities to process per batch
            batch_interval_seconds: Seconds between batch processing runs
            prometheus_metrics: PrometheusMetrics for exposing metrics
        """
        self.event_bus = event_bus
        self.embeddings_service = embeddings_service
        self.executor = executor
        self.config = config
        self.content_adapter = content_adapter
        self.batch_size = batch_size
        self.batch_interval = batch_interval_seconds
        self.prometheus_metrics = prometheus_metrics
        self._pending_requests: list[EmbeddingRequested] = []
        self._pending_chunk_requests: list[ChunkEmbeddingRequested] = []
        self.logger = get_logger("skuel.background.embeddings")

        # Internal metrics (kept for backward compatibility with /api/monitoring endpoint)
        self._total_processed = 0
        self._total_success = 0
        self._total_failed = 0
        self._batches_processed = 0
        self._started_at = None

    async def start(self) -> Result[None]:
        """
        Start listening for embedding events.

        Subscribes to all domain embedding request events and starts batch processing loop.
        """
        # Subscribe to all embedding request events — Activity domains
        self.event_bus.subscribe(TaskEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(GoalEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(HabitEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(EventEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(ChoiceEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(PrincipleEmbeddingRequested, self._queue_request)

        # Subscribe to all embedding request events — Curriculum types
        self.event_bus.subscribe(LessonEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(KuEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(ResourceEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(ExerciseEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(LearningStepEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(LearningPathEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(RevisedExerciseEmbeddingRequested, self._queue_request)

        # Subscribe to chunk embedding requests (separate queue)
        self.event_bus.subscribe(ChunkEmbeddingRequested, self._queue_chunk_request)

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

    async def _queue_request(self, event: EmbeddingRequested) -> None:
        """
        Add embedding request to pending queue.

        Args:
            event: EmbeddingRequested event from entity creation
        """
        self._pending_requests.append(event)
        self.logger.debug(
            f"Queued embedding request for {event.entity_type} {event.entity_uid} "
            f"(queue size: {len(self._pending_requests)})"
        )

    async def _queue_chunk_request(self, event: ChunkEmbeddingRequested) -> None:
        """
        Add chunk embedding request to pending queue.

        Args:
            event: ChunkEmbeddingRequested event from KU creation
        """
        self._pending_chunk_requests.append(event)
        self.logger.debug(
            f"Queued chunk embedding request for {event.ku_uid} "
            f"({len(event.chunk_uids)} chunks, queue size: {len(self._pending_chunk_requests)})"
        )

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
                batch = self._pending_requests[: self.batch_size]
                self._pending_requests = self._pending_requests[self.batch_size :]

                self.logger.info(
                    f"Processing batch of {len(batch)} embedding requests "
                    f"({len(self._pending_requests)} remaining in queue)"
                )

                await self._process_batch(batch)

            # Process chunk embeddings
            if self._pending_chunk_requests:
                chunk_batch = self._pending_chunk_requests[: self.batch_size]
                self._pending_chunk_requests = self._pending_chunk_requests[self.batch_size :]

                self.logger.info(
                    f"Processing batch of {len(chunk_batch)} chunk embedding requests "
                    f"({len(self._pending_chunk_requests)} remaining in queue)"
                )

                await self._process_chunk_batch(chunk_batch)

    async def _process_batch(self, requests: list[EmbeddingRequested]) -> None:
        """
        Generate embeddings for batch of entities.

        Args:
            requests: List of EmbeddingRequested events to process
        """
        import time

        batch_start = time.time()

        try:
            # Extract texts for batch embedding generation
            texts = [req.embedding_text for req in requests]

            # Generate embeddings in batch (more efficient than individual calls)
            embeddings_result = await self.embeddings_service.create_batch_embeddings(texts)

            if embeddings_result.is_error:
                self.logger.error(
                    f"Batch embedding generation failed: {embeddings_result.expect_error().message}"
                )
                # Track metrics
                self._total_failed += len(requests)
                # Re-queue requests for retry (simple retry logic)
                self._pending_requests.extend(requests)
                return

            embeddings = embeddings_result.value

            # Update each entity with its embedding
            success_count = 0
            entity_type_stats: dict[str, dict[str, int]] = {}

            for req, embedding in zip(requests, embeddings, strict=True):
                stored = await self._store_embedding(req.entity_uid, req.entity_type, embedding)

                # Track stats per entity type
                if req.entity_type not in entity_type_stats:
                    entity_type_stats[req.entity_type] = {"success": 0, "failed": 0}

                if stored:
                    success_count += 1
                    entity_type_stats[req.entity_type]["success"] += 1
                else:
                    entity_type_stats[req.entity_type]["failed"] += 1

            # Track internal metrics (backward compatibility)
            failed_count = len(requests) - success_count
            self._total_processed += len(requests)
            self._total_success += success_count
            self._total_failed += failed_count
            self._batches_processed += 1

            # Track Prometheus metrics
            if self.prometheus_metrics:
                # Per-entity-type counters
                for entity_type, stats in entity_type_stats.items():
                    if stats["success"] > 0:
                        self.prometheus_metrics.ai.embeddings_processed_total.labels(
                            entity_type=entity_type, status="success"
                        ).inc(stats["success"])

                    if stats["failed"] > 0:
                        self.prometheus_metrics.ai.embeddings_processed_total.labels(
                            entity_type=entity_type, status="failed"
                        ).inc(stats["failed"])

                # Batch size histogram
                self.prometheus_metrics.ai.embedding_batch_size.observe(len(requests))

            batch_duration = time.time() - batch_start

            self.logger.info(
                f"✅ Generated {success_count}/{len(requests)} embeddings successfully "
                f"(took {batch_duration:.2f}s, total: {self._total_success}/{self._total_processed})"
            )

        except Exception as e:
            self.logger.error(f"Batch processing exception: {e}")
            # Track metrics
            self._total_failed += len(requests)
            # Re-queue for retry (with limit to avoid infinite loops)
            if len(self._pending_requests) < 1000:  # Safety limit
                self._pending_requests.extend(requests)

    async def _store_embedding(
        self, entity_uid: str, entity_type: str, embedding: list[float]
    ) -> bool:
        """
        Store embedding in Neo4j node with version tracking.

        Args:
            entity_uid: UID of entity
            entity_type: Type of entity (task, goal, etc.)
            embedding: Embedding vector

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            # Map entity type to Neo4j label
            label_map = {
                "task": "Task",
                "goal": "Goal",
                "habit": "Habit",
                "event": "Event",
                "choice": "Choice",
                "principle": "Principle",
                "lesson": "Lesson",
                "ku": "Ku",
                "resource": "Resource",
                "exercise": "Exercise",
                "learning_step": "LearningStep",
                "learning_path": "LearningPath",
                "revised_exercise": "RevisedExercise",
            }
            label = label_map.get(entity_type, entity_type.capitalize())

            query = f"""
                MATCH (n:{label} {{uid: $uid}})
                SET n.embedding = $embedding,
                    n.embedding_version = $version,
                    n.embedding_model = $model,
                    n.embedding_updated_at = datetime()
                RETURN n.uid
            """

            result = await self.executor.execute_query(
                query,
                {
                    "uid": entity_uid,
                    "embedding": embedding,
                    "version": self.config.genai.embedding_version,
                    "model": self.embeddings_service.model,
                },
            )

            if result.is_error:
                self.logger.warning(
                    f"Failed to store embedding for {entity_type} {entity_uid}: {result.error}"
                )
                return False

            if result.value:
                self.logger.debug(f"Stored embedding for {entity_type} {entity_uid}")
                return True
            else:
                self.logger.warning(f"Entity not found: {entity_type} {entity_uid}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to store embedding for {entity_uid}: {e}")
            return False

    async def _process_chunk_batch(self, requests: list[ChunkEmbeddingRequested]) -> None:
        """
        Generate embeddings for batch of chunk requests.

        Each request contains multiple chunks from a single KU.
        Flattens chunks across all requests for efficient batch processing.

        Args:
            requests: List of ChunkEmbeddingRequested events to process
        """
        import time
        from datetime import datetime

        batch_start = time.time()

        try:
            # Flatten chunks from all requests
            all_chunk_uids: list[str] = []
            all_chunk_texts: list[str] = []
            request_map: dict[str, ChunkEmbeddingRequested] = {}

            for req in requests:
                all_chunk_uids.extend(req.chunk_uids)
                all_chunk_texts.extend(req.chunk_texts)
                request_map[req.ku_uid] = req

            self.logger.info(f"Processing {len(all_chunk_uids)} chunks from {len(requests)} KUs")

            # Generate embeddings in batch
            embeddings_result = await self.embeddings_service.create_batch_embeddings(
                all_chunk_texts
            )

            if embeddings_result.is_error:
                self.logger.error(
                    f"Batch chunk embedding generation failed: {embeddings_result.expect_error().message}"
                )
                # Re-queue for retry
                self._pending_chunk_requests.extend(requests)
                return

            embeddings = embeddings_result.value

            # Store embeddings via content adapter
            if self.content_adapter:
                stored = await self.content_adapter.store_chunk_embeddings(
                    chunk_uids=all_chunk_uids,
                    embeddings=embeddings,
                    version="v1",
                    model=self.embeddings_service.model,
                )

                if stored:
                    # Publish completion events for each KU
                    for ku_uid, req in request_map.items():
                        now = datetime.now()
                        await publish_event(
                            self.event_bus,
                            ChunkEmbeddingsCompleted(
                                ku_uid=ku_uid,
                                chunk_uids=req.chunk_uids,
                                success_count=len(req.chunk_uids),
                                failed_count=0,
                                completed_at=now,
                                occurred_at=now,
                            ),
                            self.logger,
                        )

                    batch_duration = time.time() - batch_start
                    self.logger.info(
                        f"✅ Generated {len(all_chunk_uids)} chunk embeddings successfully "
                        f"(took {batch_duration:.2f}s)"
                    )
                else:
                    self.logger.error("Failed to store chunk embeddings")
                    # Re-queue for retry
                    self._pending_chunk_requests.extend(requests)
            else:
                self.logger.warning("Content adapter not configured - chunk embeddings not stored")

        except Exception as e:
            self.logger.error(f"Chunk batch processing exception: {e}")
            # Re-queue for retry (with safety limit)
            if len(self._pending_chunk_requests) < 1000:
                self._pending_chunk_requests.extend(requests)

    def get_metrics(self) -> dict[str, Any]:
        """
        Get worker performance metrics.

        Returns:
            Dictionary with worker statistics:
            - total_processed: Total entities processed
            - total_success: Successfully embedded entities
            - total_failed: Failed embeddings
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
            "batches_processed": self._batches_processed,
            "queue_size": len(self._pending_requests),
            "chunk_queue_size": len(self._pending_chunk_requests),
            "uptime_seconds": uptime,
            "success_rate": round(success_rate, 2),
            "avg_batch_size": round(avg_batch, 2),
        }
