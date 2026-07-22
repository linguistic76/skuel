"""
Knowledge-Health Protocols
==========================

Backend operations for the knowledge-subgraph structural-health gauge
(ADR-080 Horizon-1).

Implementation: adapters/persistence/neo4j/backends/curriculum_backends.py
                (``KnowledgeHealthBackend``)
Consumer: core/services/analytics/knowledge_health_service.py
          (``KnowledgeHealthService``)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.query_types import KnowledgeHealthRaw


@runtime_checkable
class KnowledgeHealthOperations(Protocol):
    """Read-only corpus measurement over the knowledge subgraph.

    A single one-round-trip method — the service derives coverage ratios, the
    composite readiness score, and authoring flags from the raw facts, so the
    backend stays pure measurement.
    """

    async def measure_knowledge_subgraph(self) -> Result[KnowledgeHealthRaw]: ...
