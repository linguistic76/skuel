"""
Embedding Vector Domain Model
==============================

Represents embedding vectors for semantic search and similarity.
Stored using UniversalNeo4jBackend for graph integration.

Following SKUEL three-tier type system:
- This is Tier 3: Domain Model (frozen, immutable business logic)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.models.shared_enums import Domain


@dataclass(frozen=True)
class EmbeddingVector:
    """
    Vector embedding for semantic search.

    Stores embedding vectors alongside entity metadata in Neo4j.
    Enables semantic similarity search integrated with knowledge graph.

    Stored in Neo4j with label "EmbeddingVector".
    """

    # Identity
    uid: str  # Format: "embedding.{entity_uid}.{model}.{timestamp}"
    entity_uid: str  # UID of the entity being embedded
    entity_type: str  # "knowledge", "task", "habit", "goal", "journal", etc.

    # Vector data
    embedding: list[float]  # The actual embedding vector
    embedding_model: str  # Model used (e.g., "text-embedding-ada-002")
    embedding_dimension: int  # Vector dimensions (e.g., 1536 for ada-002)

    # Source content
    source_text: str  # Text that was embedded (for reference)
    source_hash: str  # Hash of source text (for cache invalidation)

    # Metadata
    created_at: datetime
    domain: Domain | None = (None,)
    metadata: dict[str, Any] | None = None  # type: ignore[assignment]

    # Version tracking
    version: int = 1  # Increment when re-embedding same entity

    def __post_init__(self) -> None:
        """Validate embedding data."""
        # Validate embedding dimensions
        if len(self.embedding) != self.embedding_dimension:
            raise ValueError(
                f"Embedding length {len(self.embedding)} does not match "
                f"declared dimension {self.embedding_dimension}"
            )

        # Validate all embedding values are floats
        if not all(isinstance(v, int | float) for v in self.embedding):
            raise ValueError("All embedding values must be numeric")

        # Validate source_hash
        if not self.source_hash:
            raise ValueError("source_hash is required for cache invalidation")

    @property
    def is_valid(self) -> bool:
        """Check if embedding is valid (non-zero)."""
        return any(v != 0.0 for v in self.embedding)

    @property
    def magnitude(self) -> float:
        """Calculate L2 norm (magnitude) of embedding vector."""
        return sum(v * v for v in self.embedding) ** 0.5

    def normalized(self) -> list[float]:
        """
        Return L2-normalized embedding vector.

        Returns:
            Normalized embedding (unit vector)
        """
        mag = self.magnitude
        if mag == 0.0:
            return self.embedding
        return [v / mag for v in self.embedding]

    def cosine_similarity(self, other: "EmbeddingVector") -> float:
        """
        Calculate cosine similarity with another embedding.

        Args:
            other: Another EmbeddingVector

        Returns:
            Cosine similarity score (0.0-1.0)
        """
        if len(self.embedding) != len(other.embedding):
            raise ValueError("Embeddings must have same dimensions")

        # Normalize both vectors
        norm_self = self.normalized()
        norm_other = other.normalized()

        # Dot product of normalized vectors = cosine similarity
        similarity = sum(a * b for a, b in zip(norm_self, norm_other, strict=False))

        # Clamp to [0, 1] range (handle floating point errors)
        return max(0.0, min(1.0, similarity))

    def euclidean_distance(self, other: "EmbeddingVector") -> float:
        """
        Calculate Euclidean distance to another embedding.

        Args:
            other: Another EmbeddingVector

        Returns:
            Euclidean distance
        """
        if len(self.embedding) != len(other.embedding):
            raise ValueError("Embeddings must have same dimensions")

        return (
            sum((a - b) ** 2 for a, b in zip(self.embedding, other.embedding, strict=False)) ** 0.5
        )


@dataclass(frozen=True)
class SimilarityMatch:
    """
    Result of similarity search.

    Read-only computed view, not stored directly.
    """

    entity_uid: str
    entity_type: str
    similarity_score: float  # 0.0-1.0 (cosine similarity)
    source_text: str
    domain: Domain | None = (None,)

    metadata: dict[str, Any] | None = None  # type: ignore[assignment]

    @property
    def is_high_similarity(self) -> bool:
        """Check if similarity is high (>= 0.8)."""
        return self.similarity_score >= 0.8

    @property
    def is_moderate_similarity(self) -> bool:
        """Check if similarity is moderate (0.6-0.8)."""
        return 0.6 <= self.similarity_score < 0.8

    @property
    def is_low_similarity(self) -> bool:
        """Check if similarity is low (< 0.6)."""
        return self.similarity_score < 0.6


# ============================================================================
# UID GENERATION
# ============================================================================


def generate_embedding_uid(entity_uid: str, model: str, timestamp: datetime | None = None) -> str:
    """
    Generate unique UID for embedding record.

    Format: embedding.{entity_uid}.{model}.{timestamp_ms}

    Args:
        entity_uid: Entity identifier
        model: Embedding model name
        timestamp: Optional timestamp (defaults to now)

    Returns:
        Generated UID
    """
    if not timestamp:
        timestamp = datetime.now()

    # Normalize model name (remove "text-embedding-" prefix if present)
    model_short = model.replace("text-embedding-", "").replace("-", "")

    timestamp_ms = int(timestamp.timestamp() * 1000)
    return f"embedding.{entity_uid}.{model_short}.{timestamp_ms}"


def hash_source_text(text: str) -> str:
    """
    Generate hash of source text for cache invalidation.

    Args:
        text: Source text to hash

    Returns:
        SHA256 hash (hex string)
    """
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ["EmbeddingVector", "SimilarityMatch", "generate_embedding_uid", "hash_source_text"]
