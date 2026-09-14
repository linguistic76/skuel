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

from dataclasses import dataclass, field
from typing import Literal, NamedTuple, TypedDict

from core.models.relationship_names import RelationshipName


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
        order_property: When set, the YAML list order is persisted onto each
            edge as this property (0-based index, refreshed on re-ingest) —
            sourced from the registry's ``order_by_property`` (e.g. HAS_STEP
            ``sequence``, ORGANIZES ``order``). The vault list IS the ordering;
            dropping it would lose authored sequence.
    """

    rel_type: str
    target_label: str
    direction: Literal["incoming", "outgoing", "both"]
    order_property: str


# The two edge patterns the relationship template writes, relative to the
# file's own node: ``outgoing`` = (source)-[:T]->(target), ``incoming`` =
# (source)<-[:T]-(target). A field declared ``both`` is written as outgoing.
EdgeDirection = Literal["incoming", "outgoing"]


class AuthoredEdge(NamedTuple):
    """One edge a file's frontmatter authored, addressed the way the retraction
    primitive deletes it — type, direction relative to the source, target uid.

    The ``rel_type`` is a ``RelationshipName``: the enum is what guarantees a
    fingerprint key decoded from the graph names a type the registry knows.
    """

    rel_type: RelationshipName
    direction: EdgeDirection
    target_uid: str


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
    #: uid → the status each upserted node held BEFORE this write, read under
    #: the node's write-lock (ADR-087). ``None`` for a node the write created.
    #: Empty for every operation that is not a node upsert.
    prior_status_by_uid: dict[str, str | None] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_processed == 0:
            return 0.0
        return ((self.total_processed - len(self.errors)) / self.total_processed) * 100
