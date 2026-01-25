"""
Neo4j-native bulk ingestion infrastructure.

This module provides generic patterns for bulk operations using Cypher templates,
completing the generic programming evolution by extending it to graph-native operations.
"""

from .bulk_ingestion import BulkIngestionEngine, IngestionResult
from .cypher_executor import CypherExecutor, CypherTemplate
from .vector_manager import Vector, VectorManager

__all__ = [
    "BulkIngestionEngine",
    "CypherExecutor",
    "CypherTemplate",
    "IngestionResult",
    "Vector",
    "VectorManager",
]
