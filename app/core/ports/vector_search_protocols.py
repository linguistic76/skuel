"""
Vector Search Protocols
========================

Protocols for the VectorSearchBackend — Neo4j vector index queries
and full-text search for semantic similarity.

Implementation: adapters/persistence/neo4j/vector_search_backend.py
Consumer: Neo4jVectorSearchService
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from core.ports.query_types import SemanticSearchChunkResult
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.enums.neo_labels import NeoLabel
    from core.models.type_hints import FilterParams


@runtime_checkable
class VectorSearchBackendOperations(Protocol):
    """Backend operations for vector search persistence."""

    async def query_vector_index(
        self, index_name: str, limit: int, embedding: list[float], min_score: float
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_node_embedding(
        self, label: NeoLabel, uid: str
    ) -> Result[list[dict[str, Any]]]: ...

    async def query_fulltext_index(
        self, index_name: str, query_text: str, limit: int
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_semantic_relationships(
        self, entity_uid: str, context_uids: list[str]
    ) -> Result[list[dict[str, Any]]]: ...

    async def get_learning_states_batch(
        self, user_uid: str, ku_uids: list[str]
    ) -> Result[list[dict[str, Any]]]: ...

    async def semantic_search_chunks(
        self,
        query_embedding: list[float],
        limit: int,
        threshold: float,
        chunk_types: list[str] | None = None,
        parent_uid: str | None = None,
        parent_filters: FilterParams | None = None,
        owner_uid: str | None = None,
        viewer_uid: str | None = None,
    ) -> Result[list[SemanticSearchChunkResult]]:
        """Vector search across :ContentChunk nodes for precise RAG retrieval.

        ``parent_filters`` scopes results to chunks whose owning Entity matches
        the active facets (nous, learning_level, ...). ``owner_uid`` restricts
        to chunks whose parent the given user OWNS and that is not marked
        ``private`` (canon P3 vault retrieval) — the scoped rows additionally
        carry ``parent_metadata``.

        ``viewer_uid`` is the audience (ADR-085) and is honoured on EVERY call:
        chunks of a published curriculum parent are visible to all; chunks of a
        user-owned parent (UserEntry) only to that user. ``None`` yields the
        curriculum half alone — no caller can read another user's notes by
        omitting the viewer.
        """
        ...
