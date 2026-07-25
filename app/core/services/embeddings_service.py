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
import time
from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.utils.embedding_text_builder import hash_embedding_text
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.vector_math import cosine_similarity, l2_norm

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

    def calculate_similarity(
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

        if l2_norm(embedding1) == 0.0 or l2_norm(embedding2) == 0.0:
            return Result.fail(
                Errors.validation("Cannot compute similarity for zero vectors", field="embeddings")
            )

        return Result.ok(cosine_similarity(embedding1, embedding2))

    async def store_embedding_with_metadata(
        self,
        uid: str,
        label: str,
        embedding: list[float],
        text: str,
    ) -> Result[None]:
        """
        Store embedding with version metadata on a node.

        Every store carries ``embedding_text_hash`` (sha256 of ``text`` via
        the one hash recipe) so ``verify_fresh_embeddings`` can skip
        re-embedding unchanged text — which is why ``text`` is required: a
        stored embedding without its hash would read as permanently stale.

        Args:
            uid: Node UID
            label: Node label (e.g., "Entity", "Task")
            embedding: Embedding vector to store
            text: The exact text the embedding was generated from

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
            text_hash=hash_embedding_text(text),
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

    async def verify_fresh_embeddings(self, candidates: dict[str, str]) -> Result[set[str]]:
        """
        THE skip decision: which candidates' stored embeddings are already fresh?

        Fresh = the node has an embedding, its version matches
        ``EMBEDDING_VERSION``, and its stored ``embedding_text_hash`` equals
        the hash of the candidate text. Version outranks hash: a version
        mismatch is never fresh, so a deliberate model migration re-embeds
        regardless of text equality. Fresh nodes get ``embedding_updated_at``
        touched (metadata-only, no API call) so the coarse timestamp filter
        converges instead of re-flagging them on every ``--stale`` run.

        All pre-generation consumers — the background worker's batch
        pre-check, the ``--stale`` backfill's fine filter, and
        ``get_or_create_embedding``'s cache decision — call this, so the
        freshness semantics live in exactly one place.

        Args:
            candidates: uid → the embedding text that WOULD be embedded now

        Returns:
            Result with the set of uids that need no re-embedding
        """
        if not candidates:
            return Result.ok(set())

        read = await self.backend.get_embedding_freshness(list(candidates))
        if read.is_error:
            self.logger.error(f"Failed to read embedding freshness: {read.error}")
            return Result.fail(
                Errors.database(
                    operation="verify_fresh_embeddings",
                    message=f"Freshness read failed: {read.error}",
                )
            )

        fresh: set[str] = set()
        for row in read.value:
            uid = row["uid"]
            text = candidates.get(uid)
            if (
                text is not None
                and row.get("has_embedding")
                and row.get("version") == EMBEDDING_VERSION
                and row.get("text_hash") == hash_embedding_text(text)
            ):
                fresh.add(uid)

        if fresh:
            touch = await self.backend.touch_embedding_updated_at(sorted(fresh))
            if touch.is_error:
                # The freshness verdict stands — the touch only accelerates
                # timestamp convergence; a failed touch just means the node
                # re-enters the coarse filter and hash-skips again next run.
                self.logger.warning(f"Failed to touch embedding_updated_at: {touch.error}")

        return Result.ok(fresh)

    async def stamp_embedding_hashes(self, label: str, texts: dict[str, str]) -> Result[int]:
        """
        One-shot hash rollout: stamp ``embedding_text_hash`` without re-embedding.

        For nodes embedded before the hash existed: hashes each node's CURRENT
        embedding text and writes it next to the existing vector — sound only
        for vectors that provably match that text, which the backend enforces
        (version current, no hash yet, no timestamp drift). Nodes failing the
        guards keep a null hash and self-heal through the normal re-embed
        paths. Zero API calls.

        Args:
            label: Node label (one embeddable label per call)
            texts: uid → current build_embedding_text output

        Returns:
            Result with the count of nodes stamped
        """
        if not NeoLabel.is_valid(label):
            return Result.fail(Errors.validation(f"Invalid Neo4j label: {label}", field="label"))
        if not texts:
            return Result.ok(0)

        rows = [{"uid": uid, "text_hash": hash_embedding_text(text)} for uid, text in texts.items()]
        result = await self.backend.stamp_embedding_text_hashes(
            label=NeoLabel(label), rows=rows, version=EMBEDDING_VERSION
        )
        if result.is_error:
            self.logger.error(f"Failed to stamp embedding hashes: {result.error}")
            return Result.fail(
                Errors.database(
                    operation="stamp_embedding_hashes", message=f"Stamp failed: {result.error}"
                )
            )

        stamped = int(result.value[0]["stamped"]) if result.value else 0
        return Result.ok(stamped)

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
        Return the stored embedding if it is fresh, else generate + store.

        Freshness is THE one skip decision (``verify_fresh_embeddings``):
        version current AND stored ``embedding_text_hash`` matches ``text`` —
        a version-current node whose text changed regenerates instead of
        returning its stale vector. Fails OPEN: a freshness-read error (or a
        failed cached-vector read) regenerates — correctness over savings.

        Args:
            uid: Node UID
            label: Node label
            text: The CURRENT embedding text — both the freshness input and,
                on a miss, what gets embedded and hashed

        Returns:
            Result containing embedding vector
        """
        if not NeoLabel.is_valid(label):
            return Result.fail(Errors.validation(f"Invalid Neo4j label: {label}", field="label"))

        fresh_result = await self.verify_fresh_embeddings({uid: text})
        if fresh_result.is_ok and uid in fresh_result.value:
            # Cache hit - stored vector provably matches this text
            result = await self.backend.get_cached_embedding(label=NeoLabel(label), uid=uid)

            if result.is_ok and result.value and result.value[0].get("embedding"):
                self.logger.debug(f"Cache hit: {label}:{uid} (version={EMBEDDING_VERSION})")
                return Result.ok(result.value[0]["embedding"])

            if result.is_error:
                self.logger.warning(f"Failed to get cached embedding: {result.error}")
                # Fall through to regenerate

        # Cache miss, stale, or freshness read failed (fail open) - regenerate
        self.logger.debug(f"Cache miss: {label}:{uid} - generating new embedding")

        embedding_result = await self.create_embedding(text)

        if embedding_result.is_error:
            return embedding_result

        embedding = embedding_result.value

        # Store with metadata (writes the text hash for the next freshness read)
        store_result = await self.store_embedding_with_metadata(
            uid=uid, label=label, embedding=embedding, text=text
        )

        if store_result.is_error:
            # Log warning but return embedding anyway
            self.logger.warning(f"Failed to store embedding metadata: {store_result.error}")

        return Result.ok(embedding)
