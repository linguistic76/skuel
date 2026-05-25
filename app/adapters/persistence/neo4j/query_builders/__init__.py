"""
Query Building Services
=======================

Decomposed query building system with focused sub-services.

Architecture (Decomposition Complete):
- QueryOptimizer: Index-aware optimization
- QueryTemplateRegistry: Template management
- QueryValidator: Query validation
- FacetedQueryBuilder: Faceted search
- GraphContextBuilder: Graph traversal queries

All sub-services can be used independently or via the QueryBuilder facade.
"""

from adapters.persistence.neo4j.query_builders.faceted_query_builder import FacetedQueryBuilder
from adapters.persistence.neo4j.query_builders.graph_context_builder import GraphContextBuilder
from adapters.persistence.neo4j.query_builders.query_optimizer import QueryOptimizer
from adapters.persistence.neo4j.query_builders.query_template_registry import QueryTemplateRegistry
from adapters.persistence.neo4j.query_builders.query_validator import QueryValidator

__all__ = [
    "FacetedQueryBuilder",
    "GraphContextBuilder",
    "QueryOptimizer",
    "QueryTemplateRegistry",
    "QueryValidator",
]
