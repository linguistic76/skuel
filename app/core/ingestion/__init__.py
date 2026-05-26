"""
Ingestion core helpers.

Pure, transport-agnostic ingestion pieces that stay above the hexagonal boundary:
- ``batch_preparer`` — entity → Neo4j-ready dict transformation (no Cypher, no driver)
- ``ingestion_types`` — cross-boundary types (RelationshipConfig, IngestionResult)

The bulk-upsert engine, Cypher executor, and Cypher templates were relocated below
the boundary to ``adapters/persistence/neo4j/`` (ADR-044).
"""

from .ingestion_types import IngestionResult, RelationshipConfig

__all__ = [
    "IngestionResult",
    "RelationshipConfig",
]
