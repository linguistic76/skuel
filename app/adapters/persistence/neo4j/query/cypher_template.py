"""
Cypher Query Optimization Strategy
==================================

Schema-aware optimization strategies for Cypher query planning.

The template models that used to live here (``CypherQuery``, ``TemplateSpec``,
``TemplateRecommendation``, ``SearchCriteria``) were deleted with the
``query_builders/`` package that consumed them (2026-08-17). ``GraphContextNode``
still annotates its ``optimization_strategy`` field with the enum below, so the
vocabulary survives its former registry.
"""

__version__ = "2.0"


from enum import Enum


class QueryOptimizationStrategy(Enum):
    """Optimization strategies based on available schema elements"""

    BASIC = "basic"  # No optimization
    INDEXED = "indexed"  # Use available indexes
    FULLTEXT = "fulltext"  # Use fulltext search
    UNIQUE_CONSTRAINT = "unique_constraint"  # Use unique lookups
    RELATIONSHIP_TRAVERSAL = "relationship_traversal"  # Optimize traversals


__all__ = ["QueryOptimizationStrategy"]
