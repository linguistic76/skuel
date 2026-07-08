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

from typing import Protocol, TypedDict, runtime_checkable


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
    ) -> list[BatchChunkingCandidate]:
        """Return :Content rows needing regeneration.

        Args:
            parent_uids: Restrict to these parent UIDs, or ``None`` for all
                candidates.
            force: When ``True``, return every parent with a non-empty body —
                no version-staleness predicate. When ``False``, return only
                parents with no chunks or whose chunks carry a
                ``chunking_version`` other than ``current_version``.
            current_version: The chunking algorithm version. Used only as a
                filter when ``force`` is ``False``; ignored otherwise.

        Returns:
            Candidate rows shaped by ``BatchChunkingCandidate``. Empty when
            nothing matches.
        """
        ...
