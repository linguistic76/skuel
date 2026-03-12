"""
HuggingFace Embeddings Service
==============================

Generates embeddings via HuggingFace Inference API using BAAI/bge-large-en-v1.5.

ARCHITECTURE:
- Model: BAAI/bge-large-en-v1.5 (1024 dims) — sentence-transformers-compatible,
  hosted on HuggingFace. Top-tier retrieval quality on MTEB benchmarks.
- Client: huggingface_hub.InferenceClient (NOT sentence-transformers package —
  that's for local inference. We use the API for serverless, no-GPU deployment.)
- API key: HF_API_TOKEN environment variable
- Stores embeddings in Neo4j via QueryExecutor
- Graceful degradation when HF_API_TOKEN not set

MIGRATION (March 2026):
- Replaces Neo4jGenAIEmbeddingsService (OpenAI text-embedding-3-small via GenAI plugin)
- Embedding dimension changed: 1536 → 1024
- EMBEDDING_VERSION incremented: v1 → v2
- All existing embeddings must be regenerated

See: /docs/decisions/ADR-049-huggingface-embeddings-migration.md
"""

import math
import os
import time
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor

logger = get_logger("skuel.embeddings")

# Embedding version tracking
# Increment when changing embedding model or parameters
EMBEDDING_VERSION = "v2"

# BGE-large-en-v1.5 configuration
DEFAULT_MODEL = "BAAI/bge-large-en-v1.5"
DEFAULT_DIMENSION = 1024
MAX_TOKENS = 512  # Model max token limit
MAX_CHARS = 2000  # ~512 tokens, conservative estimate


class HuggingFaceEmbeddingsService:
    """
    Embeddings service using HuggingFace Inference API.

    Uses BAAI/bge-large-en-v1.5 (1024 dimensions) via InferenceClient.feature_extraction().

    Setup:
    - Requires HF_API_TOKEN environment variable
    - No Neo4j plugin dependency (pure Python-side embedding generation)
    - Stores embeddings in Neo4j via QueryExecutor

    See: /docs/decisions/ADR-048-huggingface-embeddings-migration.md
    """

    def __init__(
        self,
        executor: "QueryExecutor",
        model: str = DEFAULT_MODEL,
        dimension: int = DEFAULT_DIMENSION,
        prometheus_metrics: Any | None = None,
    ) -> None:
        self.executor = executor
        self.model = model
        self.dimension = dimension
        self.logger = logger
        self.prometheus_metrics = prometheus_metrics

        # Initialize HuggingFace client
        hf_token = os.getenv("HF_API_TOKEN", "")
        if not hf_token:
            self.logger.warning("HF_API_TOKEN not set - embeddings will fail")
            self._client = None
        else:
            from huggingface_hub import InferenceClient

            self._client = InferenceClient(model=self.model, token=hf_token)
            self.logger.info(f"HuggingFace embeddings client initialized (model={self.model})")

    async def create_embedding(
        self, text: str, metadata: dict[str, Any] | None = None
    ) -> Result[list[float]]:
        """
        Create embedding using HuggingFace Inference API.

        Args:
            text: Text to embed
            metadata: Optional metadata (unused, kept for interface compatibility)

        Returns:
            Result containing embedding vector or error
        """
        if self._client is None:
            return Result.fail(
                Errors.unavailable(
                    feature="embeddings",
                    reason="HF_API_TOKEN not configured",
                    operation="create_embedding",
                )
            )

        if not text or not text.strip():
            return Result.fail(Errors.validation("Text cannot be empty", field="text"))

        # Truncate to stay within model token limits
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]
            self.logger.warning(f"Text truncated to {MAX_CHARS} chars for token limit")

        start_time = time.time()

        try:
            # HuggingFace Inference API call (synchronous — runs in event loop)
            # feature_extraction returns nested list: [[float, ...]]
            raw = self._client.feature_extraction(text)
            duration = time.time() - start_time

            # Extract the embedding vector from the response
            # feature_extraction returns a numpy array or nested list
            import numpy as np

            if isinstance(raw, np.ndarray):
                # Shape could be (1, dim) or (dim,) depending on API response
                embedding = raw[0].tolist() if raw.ndim == 2 else raw.tolist()
            elif isinstance(raw, list):
                # May be nested [[float, ...]] or flat [float, ...]
                embedding = raw[0] if raw and isinstance(raw[0], list) else raw
            else:
                return Result.fail(
                    Errors.integration(
                        service="HuggingFace",
                        message=f"Unexpected response type: {type(raw).__name__}",
                    )
                )

            # Track metrics
            if self.prometheus_metrics:
                self.prometheus_metrics.ai.openai_requests_total.labels(
                    operation="embeddings", model=self.model
                ).inc()
                self.prometheus_metrics.ai.openai_duration_seconds.labels(
                    operation="embeddings", model=self.model
                ).observe(duration)

            # Validate dimension
            if len(embedding) != self.dimension:
                return Result.fail(
                    Errors.integration(
                        service="HuggingFace",
                        message=f"Expected {self.dimension}d embedding, got {len(embedding)}d",
                    )
                )

            return Result.ok(embedding)

        except Exception as e:
            duration = time.time() - start_time

            if self.prometheus_metrics:
                self.prometheus_metrics.ai.openai_errors_total.labels(
                    operation="embeddings", error_type=type(e).__name__
                ).inc()

            self.logger.error(f"Embedding generation failed: {e}")
            return Result.fail(
                Errors.integration(
                    service="HuggingFace", message=f"Embedding generation failed: {e}"
                )
            )

    async def create_batch_embeddings(
        self, texts: list[str], metadata_list: list[dict[str, Any]] | None = None
    ) -> Result[list[list[float]]]:
        """
        Create embeddings for multiple texts.

        Calls HuggingFace API for each text individually (batch endpoint
        not reliably available for all models on Inference API).

        Args:
            texts: List of texts to embed
            metadata_list: Optional metadata list (unused, kept for interface compatibility)

        Returns:
            Result containing list of embedding vectors or error
        """
        if self._client is None:
            return Result.fail(
                Errors.unavailable(
                    feature="embeddings",
                    reason="HF_API_TOKEN not configured",
                    operation="create_batch_embeddings",
                )
            )

        if not texts:
            return Result.ok([])

        start_time = time.time()
        embeddings: list[list[float]] = []

        for text in texts:
            result = await self.create_embedding(text)
            if result.is_error:
                return Result.fail(
                    Errors.integration(
                        service="HuggingFace",
                        message=f"Batch embedding failed at index {len(embeddings)}: {result.error}",
                    )
                )
            embeddings.append(result.value)

        duration = time.time() - start_time

        if self.prometheus_metrics:
            self.prometheus_metrics.ai.openai_duration_seconds.labels(
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
        query = f"""
        MATCH (n:{label} {{uid: $uid}})
        SET n.embedding = $embedding,
            n.embedding_version = $version,
            n.embedding_model = $model,
            n.embedding_updated_at = datetime(),
            n.embedding_source_text = $text
        RETURN n.uid as uid
        """

        params = {
            "uid": uid,
            "embedding": embedding,
            "version": EMBEDDING_VERSION,
            "model": self.model,
            "text": text,
        }

        result = await self.executor.execute_query(query, params)

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
        query = f"""
        MATCH (n:{label} {{uid: $uid}})
        RETURN n.embedding as embedding,
               n.embedding_version as version,
               n.embedding_model as model,
               n.embedding_updated_at as updated_at
        """

        result = await self.executor.execute_query(query, {"uid": uid})

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
        # Check if node has current-version embedding
        compat_result = await self.check_version_compatibility(uid, label)

        if compat_result.is_ok and compat_result.value["is_current"]:
            # Cache hit - get existing embedding
            query = f"""
            MATCH (n:{label} {{uid: $uid}})
            RETURN n.embedding as embedding
            """

            try:
                result = await self.executor.execute_query(query, {"uid": uid})

                if result.is_ok and result.value and result.value[0].get("embedding"):
                    self.logger.debug(f"Cache hit: {label}:{uid} (version={EMBEDDING_VERSION})")
                    return Result.ok(result.value[0]["embedding"])

            except Exception as e:
                self.logger.warning(f"Failed to get cached embedding: {e}")
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


# Backward compatibility alias
Neo4jGenAIEmbeddingsService = HuggingFaceEmbeddingsService
