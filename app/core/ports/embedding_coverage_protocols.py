"""
Embedding-Coverage Protocols
============================

Backend operations for the embedding-coverage gauge — retrievability measured
in the graph rather than inferred from config (a count probe, CORE-tier safe).

Implementation: adapters/persistence/neo4j/backends/curriculum_backends.py
                (``EmbeddingCoverageBackend``)
Consumer: core/services/analytics/knowledge_health_service.py
          (``KnowledgeHealthService`` — optional report block + authoring flag)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.embeddings.retrievability import EmbeddingCoverage


@runtime_checkable
class EmbeddingCoverageOperations(Protocol):
    """Read-only corpus scan of embedding coverage across every embeddable label.

    A single one-round-trip method — per-label total vs missing counts over
    ``EMBEDDING_SCAN_LABELS``; the consumer derives totals, remedies, and
    presentation from the returned facts.
    """

    async def measure_embedding_coverage(self) -> Result[EmbeddingCoverage]: ...
