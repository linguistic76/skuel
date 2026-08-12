"""
Cypher Query Generators - Modular Query Building for Neo4j
===========================================================

This package provides focused modules for different query types:

Modules:
- crud_queries: Dynamic CRUD and search operations
- semantic_queries: Semantic relationship traversal
- domain_queries: Entity-with-context and prerequisite chains
- relationship_queries: Counting, batch operations, path queries
- intelligence_queries: Hybrid patterns, registry validation, weighted paths

Infrastructure Functions (January 2026):
- build_distinct_values_query: Get distinct field values (categories)
- build_hierarchy_query: Parent/child hierarchy traversal
- build_prerequisite_traversal_query: Prerequisite chains (both directions)
- build_prerequisite_chain_query: Flat, distance-annotated prerequisite chain (min-distance deduped)

Usage:
    from adapters.persistence.neo4j.query.cypher import build_search_query, build_text_search_query
    from adapters.persistence.neo4j.query.cypher import build_task_with_context
    from adapters.persistence.neo4j.query.cypher import build_relationship_count
    from adapters.persistence.neo4j.query.cypher import build_hybrid_knowledge_search, search, get_by

    # consolidation functions
    from adapters.persistence.neo4j.query.cypher import (
        build_distinct_values_query,
        build_hierarchy_query,
        build_prerequisite_traversal_query,
    )
"""

# Shared types
from ._helpers import CURRICULUM_COMPOSITION_EDGES
from ._types import RelationshipSpec, T

# Context query generator - registry-driven context queries (January 2026)
from .context_query_generator import (
    generate_context_query,
    get_available_relationships,
    get_relationship_details,
)

# CRUD queries - dynamic query generation
from .crud_queries import (
    build_array_any_match_query,
    build_array_contains_query,
    build_count_query,
    build_distinct_values_query,
    build_get_by_field_query,
    build_graph_aware_search_query,
    build_hierarchy_query,
    build_knowledge_read_clause,
    build_list_query,
    build_prerequisite_chain_query,
    build_prerequisite_traversal_query,
    build_publication_clause,
    build_relationship_traversal_query,
    build_search_query,
    build_search_visibility_clause,
    build_text_search_query,
    convert_value_for_neo4j,
    get_filterable_fields,
    get_supported_operators,
)

# Domain queries - entity-with-context and prerequisite chains
from .domain_queries import (
    # Time-based queries (January 2026)
    build_active_query,
    # Domain-specific entity-with-context functions (reinstated January 2026)
    build_choice_with_context,
    # Time-based queries (January 2026)
    build_due_soon_query,
    # Entity with context - generic engine
    build_entity_with_context,
    build_event_with_context,
    build_goal_with_context,
    build_habit_with_context,
    build_ku_with_context,
    # Time-based queries (January 2026)
    build_overdue_query,
    build_principle_with_context,
    # Prerequisite queries
    build_simple_prerequisite_chain,
    build_task_with_context,
    # Meta-service queries
    build_user_activity_query,
)

# Intelligence queries - hybrid patterns, registry validation, weighted paths
from .intelligence_queries import (
    # Registry-validated queries
    build_bidirectional_impact_query,
    # Hybrid queries
    build_goal_aligned_hybrid,
    build_hybrid_knowledge_search,
    build_impact_chain_query,
    # Weight queries
    build_normalized_centrality_query,
    build_optimized_ready_to_learn,
    build_registry_validated_query,
    build_relationship_weight_stats_query,
    build_weighted_path_query,
    # Convenience functions
    count,
    get_by,
    list_entities,
    search,
)

# Relationship filter fragments - graph-aware faceted search WHERE clauses
from .relationship_filter_fragments import build_relationship_filter_fragments

# Relationship queries - counting, batch operations, path queries
from .relationship_queries import (
    build_batch_get_related_with_filters,
    build_batch_relationship_count,
    build_batch_relationship_exists,
    build_batch_relationship_exists_with_filters,
    build_multi_relationship_count,
    build_relationship_count,
    build_relationship_uids_query,
)

# Semantic queries - knowledge graph traversal
from .semantic_queries import (
    build_cross_domain_bridges,
    build_domain_context_with_paths,
    build_hierarchical_context,
    build_prerequisite_chain,
    build_semantic_context,
    build_semantic_filter_query,
    build_semantic_merge,
    build_semantic_traversal,
)

__all__ = [
    # Types
    "RelationshipSpec",
    "T",
    # Array search queries
    "build_active_query",
    "build_array_any_match_query",
    "build_array_contains_query",
    "build_batch_get_related_with_filters",
    "build_batch_relationship_count",
    "build_batch_relationship_exists",
    "build_batch_relationship_exists_with_filters",
    "build_bidirectional_impact_query",
    "build_choice_with_context",
    "build_count_query",
    "build_cross_domain_bridges",
    # consolidation queries (January 2026)
    "build_distinct_values_query",
    "build_domain_context_with_paths",
    # Time-based queries (January 2026)
    "build_due_soon_query",
    # Domain queries - entity with context
    "build_entity_with_context",
    "build_event_with_context",
    "build_get_by_field_query",
    "build_goal_aligned_hybrid",
    "build_goal_with_context",
    "build_graph_aware_search_query",
    "build_habit_with_context",
    "build_hierarchical_context",
    "build_hierarchy_query",
    "build_prerequisite_chain_query",
    # Intelligence queries - hybrid
    "build_hybrid_knowledge_search",
    "build_impact_chain_query",
    "build_ku_with_context",
    "build_list_query",
    "build_multi_relationship_count",
    "build_normalized_centrality_query",
    "build_optimized_ready_to_learn",
    # Time-based queries (January 2026)
    "build_overdue_query",
    "build_prerequisite_chain",
    "build_prerequisite_traversal_query",
    "build_principle_with_context",
    # Intelligence queries - registry
    "build_registry_validated_query",
    # Relationship queries
    "build_relationship_count",
    # Relationship filter fragments (graph-aware faceted search)
    "build_relationship_filter_fragments",
    "build_relationship_traversal_query",
    "build_relationship_uids_query",
    "build_relationship_weight_stats_query",
    # CRUD queries
    "build_search_query",
    # Semantic queries
    "build_semantic_context",
    "build_semantic_filter_query",
    "CURRICULUM_COMPOSITION_EDGES",
    "build_knowledge_read_clause",
    "build_publication_clause",
    "build_search_visibility_clause",
    "build_semantic_merge",
    "build_semantic_traversal",
    # Domain queries - prerequisites
    "build_simple_prerequisite_chain",
    "build_task_with_context",
    "build_text_search_query",
    # Meta-service queries
    "build_user_activity_query",
    # Intelligence queries - weights
    "build_weighted_path_query",
    "convert_value_for_neo4j",
    "count",
    "get_by",
    "get_filterable_fields",
    "get_supported_operators",
    "list_entities",
    # Convenience functions
    "search",
    # Context query generator (January 2026)
    "generate_context_query",
    "get_available_relationships",
    "get_relationship_details",
]
