"""
Ingestion Cross-Boundary Types
==============================

The two ingestion types that cross the hexagonal boundary (ADR-044):

- ``RelationshipConfig`` — passed INTO the bulk-upsert backend by the ingestion
  service / ``config.py`` to describe how YAML connection fields become edges.
- ``IngestionResult`` — returned OUT of the backend to the service as the
  per-operation statistics payload.

Both must live in core so the ``core/ports`` protocol and its
``adapters/persistence/neo4j`` implementation can share the contract without the
service layer importing the adapter. The Cypher that consumes/produces them
lives below the boundary in ``adapters/persistence/neo4j/bulk_upsert_backend.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


class RelationshipConfig(TypedDict, total=False):
    """
    Configuration for a single relationship type in graph-native ingestion.

    Maps a flattened YAML connection field (e.g. ``connections.requires``) to the
    edge it should create.

    Fields:
        rel_type: Neo4j relationship type (e.g., "REQUIRES_KNOWLEDGE")
        target_label: Neo4j label for target nodes (e.g., "Entity")
        direction: Edge direction relative to the source node:
            - "incoming": creates ``(n)<-[:TYPE]-(target)``
            - "outgoing": creates ``(n)-[:TYPE]->(target)`` [default]
            - "both": creates bidirectional edges
    """

    rel_type: str
    target_label: str
    direction: Literal["incoming", "outgoing", "both"]


@dataclass
class IngestionResult:
    """Results from a bulk ingestion operation."""

    total_processed: int
    nodes_created: int
    nodes_updated: int
    relationships_created: int
    errors: list[str]
    duration_ms: float | None = None
    nodes_deleted: int = 0
    relationships_deleted: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_processed == 0:
            return 0.0
        return ((self.total_processed - len(self.errors)) / self.total_processed) * 100
