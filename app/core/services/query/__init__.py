"""
Query Building Services
=======================

Decomposed query building system with focused sub-services.

Architecture (Decomposition Complete):
- QueryOptimizer: Index-aware optimization
- QueryTemplateManager: Template management
- QueryValidator: Query validation
- FacetedQueryBuilder: Faceted search
- GraphContextBuilder: Graph traversal queries

All sub-services can be used independently or via the QueryBuilder facade.
"""

from core.services.query.faceted_query_builder import FacetedQueryBuilder
from core.services.query.graph_context_builder import GraphContextBuilder
from core.services.query.query_optimizer import QueryOptimizer
from core.services.query.query_template_manager import QueryTemplateManager
from core.services.query.query_validator import QueryValidator

__all__ = [
    "FacetedQueryBuilder",
    "GraphContextBuilder",
    "QueryOptimizer",
    "QueryTemplateManager",
    "QueryValidator",
]
