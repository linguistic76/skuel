"""
Search Field Configuration
==========================

Shared search field configuration and types consumed by the domain search
services and SearchRouter (``SEARCH_FIELD_CONFIG``, ``SearchFieldConfig``, and the
field-accessor helpers).

The live search intelligence lives elsewhere, not here:
- Query understanding / faceting / ranking (Analog, CORE tier): ``SearchQueryParser``
  + Cypher property faceting + the unified ``score_*`` framework, in
  ``core/orchestrator/search_router.py``.
- Semantic intent + vector search (Digital, FULL tier): ``core/services/askesis/``
  and ``Neo4jVectorSearchService``.

The former unwired heuristic layer (``SearchIntelligenceService`` /
``QueryIntelligenceService``) was deleted 2026-08 as never-adopted (#983).
"""

__version__ = "1.0"

# Search field configuration
from core.services.search.config import (
    SEARCH_FIELD_CONFIG,
    SearchFieldConfig,
    get_array_fields,
    get_filter_fields,
    get_search_fields,
)

__all__ = [
    # Search field configuration
    "SEARCH_FIELD_CONFIG",
    "SearchFieldConfig",
    "get_array_fields",
    "get_filter_fields",
    "get_search_fields",
]
