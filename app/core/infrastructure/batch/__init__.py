"""
Batch Operations Infrastructure
===============================

Centralized helpers for efficient UNWIND-based batch Neo4j operations.

This module consolidates duplicate batch patterns used across:
- UniversalNeo4jBackend (relationship CRUD)
- CypherGenerator (query generation)
- 12 relationship services (batch creation)

Core Principle: "One query builder, many consumers"
"""

from core.infrastructure.batch.batch_cypher_builder import (
    BatchCypherBuilder,
    BatchQueryResult,
)

__all__ = [
    "BatchCypherBuilder",
    "BatchQueryResult",
]
