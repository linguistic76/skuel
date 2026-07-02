"""
Embeddings Protocols
====================

Two distinct boundaries:

- ``EmbeddingsBackendOperations`` — Neo4j STORAGE of embedding vectors and
  metadata on entity nodes.
  Implementation: adapters/persistence/neo4j/embeddings_backend.py

- ``EmbeddingClientOperations`` — the model-call boundary that turns text into
  a vector. Keeps vendor SDKs (``openai``, ``huggingface_hub``) out of
  ``core/`` (ADR-044 / W1, ADR-063).
  Implementations: adapters/external/embeddings/ (OpenAI is the wired provider,
  ADR-068; the HuggingFace/BGE adapter is staged for the long-term swap).

Consumer of both: EmbeddingsService (caching, versioning, storage
orchestration around the inference client).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.enums.neo_labels import NeoLabel


@runtime_checkable
class EmbeddingsBackendOperations(Protocol):
    """Backend operations for embedding storage and retrieval."""

    async def store_embedding_metadata(
        self,
        label: NeoLabel,
        uid: str,
        embedding: list[float],
        version: str,
        model: str,
        text_hash: str,
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_embedding_metadata(
        self, label: NeoLabel, uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_cached_embedding(
        self, label: NeoLabel, uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_embedding_freshness(self, uids: list[str]) -> Result[list[dict[str, Any]]]: ...

    async def touch_embedding_updated_at(self, uids: list[str]) -> Result[list[dict[str, Any]]]: ...

    async def stamp_embedding_text_hashes(
        self, label: NeoLabel, rows: list[dict[str, str]], version: str
    ) -> Result[list[dict[str, Any]]]: ...


@runtime_checkable
class EmbeddingClientOperations(Protocol):
    """Inference-side embedding generation: text → vector.

    This is the model-call boundary, distinct from EmbeddingsBackendOperations
    (which persists vectors in Neo4j). The concrete adapter owns the vendor SDK
    (openai / huggingface_hub) and the transport-level retry; the consuming core
    service keeps the caching/versioning/storage logic and reads
    ``model``/``dimension``/``max_input_chars`` off this port for metrics,
    validation, and truncation.

    Implementations: adapters/external/embeddings/
    """

    @property
    def model(self) -> str:
        """The embedding model identifier (e.g. ``'text-embedding-3-small'``)."""
        ...

    @property
    def dimension(self) -> int:
        """The embedding vector dimension (e.g. ``1024``)."""
        ...

    @property
    def max_input_chars(self) -> int:
        """Conservative character budget for the model's input token limit.

        The consuming service truncates text to this length before calling
        ``embed()`` — each adapter knows its own model's context window.
        """
        ...

    async def embed(self, text: str) -> Result[list[float]]:
        """Generate an embedding vector for a single text.

        Returns ``Result.ok(vector)`` or ``Result.fail(integration_error)``.
        Transport-level retry on transient failures is the adapter's concern.
        """
        ...
