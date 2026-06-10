"""
Embeddings Service
==================

Orchestrates embedding generation: caching, version tracking, dimension
validation, metrics, and Neo4j storage around an injected inference client.

ARCHITECTURE:
- Provider-agnostic: the inference client is injected via the
  ``EmbeddingClientOperations`` port and is the single source of truth for
  model, dimension, and input-size limits. Vendor SDKs live below the
  hexagonal boundary in ``adapters/external/embeddings/`` (W1 / ADR-044);
  the API key is read at the composition root, not here.
- Wired provider: OpenAI text-embedding-3-small at 1024 dims (ADR-068);
  the HuggingFace/BGE adapter is staged for the long-term swap.
- Stores embeddings in Neo4j via EmbeddingsBackend (``EmbeddingsBackendOperations``)

See: /docs/decisions/ADR-068-openai-embeddings-now-bge-later.md
"""

import asyncio
import math
import time
from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.embeddings_protocols import (
        EmbeddingClientOperations,
        EmbeddingsBackendOperations,
    )

logger = get_logger("skuel.embeddings")

# Embedding version tracking — THE single source of truth for stored-embedding
# compatibility. Increment when changing embedding model or parameters.
# History: v1 = OpenAI text-embedding-3-small @1536 via Neo4j GenAI plugin;
# v2 = BGE-large-en-v1.5 @1024 via HF Inference API (never backfilled);
# v3 = OpenAI text-embedding-3-small @1024 via API `dimensions` param (ADR-068).
EMBEDDING_VERSION = "v3"


class EmbeddingsService:
    """
    Embeddings service orchestrating an injected inference client.

    Owns caching, version tracking, dimension validation, metrics, and Neo4j
    storage. The actual text → vector call is delegated to an
    ``EmbeddingClientOperations`` adapter, which also dictates model,
    dimension, and truncation budget.

    Setup:
    - Inference client injected at the composition root (no SDK or credential
      reads here — W1 / ADR-044)
    - No Neo4j plugin dependency (pure Python-side embedding generation)
    - Stores embeddings in Neo4j via EmbeddingsBackend

    See: /docs/decisions/ADR-068-openai-embeddings-now-bge-later.md
    """

    def __init__(
        self,
        backend: "EmbeddingsBackendOperations",
        embedding_client: "EmbeddingClientOperations",
        prometheus_metrics: Any | None = None,
    ) -> None:
        self.backend = backend
        self._embedding_client = embedding_client
        # model/dimension are sourced from the inference client (single source of
        # truth) — read by metrics, dimension validation, and storage metadata.
        self.model = embedding_client.model
        self.dimension = embedding_client.dimension
        self.logger = logger
        self.prometheus_metrics = prometheus_metrics

    async def create_embedding(
        self, text: str, metadata: dict[str, Any] | None = None
    ) -> Result[list[float]]:
        """
        Create an embedding, delegating the model call to the inference client.

        Args:
            text: Text to embed
            metadata: Optional metadata (unused, kept for interface compatibility)

        Returns:
            Result containing embedding vector or error
        """
        if not text or not text.strip():
            return Result.fail(Errors.validation("Text cannot be empty", field="text"))

        # Truncate to stay within model token limits (budget owned by the client)
        max_chars = self._embedding_client.max_input_chars
        if len(text) > max_chars:
            text = text[:max_chars]
            self.logger.warning(f"Text truncated to {max_chars} chars for token limit")

        start_time = time.time()
        result = await self._embedding_client.embed(text)
        duration = time.time() - start_time

        if result.is_error:
            if self.prometheus_metrics:
                self.prometheus_metrics.ai.ai_errors_total.labels(
                    operation="embeddings", error_type="integration"
                ).inc()
            self.logger.error(f"Embedding generation failed: {result.error}")
            return Result.fail(result)

        embedding = result.value

        # Track metrics
        if self.prometheus_metrics:
            self.prometheus_metrics.ai.ai_requests_total.labels(
                operation="embeddings", model=self.model
            ).inc()
            self.prometheus_metrics.ai.ai_duration_seconds.labels(
                operation="embeddings", model=self.model
            ).observe(duration)

        # Validate dimension
        if len(embedding) != self.dimension:
            return Result.fail(
                Errors.integration(
                    service="embeddings",
                    message=f"Expected {self.dimension}d embedding, got {len(embedding)}d",
                )
            )

        return Result.ok(embedding)

    async def create_batch_embeddings(
        self, texts: list[str], metadata_list: list[dict[str, Any]] | None = None
    ) -> Result[list[list[float]]]:
        """
        Create embeddings for multiple texts.

        Calls the inference client for each text individually, concurrently
        (single-text ``embed()`` is the port contract; providers with native
        batch endpoints can be exploited later via a port extension).

        Args:
            texts: List of texts to embed
            metadata_list: Optional metadata list (unused, kept for interface compatibility)

        Returns:
            Result containing list of embedding vectors or error
        """
        if not texts:
            return Result.ok([])

        start_time = time.time()

        # Fire all requests concurrently
        tasks = [self.create_embedding(text) for text in texts]
        results = await asyncio.gather(*tasks)

        embeddings: list[list[float]] = []
        for i, result in enumerate(results):
            if result.is_error:
                return Result.fail(
                    Errors.integration(
                        service="embeddings",
                        message=f"Batch embedding failed at index {i}: {result.error}",
                    )
                )
            embeddings.append(result.value)

        duration = time.time() - start_time

        if self.prometheus_metrics:
            self.prometheus_metrics.ai.ai_duration_seconds.labels(
                operation="embeddings_batch", model=self.model
            ).observe(duration)

        return Result.ok(embeddings)

    async def calculate_similarity(
        self, embedding1: list[float], embedding2: list[float]
    ) -> Result[float]:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Result containing similarity score (0.0-1.0) or error
        """
        if len(embedding1) != len(embedding2):
            return Result.fail(
                Errors.validation("Embeddings must have same dimension", field="embeddings")
            )

        dot_product = sum(a * b for a, b in zip(embedding1, embedding2, strict=False))
        norm1 = math.sqrt(sum(a * a for a in embedding1))
        norm2 = math.sqrt(sum(b * b for b in embedding2))

        if norm1 == 0 or norm2 == 0:
            return Result.fail(
                Errors.validation("Cannot compute similarity for zero vectors", field="embeddings")
            )

        similarity = dot_product / (norm1 * norm2)
        return Result.ok(similarity)

    async def store_embedding_with_metadata(
        self,
        uid: str,
        label: str,
        embedding: list[float],
        text: str | None = None,
    ) -> Result[None]:
        """
        Store embedding with version metadata on a node.

        Args:
            uid: Node UID
            label: Node label (e.g., "Entity", "Task")
            embedding: Embedding vector to store
            text: Optional source text that was embedded

        Returns:
            Result indicating success or error
        """
        if not NeoLabel.is_valid(label):
            return Result.fail(Errors.validation(f"Invalid Neo4j label: {label}", field="label"))
        result = await self.backend.store_embedding_metadata(
            label=NeoLabel(label),
            uid=uid,
            embedding=embedding,
            version=EMBEDDING_VERSION,
            model=self.model,
            text=text,
        )

        if result.is_error:
            self.logger.error(f"Failed to store embedding metadata: {result.error}")
            return Result.fail(
                Errors.database(
                    operation="store_embedding", message=f"Failed to store: {result.error}"
                )
            )

        if not result.value:
            return Result.fail(Errors.not_found(resource="Node", identifier=f"{label}:{uid}"))

        self.logger.debug(f"Stored embedding for {label}:{uid} (version={EMBEDDING_VERSION})")
        return Result.ok(None)

    async def get_embedding_metadata(self, uid: str, label: str) -> Result[dict[str, Any]]:
        """
        Get embedding version metadata for a node.

        Returns:
            Result containing metadata dict with keys:
            - has_embedding, version, model, updated_at, dimension
        """
        if not NeoLabel.is_valid(label):
            return Result.fail(Errors.validation(f"Invalid Neo4j label: {label}", field="label"))
        result = await self.backend.get_embedding_metadata(label=NeoLabel(label), uid=uid)

        if result.is_error:
            self.logger.error(f"Failed to get embedding metadata: {result.error}")
            return Result.fail(
                Errors.database(
                    operation="get_metadata", message=f"Failed to get metadata: {result.error}"
                )
            )

        if not result.value:
            return Result.fail(Errors.not_found(resource="Node", identifier=f"{label}:{uid}"))

        record = result.value[0]
        embedding = record.get("embedding")

        metadata = {
            "has_embedding": embedding is not None,
            "version": record.get("version"),
            "model": record.get("model"),
            "updated_at": record.get("updated_at"),
            "dimension": len(embedding) if embedding else None,
        }

        return Result.ok(metadata)

    async def check_version_compatibility(self, uid: str, label: str) -> Result[dict[str, Any]]:
        """
        Check if node's embedding version is compatible with current version.

        Returns:
            Result containing compatibility info:
            - is_current, node_version, current_version, needs_update, has_embedding
        """
        metadata_result = await self.get_embedding_metadata(uid, label)

        if metadata_result.is_error:
            return metadata_result

        metadata = metadata_result.value
        node_version = metadata.get("version")

        is_current = node_version == EMBEDDING_VERSION
        needs_update = metadata["has_embedding"] and not is_current

        compatibility = {
            "is_current": is_current,
            "node_version": node_version,
            "current_version": EMBEDDING_VERSION,
            "needs_update": needs_update,
            "has_embedding": metadata["has_embedding"],
        }

        return Result.ok(compatibility)

    async def get_or_create_embedding(self, uid: str, label: str, text: str) -> Result[list[float]]:
        """
        Get cached embedding or create new one with version tracking.

        Cache hit: Return existing embedding (no API call).
        Cache miss or stale: Generate new embedding and store with metadata.

        Args:
            uid: Node UID
            label: Node label
            text: Text to embed (used if generating new)

        Returns:
            Result containing embedding vector
        """
        if not NeoLabel.is_valid(label):
            return Result.fail(Errors.validation(f"Invalid Neo4j label: {label}", field="label"))

        # Check if node has current-version embedding
        compat_result = await self.check_version_compatibility(uid, label)

        if compat_result.is_ok and compat_result.value["is_current"]:
            # Cache hit - get existing embedding
            result = await self.backend.get_cached_embedding(label=NeoLabel(label), uid=uid)

            if result.is_ok and result.value and result.value[0].get("embedding"):
                self.logger.debug(f"Cache hit: {label}:{uid} (version={EMBEDDING_VERSION})")
                return Result.ok(result.value[0]["embedding"])

            if result.is_error:
                self.logger.warning(f"Failed to get cached embedding: {result.error}")
                # Fall through to regenerate

        # Cache miss or stale - generate new embedding
        self.logger.debug(f"Cache miss: {label}:{uid} - generating new embedding")

        embedding_result = await self.create_embedding(text)

        if embedding_result.is_error:
            return embedding_result

        embedding = embedding_result.value

        # Store with metadata
        store_result = await self.store_embedding_with_metadata(
            uid=uid, label=label, embedding=embedding, text=text
        )

        if store_result.is_error:
            # Log warning but return embedding anyway
            self.logger.warning(f"Failed to store embedding metadata: {store_result.error}")

        return Result.ok(embedding)
