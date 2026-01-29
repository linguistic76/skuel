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
    ChoiceEmbeddingRequested,
    EventEmbeddingRequested,
    GoalEmbeddingRequested,
    HabitEmbeddingRequested,
    PrincipleEmbeddingRequested,
    TaskEmbeddingRequested,
)
from core.events.embedding_events import EmbeddingRequested
from core.services.protocols.infrastructure_protocols import EventBusOperations
from core.utils.logging import get_logger


class EmbeddingBackgroundWorker:
    """
    Background worker that listens for embedding events and processes in batches.

    Zero-latency async embedding generation for all activity domains.
    """

    def __init__(
        self,
        event_bus: EventBusOperations,
        embeddings_service: Any,  # Neo4jGenAIEmbeddingsService
        driver: Any,  # AsyncDriver
        batch_size: int = 25,
        batch_interval_seconds: int = 30,
    ) -> None:
        """
        Initialize background worker.

        Args:
            event_bus: Event bus for subscribing to embedding requests
            embeddings_service: Neo4jGenAIEmbeddingsService for generating embeddings
            driver: Neo4j driver for updating nodes
            batch_size: Number of entities to process per batch
            batch_interval_seconds: Seconds between batch processing runs
        """
        self.event_bus = event_bus
        self.embeddings_service = embeddings_service
        self.driver = driver
        self.batch_size = batch_size
        self.batch_interval = batch_interval_seconds
        self._pending_requests: list[EmbeddingRequested] = []
        self.logger = get_logger("skuel.background.embeddings")

    async def start(self) -> None:
        """
        Start listening for embedding events.

        Subscribes to all domain embedding request events and starts batch processing loop.
        """
        # Subscribe to all embedding request events
        self.event_bus.subscribe(TaskEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(GoalEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(HabitEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(EventEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(ChoiceEmbeddingRequested, self._queue_request)
        self.event_bus.subscribe(PrincipleEmbeddingRequested, self._queue_request)

        self.logger.info(
            f"🔄 Embedding background worker started (batch_size={self.batch_size}, "
            f"interval={self.batch_interval}s)"
        )

        # Start batch processing loop
        await self._process_batches_loop()

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

    async def _process_batches_loop(self) -> None:
        """
        Process pending embedding requests in batches every N seconds.

        Infinite loop that runs batch processing at regular intervals.
        """
        while True:
            await asyncio.sleep(self.batch_interval)

            if not self._pending_requests:
                continue

            # Take batch of requests
            batch = self._pending_requests[: self.batch_size]
            self._pending_requests = self._pending_requests[self.batch_size :]

            self.logger.info(
                f"Processing batch of {len(batch)} embedding requests "
                f"({len(self._pending_requests)} remaining in queue)"
            )

            # Process batch
            await self._process_batch(batch)

    async def _process_batch(self, requests: list[EmbeddingRequested]) -> None:
        """
        Generate embeddings for batch of entities.

        Args:
            requests: List of EmbeddingRequested events to process
        """
        try:
            # Extract texts for batch embedding generation
            texts = [req.embedding_text for req in requests]

            # Generate embeddings in batch (more efficient than individual calls)
            embeddings_result = await self.embeddings_service.create_batch_embeddings(texts)

            if embeddings_result.is_error:
                self.logger.error(
                    f"Batch embedding generation failed: {embeddings_result.expect_error().message}"
                )
                # Re-queue requests for retry (simple retry logic)
                self._pending_requests.extend(requests)
                return

            embeddings = embeddings_result.value

            # Update each entity with its embedding
            success_count = 0
            for req, embedding in zip(requests, embeddings, strict=True):
                stored = await self._store_embedding(req.entity_uid, req.entity_type, embedding)
                if stored:
                    success_count += 1

            self.logger.info(
                f"✅ Generated {success_count}/{len(requests)} embeddings successfully"
            )

        except Exception as e:
            self.logger.error(f"Batch processing exception: {e}")
            # Re-queue for retry (with limit to avoid infinite loops)
            if len(self._pending_requests) < 1000:  # Safety limit
                self._pending_requests.extend(requests)

    async def _store_embedding(
        self, entity_uid: str, entity_type: str, embedding: list[float]
    ) -> bool:
        """
        Store embedding in Neo4j node.

        Args:
            entity_uid: UID of entity
            entity_type: Type of entity (task, goal, etc.)
            embedding: Embedding vector

        Returns:
            True if stored successfully, False otherwise
        """
        try:
            # Map entity type to Neo4j label (capitalized)
            label_map = {
                "task": "Task",
                "goal": "Goal",
                "habit": "Habit",
                "event": "Event",
                "choice": "Choice",
                "principle": "Principle",
            }
            label = label_map.get(entity_type, entity_type.capitalize())

            query = f"""
                MATCH (n:{label} {{uid: $uid}})
                SET n.embedding = $embedding,
                    n.embedding_model = $model,
                    n.embedding_updated_at = datetime()
                RETURN n.uid
            """

            result = await self.driver.execute_query(
                query,
                uid=entity_uid,
                embedding=embedding,
                model=self.embeddings_service.model,
            )

            if result and len(result) > 0:
                self.logger.debug(f"✅ Stored embedding for {entity_type} {entity_uid}")
                return True
            else:
                self.logger.warning(f"⚠️ Entity not found: {entity_type} {entity_uid}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to store embedding for {entity_uid}: {e}")
            return False
