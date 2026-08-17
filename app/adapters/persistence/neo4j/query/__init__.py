"""
Query Infrastructure - Universal Query Models
==============================================

Infrastructure-level query models for all domains.
Provides Neo4j-first query capabilities with Pure Cypher as default.

This is THE single source of truth for query operations across SKUEL.
All domains consume these infrastructure components.

Architecture — Two Layers
--------------------------

The query system is a fluent facade over a package of Cypher-building functions::

    UnifiedQueryBuilder  ← fluent entry point
    └── ModelQueryBuilder  → cypher/ build_* functions (list/search/count)

Callers that need a shape the facade does not cover call the ``cypher/``
``build_*`` functions directly — that is the documented second path, not a
fallback.

Supporting infrastructure (leaf-level utilities, NOT alternative query paths):

- ``confidence_filter.py`` — Cypher clause fragments for confidence filtering.
  Consumed by query builders, not by services directly.
- ``convert_value_for_neo4j()`` — Python→Neo4j type boundary (enums, datetimes).
  Complements Pydantic (HTTP boundary), does NOT duplicate it.

Key Components:
- cypher package: Modular Cypher query building (crud, semantic, domain, relationship, intelligence)
- QueryIntent: Semantic query understanding
- QueryOptimizationStrategy: Schema-aware optimization vocabulary

**Pure Cypher Architecture (October 20, 2025)** - No APOC dependencies!

Usage Examples:

    # Dynamic queries from model introspection
    from adapters.persistence.neo4j.query import build_search_query

    query, params = build_search_query(
        Task,
        {'priority': 'high', 'due_date__gte': date.today()}
    )

    # Semantic relationship traversal
    from adapters.persistence.neo4j.query import build_semantic_context

    query, params = build_semantic_context(
        node_uid="ku.python_basics",
        semantic_types=[SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING],
        GraphDepth.NEIGHBORHOOD
    )

    # Graph context traversal (Pure Cypher variable-length patterns)
    from adapters.persistence.neo4j.query.graph_traversal import build_graph_context_query
    from core.models.query_types import QueryIntent

    query = build_graph_context_query("task.123", QueryIntent.HIERARCHICAL, depth=GraphDepth.NEIGHBORHOOD)

See Documentation:
- /docs/SKUEL_QUERY_DESIGN.md - Pure Cypher query design
- /docs/PURE_CYPHER_MIGRATION_SUMMARY.md - Migration summary
- /docs/intelligence/PEDAGOGICAL_QUESTIONS.md - Pedagogical questions reference
"""

# Internal implementation modules (marked with underscore prefix)
from core.constants import GraphDepth

# Boundary types — canonical location is core.models.query_types. Re-exported here
# because callers reach the query package for them (previously via _query_models,
# deleted 2026-08-17); `__all__` promises the name.
from core.models.query_types import QueryIntent

# Search boundary models — canonical location is core.models.search_models
from core.models.search_models import FacetSetRequest, SearchQueryRequest, SearchResultDTO

from ._progressive_learning_queries import ProgressiveLearningQueries
from ._provenance_queries import ProvenanceQueries
from ._semantic_similarity_queries import SemanticSimilarityQueries

# Confidence filtering utilities (December 2025)
from .confidence_filter import (
    CONFIDENCE_DEFAULTS,
    ConfidenceMode,
    build_confidence_clause,
    build_confidence_field,
    build_multi_fallback_confidence,
    build_path_confidence_aggregation,
)

# Cypher query functions - modular package (January 2026)
from .cypher import (
    # Relationship queries
    build_batch_get_related_with_filters,
    build_batch_relationship_count,
    build_batch_relationship_exists,
    build_batch_relationship_exists_with_filters,
    # Intelligence queries
    build_bidirectional_impact_query,
    # Domain-specific entity-with-context functions (reinstated January 2026)
    build_choice_with_context,
    # CRUD queries
    build_count_query,
    # Semantic queries
    build_cross_domain_bridges,
    build_domain_context_with_paths,
    build_entity_with_context,
    build_event_with_context,
    build_get_by_field_query,
    build_goal_aligned_hybrid,
    build_goal_with_context,
    build_habit_with_context,
    build_hierarchical_context,
    build_hybrid_knowledge_search,
    build_impact_chain_query,
    build_ku_with_context,
    build_list_query,
    build_multi_relationship_count,
    build_normalized_centrality_query,
    build_optimized_ready_to_learn,
    build_prerequisite_chain,
    build_principle_with_context,
    build_registry_validated_query,
    build_relationship_count,
    build_relationship_filter_fragments,
    build_relationship_traversal_query,
    build_relationship_uids_query,
    build_relationship_weight_stats_query,
    build_search_query,
    build_semantic_context,
    build_semantic_filter_query,
    build_semantic_merge,
    build_semantic_traversal,
    build_simple_prerequisite_chain,
    build_task_with_context,
    build_text_search_query,
    build_user_activity_query,
    build_weighted_path_query,
    convert_value_for_neo4j,
    count,
    # Context query generator (January 2026)
    generate_context_query,
    get_available_relationships,
    get_by,
    get_filterable_fields,
    get_relationship_details,
    get_supported_operators,
    list_entities,
    search,
)

# No APOC in the query layer. There was never an ApocQueryBuilder class to remove —
# it was a 2025 design-notes proposal that shipped as pure Cypher instead.
# Use Pure Cypher UNWIND patterns for batch operations
# Use build_graph_context_query() for graph traversal
from .cypher_template import QueryOptimizationStrategy

# Graph traversal with Pure Cypher
from .graph_traversal import build_graph_context_query

# Pure Cypher schema DDL
from .schema_ddl import (
    build_create_constraint_ddl,
    build_create_index_ddl,
    build_drop_constraint_ddl,
    build_drop_index_ddl,
)
from .unified_query_builder import (
    # Individual builder (for advanced usage)
    ModelQueryBuilder,
    # Result type
    QueryResult,
    # THE FLUENT ENTRY POINT
    UnifiedQueryBuilder,
    query,
)

__all__ = [
    # ============================================================================
    # CONFIDENCE FILTERING (December 2025)
    # ============================================================================
    "CONFIDENCE_DEFAULTS",
    "ConfidenceMode",
    "GraphDepth",  # Imported from core.constants for convenience
    # ============================================================================
    # SEARCH BOUNDARY MODELS
    # ============================================================================
    "FacetSetRequest",
    "SearchQueryRequest",
    "SearchResultDTO",
    # ============================================================================
    # QUERY MODELS & STRATEGIES
    # ============================================================================
    "ModelQueryBuilder",
    "ProgressiveLearningQueries",
    "ProvenanceQueries",
    "QueryIntent",
    "QueryOptimizationStrategy",
    "QueryResult",
    "SemanticSimilarityQueries",
    # ============================================================================
    # UNIFIED QUERY BUILDER - THE SINGLE ENTRY POINT
    # ============================================================================
    "UnifiedQueryBuilder",
    # Relationship queries
    "build_batch_get_related_with_filters",
    "build_batch_relationship_count",
    "build_batch_relationship_exists",
    "build_batch_relationship_exists_with_filters",
    # Intelligence queries
    "build_bidirectional_impact_query",
    # Context query generator (January 2026)
    "generate_context_query",
    "get_available_relationships",
    "get_relationship_details",
    # Domain queries - entity with context
    "build_choice_with_context",
    "build_confidence_clause",
    "build_confidence_field",
    # ============================================================================
    # CYPHER QUERY FUNCTIONS - Modular Package (January 2026)
    # ============================================================================
    # CRUD queries
    "build_count_query",
    # ============================================================================
    # PURE CYPHER SCHEMA DDL
    # ============================================================================
    "build_create_constraint_ddl",
    "build_create_index_ddl",
    # Semantic queries
    "build_cross_domain_bridges",
    "build_domain_context_with_paths",
    "build_drop_constraint_ddl",
    "build_drop_index_ddl",
    "build_entity_with_context",
    "build_event_with_context",
    "build_get_by_field_query",
    "build_goal_aligned_hybrid",
    "build_goal_with_context",
    # ============================================================================
    # PURE CYPHER GRAPH TRAVERSAL
    # ============================================================================
    "build_graph_context_query",
    "build_habit_with_context",
    "build_hierarchical_context",
    "build_hybrid_knowledge_search",
    "build_impact_chain_query",
    "build_ku_with_context",
    "build_list_query",
    "build_multi_fallback_confidence",
    "build_multi_relationship_count",
    "build_normalized_centrality_query",
    "build_optimized_ready_to_learn",
    "build_path_confidence_aggregation",
    "build_prerequisite_chain",
    "build_principle_with_context",
    "build_registry_validated_query",
    "build_relationship_count",
    "build_relationship_filter_fragments",
    "build_relationship_traversal_query",
    "build_relationship_uids_query",
    "build_relationship_weight_stats_query",
    "build_search_query",
    "build_semantic_context",
    "build_semantic_filter_query",
    "build_semantic_merge",
    "build_semantic_traversal",
    "build_simple_prerequisite_chain",
    "build_task_with_context",
    "build_text_search_query",
    "build_user_activity_query",
    "build_weighted_path_query",
    "convert_value_for_neo4j",
    # Convenience functions
    "count",
    "get_by",
    "get_filterable_fields",
    "get_supported_operators",
    "list_entities",
    "query",
    "search",
]
