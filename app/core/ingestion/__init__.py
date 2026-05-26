"""
Ingestion core helpers.

Pure, transport-agnostic ingestion pieces that stay above the hexagonal boundary:
- ``batch_preparer`` — entity → Neo4j-ready dict transformation (no Cypher, no driver)
- ``ingestion_types`` — cross-boundary types (RelationshipConfig, IngestionResult)
- ``vectors`` — Vector value object + VectorSpace enum (pure math)

The bulk-upsert engine, Cypher executor, Cypher templates, and the graph-backed
VectorOperations were relocated below the boundary to ``adapters/persistence/neo4j/``
(ADR-044).
"""

from .ingestion_types import IngestionResult, RelationshipConfig
from .vectors import Vector, VectorSpace

__all__ = [
    "IngestionResult",
    "RelationshipConfig",
    "Vector",
    "VectorSpace",
]
