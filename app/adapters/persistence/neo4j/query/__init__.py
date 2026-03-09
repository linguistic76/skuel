"""
Query Infrastructure - Universal Query Models
==============================================

Infrastructure-level query models for all domains.
Provides Neo4j-first query capabilities with Pure Cypher as default.

This is THE single source of truth for query operations across SKUEL.
All domains consume these infrastructure components.

Key Components:
- cypher package: Modular Cypher query building (crud, semantic, domain, relationship, intelligence)
- SKUEL Query Templates: Curriculum-aware Pure Cypher patterns
- QueryPatterns: Generic graph traversal patterns for all services
- QueryIntent: Semantic query understanding
- IndexStrategy: Neo4j index optimization strategies
- QueryBuildRequest: Declarative query construction
- QueryPlan: Optimized query execution plans
- ValidationResult: Schema-aware query validation

**Pure Cypher Architecture (October 20, 2025)** - No APOC dependencies!

Usage Examples:

    # QueryPatterns - Generic graph patterns
    from adapters.persistence.neo4j.query import QueryPatterns

    # Get user's mastered knowledge
    query, params = QueryPatterns.get_user_entities(
        "Entity", user_uid,
        relationship="MASTERED",
        order_by="r.achieved_at DESC"
    )

    # Dynamic queries from model introspection
    from adapters.persistence.neo4j.query import build_search_query

    query, params = build_search_query(
        TaskPure,
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
- /docs/SKUEL_QUERY_USAGE_GUIDE.md - Template usage guide
- /docs/PURE_CYPHER_MIGRATION_SUMMARY.md - Migration summary
"""

# Internal implementation modules (marked with underscore prefix)
from core.constants import GraphDepth

from ._progressive_learning_queries import ProgressiveLearningQueries
from ._provenance_queries import ProvenanceQueries
from ._query_models import (
    IndexRecommendation,
    # Query strategies and intents
    IndexStrategy,
    # Query analysis models
    PropertyReference,
    QueryBuildRequest,
    # Query building models
    QueryConstraint,
    QueryElements,
    QueryIntent,
    QueryOptimizationResult,
    QueryPlan,
    QuerySort,
    ValidationIssue,
    ValidationResult,
    # Helper functions
    analyze_query_intent,
    create_filter_request,
    create_range_request,
    create_search_request,
)
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
    # Domain queries - dependencies
    build_choice_dependencies,
    # Domain-specific entity-with-context functions (reinstated January 2026)
    build_choice_with_context,
    # CRUD queries
    build_count_query,
    # Semantic queries
    build_cross_domain_bridges,
    build_domain_context_with_paths,
    build_entity_with_context,
    build_event_dependencies,
    build_event_with_context,
    build_get_by_field_query,
    build_goal_aligned_hybrid,
    build_goal_dependencies,
    build_goal_with_context,
    build_habit_dependencies,
    build_habit_with_context,
    build_hierarchical_context,
    build_hybrid_knowledge_search,
    build_impact_chain_query,
    build_knowledge_prerequisites,
    build_ku_with_context,
    build_list_query,
    build_metadata_aware_path_query,
    build_multi_domain_context,
    build_multi_relationship_count,
    build_normalized_centrality_query,
    build_optimized_ready_to_learn,
    build_prerequisite_chain,
    build_principle_dependencies,
    build_principle_with_context,
    build_registry_validated_query,
    build_relationship_count,
    build_relationship_traversal_query,
    build_relationship_uids_query,
    build_relationship_weight_stats_query,
    build_search_query,
    build_semantic_context,
    build_semantic_filter_query,
    build_semantic_traversal,
    build_simple_prerequisite_chain,
    build_task_dependencies,
    build_task_with_context,
    build_text_search_query,
    build_unmastered_prerequisite_chain,
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

# ApocQueryBuilder REMOVED - Pure Cypher migration (October 20, 2025)
# Use Pure Cypher UNWIND patterns for batch operations
# Use build_graph_context_query() for graph traversal
from .cypher_template import (
    CypherQuery,
    QueryOptimizationStrategy,
    SearchCriteria,
    TemplateRecommendation,
    TemplateSpec,
)

# Graph traversal with Pure Cypher
from .graph_traversal import build_graph_context_query

# Generic query patterns
from .query_patterns import QueryPatterns

# Pure Cypher schema DDL
from .schema_ddl import (
    build_create_constraint_ddl,
    build_create_index_ddl,
    build_drop_constraint_ddl,
    build_drop_index_ddl,
)

# Search boundary models — canonical location is core.models.search_models
from core.models.search_models import FacetSetRequest, SearchQueryRequest, SearchResultDTO
from .unified_query_builder import (
    # Individual builders (for advanced usage)
    ModelQueryBuilder,
    # Result type
    QueryResult,
    SemanticQueryBuilder,
    TemplateQueryBuilder,
    # THE SINGLE ENTRY POINT
    UnifiedQueryBuilder,
    query,
)

__all__ = [
    # ============================================================================
    # CONFIDENCE FILTERING (December 2025)
    # ============================================================================
    "CONFIDENCE_DEFAULTS",
    "ConfidenceMode",
    # ============================================================================
    # CYPHER TEMPLATES
    # ============================================================================
    "CypherQuery",
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
    "IndexRecommendation",
    "IndexStrategy",
    "ModelQueryBuilder",
    "ProgressiveLearningQueries",
    "PropertyReference",
    "ProvenanceQueries",
    "QueryBuildRequest",
    "QueryConstraint",
    "QueryElements",
    "QueryIntent",
    "QueryOptimizationResult",
    "QueryOptimizationStrategy",
    "QueryPatterns",
    "QueryPlan",
    "QueryResult",
    "QuerySort",
    "SearchCriteria",
    "SemanticQueryBuilder",
    "SemanticSimilarityQueries",
    "TemplateQueryBuilder",
    "TemplateRecommendation",
    "TemplateSpec",
    # ============================================================================
    # UNIFIED QUERY BUILDER - THE SINGLE ENTRY POINT
    # ============================================================================
    "UnifiedQueryBuilder",
    "ValidationIssue",
    "ValidationResult",
    "analyze_query_intent",
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
    # Domain queries - dependencies
    "build_choice_dependencies",
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
    "build_event_dependencies",
    "build_event_with_context",
    "build_get_by_field_query",
    "build_goal_aligned_hybrid",
    "build_goal_dependencies",
    "build_goal_with_context",
    # ============================================================================
    # PURE CYPHER GRAPH TRAVERSAL
    # ============================================================================
    "build_graph_context_query",
    "build_habit_dependencies",
    "build_habit_with_context",
    "build_hierarchical_context",
    "build_hybrid_knowledge_search",
    "build_impact_chain_query",
    "build_knowledge_prerequisites",
    "build_ku_with_context",
    "build_list_query",
    "build_metadata_aware_path_query",
    "build_multi_domain_context",
    "build_multi_fallback_confidence",
    "build_multi_relationship_count",
    "build_normalized_centrality_query",
    "build_optimized_ready_to_learn",
    "build_path_confidence_aggregation",
    "build_prerequisite_chain",
    "build_principle_dependencies",
    "build_principle_with_context",
    "build_registry_validated_query",
    "build_relationship_count",
    "build_relationship_traversal_query",
    "build_relationship_uids_query",
    "build_relationship_weight_stats_query",
    "build_search_query",
    "build_semantic_context",
    "build_semantic_filter_query",
    "build_semantic_traversal",
    "build_simple_prerequisite_chain",
    "build_task_dependencies",
    "build_task_with_context",
    "build_text_search_query",
    "build_unmastered_prerequisite_chain",
    "build_user_activity_query",
    "build_weighted_path_query",
    "convert_value_for_neo4j",
    # Convenience functions
    "count",
    "create_filter_request",
    "create_range_request",
    "create_search_request",
    "get_by",
    "get_filterable_fields",
    "get_supported_operators",
    "list_entities",
    "query",
    "search",
]
