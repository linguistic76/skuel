"""
Embeddings Protocols
====================

Protocol for the EmbeddingsBackend — Neo4j operations for storing
and retrieving embedding vectors and metadata on entity nodes.

Implementation: adapters/persistence/neo4j/embeddings_backend.py
Consumer: HuggingFaceEmbeddingsService
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
        text: str | None,
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_embedding_metadata(
        self, label: NeoLabel, uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_cached_embedding(
        self, label: NeoLabel, uid: str
    ) -> Result[list[dict[str, Any]]]: ...
