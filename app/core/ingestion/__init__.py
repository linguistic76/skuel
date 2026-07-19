"""
Ingestion core helpers.

Pure, transport-agnostic ingestion pieces that stay above the hexagonal boundary:
- ``ingestion_types`` — cross-boundary types (RelationshipConfig, IngestionResult)

The bulk-upsert engine, Cypher executor, Cypher templates, and the batch
preparer (entity → Neo4j-ready dict transformation) live below the boundary in
``adapters/persistence/neo4j/`` (ADR-044; batch_preparer relocated in Tier 6 —
its only consumer is the bulk-upsert backend).
"""

from .ingestion_types import IngestionResult, RelationshipConfig

__all__ = [
    "IngestionResult",
    "RelationshipConfig",
]
