"""
Chunk Protocols
===============

Persistence-layer protocols for the content-chunk regeneration pipeline.

The chunking algorithm (CHUNKING_ALGORITHM_VERSION) can change; when it does,
existing :ContentChunk nodes drift from their source :Content body and need to
be regenerated. ``BatchChunkingService`` orchestrates that — discovering stale
candidates from the graph and re-chunking them.

The candidate discovery itself is dynamic-Cypher (parent-uid filter + optional
version-staleness predicate), so it lives below the hexagonal boundary
(``adapters/persistence/neo4j/batch_chunking_backend.py``) and the service
depends on this port.

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
See: /docs/migrations/AUTOMATIC_CHUNKING_INTEGRATION_2026-01-29.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypedDict, runtime_checkable

if TYPE_CHECKING:
    from core.ports.query_types import ReferenceChunkHit


class BatchChunkingCandidate(TypedDict):
    """One :Content row needing chunk regeneration.

    Shape returned by the candidate-discovery Cypher in
    ``BatchChunkingBackend.fetch_regeneration_candidates`` — four Neo4j
    columns: ``c.uid``, ``c.body``, ``c.format``, and the parent's domain
    ``entity_label``. The query guards ``body`` against null/empty, but
    ``format`` is returned as-is, so it may be ``None`` for legacy content that
    predates the format field. ``entity_label`` is the parent Entity's domain
    label (e.g. ``"Ku"``, ``"PathStep"``) — used to resolve per-domain chunking
    params; ``None`` when no parent Entity is linked (falls back to defaults).
    """

    uid: str
    body: str
    format: str | None
    entity_label: str | None


@runtime_checkable
class BatchChunkingOperations(Protocol):
    """Persistence port for :Content chunk-regeneration candidate discovery.

    Implemented by ``BatchChunkingBackend``. Consumed by ``BatchChunkingService``.

    Narrow by design — the service only needs candidate rows; everything else
    (re-chunking, re-persisting, embedding re-emission) happens above the
    boundary in pure Python.
    """

    async def fetch_regeneration_candidates(
        self,
        parent_uids: list[str] | None,
        force: bool,
        current_version: str,
        expected_by_label: dict[str, str] | None = None,
    ) -> list[BatchChunkingCandidate]:
        """Return :Content rows needing regeneration.

        Args:
            parent_uids: Restrict to these parent UIDs, or ``None`` for all
                candidates.
            force: When ``True``, return every parent with a non-empty body —
                no version-staleness predicate. When ``False``, return only
                parents with no chunks or whose chunks carry a
                ``chunking_version`` other than the unit's *expected* tag.
            current_version: Fallback expected tag for any parent whose domain
                label is not in ``expected_by_label``. Used only when ``force``
                is ``False``; ignored otherwise.
            expected_by_label: Parent domain label → expected chunk-version tag,
                for domains whose ``ChunkingParams`` diverge from the default.
                Absent/empty (every domain on defaults) → all units compare
                against ``current_version``.

        Returns:
            Candidate rows shaped by ``BatchChunkingCandidate``. Empty when
            nothing matches.
        """
        ...


@runtime_checkable
class ReferenceChunkSearchOperations(Protocol):
    """Persistence port for reading the canon shelf's :ReferenceChunk vectors.

    Implemented by ``Neo4jReferenceChunkAdapter``. Consumed by
    ``CanonRetrievalService``. The ONLY read against
    ``referencechunk_embedding_idx`` — living here (not on the shared vector
    backend) is what keeps canon structurally invisible to SearchRouter (see
    ``tests/unit/adapters/test_reference_chunk_isolation.py``).
    """

    async def search_reference_chunks(
        self,
        query_embedding: list[float],
        limit: int,
        threshold: float,
        resource_uids: list[str] | None = None,
    ) -> list[ReferenceChunkHit]:
        """Return the top canon passages nearest the query embedding.

        Args:
            query_embedding: The query text's embedding vector.
            limit: Maximum passages to return.
            threshold: Minimum cosine similarity for a passage to count.
            resource_uids: ``None`` = the whole shelf (index search); a list =
                only chunks under those Resources (exact scoped scan); ``[]``
                = empty scope, returns ``[]`` without searching.

        Returns:
            ``ReferenceChunkHit`` rows ordered by descending similarity, each
            joined to its owning :Resource (book). Empty on no match, empty
            scope, or read error (fails open — a canon miss must never break
            the caller's session).
        """
        ...
