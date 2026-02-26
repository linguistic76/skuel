"""
Cypher Query Generators - Modular Query Building for Neo4j
===========================================================

This package provides focused modules for different query types:

Modules:
- crud_queries: Dynamic CRUD and search operations
- semantic_queries: Semantic relationship traversal
- domain_queries: Domain dependencies and entity-with-context
- relationship_queries: Counting, batch operations, path queries
- intelligence_queries: Hybrid patterns, registry validation, weighted paths

Infrastructure Functions (January 2026):
- build_distinct_values_query: Get distinct field values (categories)
- build_hierarchy_query: Parent/child hierarchy traversal
- build_prerequisite_traversal_query: Prerequisite chains (both directions)
- build_user_progress_query: User mastery/progress data
- build_user_curriculum_query: User's curriculum entities

Usage:
    from core.models.query.cypher import build_search_query, build_text_search_query
    from core.models.query.cypher import build_task_dependencies, build_task_with_context
    from core.models.query.cypher import build_relationship_count, build_batch_relationship_exists
    from core.models.query.cypher import build_hybrid_knowledge_search, search, get_by

    # consolidation functions
    from core.models.query.cypher import (
        build_distinct_values_query,
        build_hierarchy_query,
        build_prerequisite_traversal_query,
        build_user_progress_query,
        build_user_curriculum_query,
    )
"""

# Shared types
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
    build_list_query,
    build_prerequisite_traversal_query,
    build_relationship_traversal_query,
    build_search_query,
    build_text_search_query,
    build_user_curriculum_query,
    build_user_progress_query,
    convert_value_for_neo4j,
    get_filterable_fields,
    get_supported_operators,
)

# Domain queries - dependencies and entity-with-context
from .domain_queries import (
    # Domain dependencies
    build_choice_dependencies,
    # Domain-specific entity-with-context functions (reinstated January 2026)
    build_choice_with_context,
    # Time-based queries (January 2026)
    build_due_soon_query,
    # Entity with context - generic engine
    build_entity_with_context,
    build_event_dependencies,
    build_event_with_context,
    build_goal_dependencies,
    build_goal_with_context,
    build_habit_dependencies,
    build_habit_with_context,
    build_knowledge_prerequisites,
    build_ku_with_context,
    # Prerequisite queries
    build_multi_domain_context,
    # Time-based queries (January 2026)
    build_overdue_query,
    build_principle_dependencies,
    build_principle_with_context,
    build_simple_prerequisite_chain,
    build_task_dependencies,
    build_task_with_context,
    build_unmastered_prerequisite_chain,
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

# Post-query processors for calculated fields (January 2026)
from .post_processors import (
    PROCESSOR_REGISTRY,
    apply_processor,
    calculate_habit_streak_summary,
    calculate_milestone_progress,
    calculate_task_status_summary,
    get_processor,
)

# Relationship queries - counting, batch operations, path queries
from .relationship_queries import (
    build_batch_get_related_with_filters,
    build_batch_relationship_count,
    build_batch_relationship_exists,
    build_batch_relationship_exists_with_filters,
    build_metadata_aware_path_query,
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
    build_semantic_traversal,
)

__all__ = [
    # Types
    "RelationshipSpec",
    "T",
    # Array search queries
    "build_array_any_match_query",
    "build_array_contains_query",
    "build_batch_get_related_with_filters",
    "build_batch_relationship_count",
    "build_batch_relationship_exists",
    "build_batch_relationship_exists_with_filters",
    "build_bidirectional_impact_query",
    "build_choice_dependencies",
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
    "build_event_dependencies",
    "build_event_with_context",
    "build_get_by_field_query",
    "build_goal_aligned_hybrid",
    "build_goal_dependencies",
    "build_goal_with_context",
    "build_graph_aware_search_query",
    "build_habit_dependencies",
    "build_habit_with_context",
    "build_hierarchical_context",
    "build_hierarchy_query",
    # Intelligence queries - hybrid
    "build_hybrid_knowledge_search",
    "build_impact_chain_query",
    # Domain queries - dependencies
    "build_knowledge_prerequisites",
    "build_ku_with_context",
    "build_list_query",
    "build_metadata_aware_path_query",
    "build_multi_domain_context",
    "build_multi_relationship_count",
    "build_normalized_centrality_query",
    "build_optimized_ready_to_learn",
    # Time-based queries (January 2026)
    "build_overdue_query",
    "build_prerequisite_chain",
    "build_prerequisite_traversal_query",
    "build_principle_dependencies",
    "build_principle_with_context",
    # Intelligence queries - registry
    "build_registry_validated_query",
    # Relationship queries
    "build_relationship_count",
    "build_relationship_traversal_query",
    "build_relationship_uids_query",
    "build_relationship_weight_stats_query",
    # CRUD queries
    "build_search_query",
    # Semantic queries
    "build_semantic_context",
    "build_semantic_filter_query",
    "build_semantic_traversal",
    # Domain queries - prerequisites
    "build_simple_prerequisite_chain",
    "build_task_dependencies",
    "build_task_with_context",
    "build_text_search_query",
    "build_unmastered_prerequisite_chain",
    # Meta-service queries
    "build_user_activity_query",
    "build_user_curriculum_query",
    "build_user_progress_query",
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
    # Post-query processors (January 2026)
    "PROCESSOR_REGISTRY",
    "apply_processor",
    "calculate_habit_streak_summary",
    "calculate_milestone_progress",
    "calculate_task_status_summary",
    "get_processor",
]
