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

from typing import Any, Protocol, runtime_checkable


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
    ) -> list[dict[str, Any]]:
        """Return :Content rows (``uid``, ``body``, ``format``) needing regeneration.

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
            Plain-row dicts with keys ``uid``, ``body``, ``format``. Empty when
            nothing matches.
        """
        ...
