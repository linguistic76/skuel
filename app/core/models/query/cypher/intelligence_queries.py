"""
Intelligence Queries - Hybrid, Registry-Validated, and Weight Queries
======================================================================

Cypher query builders for intelligent search patterns combining property
filters with graph traversal, registry validation, and weighted path finding.

Hybrid Queries:
- build_hybrid_knowledge_search: Property filters + graph patterns
- build_optimized_ready_to_learn: Ready-to-learn with property filtering
- build_goal_aligned_hybrid: Goal alignment with property filters

Registry-Validated Queries:
- build_registry_validated_query: Validates relationships against registry
- build_impact_chain_query: Trace impact chains between domains
- build_bidirectional_impact_query: Find upstream/downstream impacts

Weight Normalization Queries:
- build_weighted_path_query: Weighted path finding
- build_normalized_centrality_query: Degree centrality with normalization
- build_relationship_weight_stats_query: Analyze weight distributions

Convenience Functions:
- search: Shorthand for search queries
- get_by: Shorthand for get by field
- list_entities: Shorthand for listing
- count: Shorthand for counting
"""

from typing import Any, TypeVar

T = TypeVar("T")


# ============================================================================
# HYBRID QUERY PATTERNS - Optimized Property + Graph Combinations
# ============================================================================


def build_hybrid_knowledge_search(
    property_filters: dict[str, Any],
    graph_patterns: dict[str, str],
    user_uid: str,
    limit: int = 20,
    offset: int = 0,
    query_text: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Build optimized hybrid query combining property filters and graph patterns.

    **Core Optimization Pattern:**
    1. Property filters FIRST (fast indexed lookups)
    2. WITH clause to pass filtered results
    3. Graph patterns on filtered set (efficient traversal)

    Args:
        property_filters: Property-based filters (sel_category, learning_level, etc.)
        graph_patterns: Graph patterns as dict (pattern_name -> cypher_condition)
        user_uid: User identifier for personalized patterns
        limit: Maximum results
        offset: Pagination offset
        query_text: Optional text search

    Returns:
        Tuple of (cypher_query, parameters)

    Performance:
        - Property filters use indexes (O(log n) lookup)
        - Graph traversal on filtered set (10-100x smaller)
        - Overall: O(log n) + O(filtered_edges) vs O(all_edges)
    """
    cypher_parts = ["MATCH (ku:Ku)"]
    params: dict[str, Any] = {
        "user_uid": user_uid,
        "limit": limit,
        "offset": offset,
    }

    # Phase 1: Property Filters (FAST - uses indexes)
    property_conditions = []

    for key, value in property_filters.items():
        param_name = f"prop_{key}"
        property_conditions.append(f"ku.{key} = ${param_name}")
        params[param_name] = value

    # Add text search to property filters (indexed)
    if query_text:
        property_conditions.append(
            "(ku.title CONTAINS $query_text OR ku.content CONTAINS $query_text)"
        )
        params["query_text"] = query_text

    # Add property WHERE clause if we have filters
    if property_conditions:
        cypher_parts.append("WHERE " + " AND ".join(property_conditions))

    # Phase 2: WITH clause to pass filtered results (KEY for optimization)
    if graph_patterns:
        cypher_parts.append("WITH ku")

    # Phase 3: Graph Patterns (operates on filtered candidates)
    if graph_patterns:
        # Each pattern is a complete condition (may include EXISTS, NOT EXISTS, etc.)
        graph_conditions = [
            f"({pattern_cypher.strip()})" for pattern_cypher in graph_patterns.values()
        ]

        if graph_conditions:
            cypher_parts.append("WHERE " + " AND ".join(graph_conditions))

    # Phase 4: Return with pagination
    cypher_parts.extend(
        ["", "RETURN ku", "ORDER BY ku.created_at DESC", "SKIP $offset", "LIMIT $limit"]
    )

    cypher = "\n".join(cypher_parts)
    return cypher, params


def build_optimized_ready_to_learn(
    user_uid: str,
    category: str | None = None,
    level: str | None = None,
    limit: int = 10,
    min_confidence: float = 0.7,
) -> tuple[str, dict[str, Any]]:
    """
    Build optimized 'ready to learn' query demonstrating hybrid pattern.

    **Optimization Strategy:**
    - Filter by category/level FIRST (indexed properties)
    - THEN check prerequisites via graph pattern (on smaller set)

    This is 10-100x faster than checking prerequisites on ALL knowledge units.

    Args:
        user_uid: User identifier
        category: Optional SEL category filter (e.g., "self_awareness")
        level: Optional learning level filter (e.g., "beginner")
        limit: Maximum results
        min_confidence: Minimum prerequisite confidence threshold

    Returns:
        Tuple of (cypher_query, parameters)
    """
    params: dict[str, Any] = {
        "user_uid": user_uid,
        "limit": limit,
        "min_confidence": min_confidence,
    }

    # Build property filters (indexed lookups)
    property_filters = []
    if category:
        property_filters.append("ku.sel_category = $category")
        params["category"] = category
    if level:
        property_filters.append("ku.learning_level = $level")
        params["level"] = level

    # Build WHERE clause for properties
    property_where = " AND ".join(property_filters) if property_filters else "true"

    cypher = f"""
    // Phase 1: Property filters (FAST - indexed)
    MATCH (ku:Ku)
    WHERE {property_where}

    // Phase 2: WITH to pass filtered results
    WITH ku

    // Phase 3: Graph patterns on filtered set
    WHERE NOT EXISTS {{
        // Check prerequisites (relationship traversal)
        MATCH (ku)-[r:REQUIRES_KNOWLEDGE]->(prereq:Ku)
        WHERE r.confidence >= $min_confidence
          AND NOT EXISTS {{
            MATCH (user:User {{uid: $user_uid}})-[:MASTERED]->(prereq)
          }}
    }}
    AND NOT EXISTS {{
        // Not already mastered
        MATCH (user:User {{uid: $user_uid}})-[:MASTERED]->(ku)
    }}

    // Count what this unlocks (useful for prioritization)
    OPTIONAL MATCH (ku)-[:ENABLES_LEARNING]->(unlocked:Ku)
    WHERE NOT EXISTS {{
        MATCH (user:User {{uid: $user_uid}})-[:MASTERED]->(unlocked)
    }}

    WITH ku, count(DISTINCT unlocked) as unlocks_count

    RETURN ku, unlocks_count
    ORDER BY unlocks_count DESC, ku.created_at DESC
    LIMIT $limit
    """

    return cypher.strip(), params


def build_goal_aligned_hybrid(
    user_uid: str,
    content_type: str | None = None,
    learning_level: str | None = None,
    only_active_goals: bool = True,
    limit: int = 10,
) -> tuple[str, dict[str, Any]]:
    """
    Build hybrid query for goal-aligned knowledge with property filters.

    **Hybrid Pattern:**
    - Property filters: content_type, learning_level (indexed)
    - Graph pattern: goal alignment via relationships

    Args:
        user_uid: User identifier
        content_type: Optional content type filter (e.g., "article", "video")
        learning_level: Optional learning level filter
        only_active_goals: Only consider active/in_progress goals
        limit: Maximum results

    Returns:
        Tuple of (cypher_query, parameters)
    """
    params: dict[str, Any] = {
        "user_uid": user_uid,
        "limit": limit,
    }

    # Build property filters
    property_filters = []
    if content_type:
        property_filters.append("ku.content_type = $content_type")
        params["content_type"] = content_type
    if learning_level:
        property_filters.append("ku.learning_level = $learning_level")
        params["learning_level"] = learning_level

    # Goal status filter
    goal_status_filter = "goal.status IN ['active', 'in_progress']" if only_active_goals else "true"

    # Build WHERE clause
    property_where = " AND ".join(property_filters) if property_filters else "true"

    cypher = f"""
    // Start with user's goals
    MATCH (user:User {{uid: $user_uid}})-[:PURSUING_GOAL]->(goal:Goal)
    WHERE {goal_status_filter}

    // Find knowledge required by goals
    MATCH (goal)-[:REQUIRES_KNOWLEDGE]->(ku:Ku)

    // Apply property filters (indexed)
    WHERE {property_where}
      AND NOT EXISTS {{
        MATCH (user)-[:MASTERED]->(ku)
      }}

    // Aggregate by knowledge unit
    WITH ku, collect(DISTINCT goal.uid) as supporting_goal_uids

    // Calculate alignment score
    WITH ku,
         supporting_goal_uids,
         size(supporting_goal_uids) * 0.25 as alignment_score

    RETURN ku,
           supporting_goal_uids,
           size(supporting_goal_uids) as goal_count,
           CASE WHEN alignment_score > 1.0 THEN 1.0 ELSE alignment_score END as alignment_score
    ORDER BY alignment_score DESC, goal_count DESC
    LIMIT $limit
    """

    return cypher.strip(), params


# ============================================================================
# REGISTRY-VALIDATED QUERIES
# ============================================================================


def build_registry_validated_query(
    source_label: str,
    target_label: str,
    relationship_type: str,
    source_uid: str | None = None,
    target_uid: str | None = None,
    properties: dict[str, Any] | None = None,
    return_properties: list[str] | None = None,
    limit: int = 100,
) -> tuple[str, dict[str, Any]]:
    """
    Build a Cypher query with RelationshipRegistry validation.

    This method validates the relationship type against the registry BEFORE
    generating the query, ensuring only valid relationships are queried.
    Raises ValueError if the relationship is invalid for the source domain.

    Args:
        source_label: Source node label (e.g., "Task", "Goal")
        target_label: Target node label (e.g., "Ku", "Habit")
        relationship_type: Relationship type to query (e.g., "APPLIES_KNOWLEDGE")
        source_uid: Optional source node UID filter
        target_uid: Optional target node UID filter
        properties: Optional relationship property filters
        return_properties: Optional list of node properties to return
        limit: Maximum results (default 100)

    Returns:
        Tuple of (cypher_query, parameters)

    Raises:
        ValueError: If relationship_type is not valid for source_label
    """
    from core.models.relationship_registry import (
        get_relationship_metadata,
        get_valid_relationships,
        validate_relationship,
    )

    # Validate relationship against registry
    if not validate_relationship(source_label, relationship_type):
        valid_rels = list(get_valid_relationships(source_label).keys())
        raise ValueError(
            f"Invalid relationship '{relationship_type}' for {source_label}. "
            f"Valid relationships: {valid_rels}"
        )

    # Get relationship spec for direction awareness
    spec = get_relationship_metadata(source_label, relationship_type)
    if not spec:
        raise ValueError(f"Could not get metadata for {source_label}.{relationship_type}")

    # Validate target label matches spec
    if spec.target_labels and target_label not in spec.target_labels:
        raise ValueError(
            f"Invalid target '{target_label}' for {source_label}.{relationship_type}. "
            f"Valid targets: {spec.target_labels}"
        )

    # Build direction pattern
    if spec.direction == "incoming":
        direction_pattern = f"<-[r:{relationship_type}]-"
    elif spec.direction == "both":
        direction_pattern = f"-[r:{relationship_type}]-"
    else:  # outgoing
        direction_pattern = f"-[r:{relationship_type}]->"

    # Build WHERE clauses
    where_clauses = []
    params: dict[str, Any] = {"limit": limit}

    if source_uid:
        where_clauses.append("source.uid = $source_uid")
        params["source_uid"] = source_uid

    if target_uid:
        where_clauses.append("target.uid = $target_uid")
        params["target_uid"] = target_uid

    # Build relationship property filters
    if properties:
        for prop_key, prop_value in properties.items():
            # Handle operators (e.g., score__gte)
            if "__" in prop_key:
                field, op = prop_key.rsplit("__", 1)
                param_name = f"prop_{field}"
                params[param_name] = prop_value

                op_map = {
                    "gt": ">",
                    "gte": ">=",
                    "lt": "<",
                    "lte": "<=",
                    "ne": "<>",
                }
                if op in op_map:
                    where_clauses.append(f"r.{field} {op_map[op]} ${param_name}")
                elif op == "contains":
                    where_clauses.append(f"r.{field} CONTAINS ${param_name}")
            else:
                param_name = f"prop_{prop_key}"
                params[param_name] = prop_value
                where_clauses.append(f"r.{prop_key} = ${param_name}")

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Build RETURN clause
    if return_properties:
        return_fields = ", ".join([f"target.{p} as {p}" for p in return_properties])
        return_clause = f"RETURN source.uid as source_uid, target.uid as target_uid, {return_fields}, properties(r) as relationship_properties"
    else:
        return_clause = "RETURN source, target, properties(r) as relationship_properties"

    cypher = f"""
    MATCH (source:{source_label}){direction_pattern}(target:{target_label})
    {where_clause}
    {return_clause}
    LIMIT $limit
    """

    return cypher.strip(), params


def build_impact_chain_query(
    start_uid: str,
    start_label: str,
    end_label: str,
    max_depth: int = 4,
    relationship_filter: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Build query to trace impact chains between domains.

    Finds all paths from a source entity to entities of a target domain,
    using the RelationshipRegistry to discover valid connecting relationships.

    Use cases:
    - How does completing a Task impact Goals?
    - How does a Choice ripple through Habits and Tasks?
    - What Knowledge enables which Goals?

    Args:
        start_uid: Starting entity UID
        start_label: Starting entity label (e.g., "Task", "Choice")
        end_label: Target domain label (e.g., "Goal", "Ku")
        max_depth: Maximum path length (default 4)
        relationship_filter: Optional list of specific relationships to traverse

    Returns:
        Tuple of (cypher_query, parameters)
    """
    from core.models.relationship_registry import get_valid_relationships

    # Discover valid relationships for this path
    if relationship_filter:
        rel_types = relationship_filter
    else:
        # Get all outgoing relationships from source domain
        source_rels = get_valid_relationships(start_label)
        rel_types = list(source_rels.keys())

        # Also check intermediate domains for multi-hop paths
        intermediate_rels = [
            "SUPPORTS_GOAL",
            "CONTRIBUTES_TO_GOAL",
            "REQUIRES_KNOWLEDGE",
            "APPLIES_KNOWLEDGE",
            "REINFORCES_HABIT",
            "EMBODIES_PRINCIPLE",
            "INFORMED_BY_PRINCIPLE",
            "INSPIRES_HABIT",
            "INSPIRES_GOAL",
            "GENERATES_TASK",
        ]
        rel_types = list(set(rel_types + intermediate_rels))

    # Build relationship pattern
    rel_pattern = "|".join(rel_types)

    cypher = f"""
    // Find impact chains from {start_label} to {end_label}
    MATCH (start:{start_label} {{uid: $start_uid}})
    MATCH path = (start)-[r:{rel_pattern}*1..{max_depth}]->(end:{end_label})

    // Extract path details
    WITH path,
         start,
         end,
         relationships(path) as rels,
         nodes(path) as path_nodes,
         length(path) as path_length

    // Calculate path strength (product of confidences)
    WITH path,
         start,
         end,
         path_length,
         path_nodes,
         rels,
         reduce(strength = 1.0, r in rels |
             strength * coalesce(r.confidence, r.alignment_score, r.strength, 1.0)
         ) as path_strength

    // Format path for return
    RETURN
        start.uid as source_uid,
        start.title as source_title,
        end.uid as target_uid,
        end.title as target_title,
        path_length as hops,
        path_strength,
        [n in path_nodes | {{
            uid: n.uid,
            title: n.title,
            label: labels(n)[0]
        }}] as path_nodes,
        [r in rels | {{
            type: type(r),
            confidence: coalesce(r.confidence, r.alignment_score, r.strength, 1.0)
        }}] as path_relationships
    ORDER BY path_strength DESC, path_length ASC
    LIMIT 20
    """

    params = {"start_uid": start_uid}
    return cypher.strip(), params


def build_bidirectional_impact_query(
    entity_uid: str,
    entity_label: str,
    max_depth: int = 2,
) -> tuple[str, dict[str, Any]]:
    """
    Build query to find all entities impacted BY and impacting an entity.

    Returns both:
    - Downstream impact: What this entity affects
    - Upstream dependencies: What affects this entity

    Args:
        entity_uid: Entity UID to analyze
        entity_label: Entity label (e.g., "Task", "Goal")
        max_depth: Maximum traversal depth (default 2)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    from core.models.relationship_registry import (
        get_all_labels,
        get_valid_relationships,
    )

    # Get all relationships for this domain
    domain_rels = get_valid_relationships(entity_label)
    rel_types = list(domain_rels.keys())

    # Add inverse relationships from other domains
    for label in get_all_labels():
        if label != entity_label:
            label_rels = get_valid_relationships(label)
            for rel_type, spec in label_rels.items():
                if spec.target_labels and entity_label in spec.target_labels:
                    rel_types.append(rel_type)

    rel_pattern = "|".join(set(rel_types))

    cypher = f"""
    // Find bidirectional impact for {entity_label}
    MATCH (center:{entity_label} {{uid: $entity_uid}})

    // Downstream impact (what this entity affects)
    OPTIONAL MATCH downstream_path = (center)-[r_out:{rel_pattern}*1..{max_depth}]->(downstream)
    WHERE downstream <> center

    WITH center,
         collect(DISTINCT {{
             uid: downstream.uid,
             title: downstream.title,
             label: labels(downstream)[0],
             direction: 'downstream',
             distance: length(downstream_path),
             via: [r in relationships(downstream_path) | type(r)]
         }}) as downstream_entities

    // Upstream dependencies (what affects this entity)
    OPTIONAL MATCH upstream_path = (center)<-[r_in:{rel_pattern}*1..{max_depth}]-(upstream)
    WHERE upstream <> center

    WITH center,
         downstream_entities,
         collect(DISTINCT {{
             uid: upstream.uid,
             title: upstream.title,
             label: labels(upstream)[0],
             direction: 'upstream',
             distance: length(upstream_path),
             via: [r in relationships(upstream_path) | type(r)]
         }}) as upstream_entities

    RETURN
        center.uid as entity_uid,
        center.title as entity_title,
        downstream_entities,
        upstream_entities,
        size([e in downstream_entities WHERE e.uid IS NOT NULL]) as downstream_count,
        size([e in upstream_entities WHERE e.uid IS NOT NULL]) as upstream_count
    """

    params = {"entity_uid": entity_uid}
    return cypher.strip(), params


# ============================================================================
# WEIGHT NORMALIZATION FOR GRAPH ALGORITHMS
# ============================================================================


def build_weighted_path_query(
    start_uid: str,
    end_uid: str,
    relationship_types: list[str],
    weight_property: str = "confidence",
    max_depth: int = 5,
    weight_mode: str = "multiply",
) -> tuple[str, dict[str, Any]]:
    """
    Build query for weighted path finding with normalized edge weights.

    Supports different weight aggregation modes for different use cases:
    - multiply: Product of weights (good for confidence cascades)
    - sum: Sum of weights (good for cost accumulation)
    - min: Minimum weight in path (good for bottleneck detection)
    - avg: Average weight (good for overall quality)

    Args:
        start_uid: Starting node UID
        end_uid: Ending node UID
        relationship_types: List of relationship types to traverse
        weight_property: Property to use as weight (default "confidence")
        max_depth: Maximum path length (default 5)
        weight_mode: How to aggregate weights - "multiply", "sum", "min", "avg"

    Returns:
        Tuple of (cypher_query, parameters)
    """
    rel_pattern = "|".join(relationship_types)

    # Build weight aggregation expression
    weight_expr_map = {
        "multiply": f"reduce(w = 1.0, r in rels | w * coalesce(r.{weight_property}, 1.0))",
        "sum": f"reduce(w = 0.0, r in rels | w + coalesce(r.{weight_property}, 0.0))",
        "min": f"reduce(w = 1.0, r in rels | CASE WHEN coalesce(r.{weight_property}, 1.0) < w THEN coalesce(r.{weight_property}, 1.0) ELSE w END)",
        "avg": f"CASE WHEN size(rels) > 0 THEN reduce(w = 0.0, r in rels | w + coalesce(r.{weight_property}, 0.0)) / size(rels) ELSE 0.0 END",
    }

    if weight_mode not in weight_expr_map:
        raise ValueError(f"Invalid weight_mode: {weight_mode}. Use: multiply, sum, min, avg")

    weight_expr = weight_expr_map[weight_mode]

    cypher = f"""
    // Weighted path finding with {weight_mode} aggregation
    MATCH (start {{uid: $start_uid}})
    MATCH (end {{uid: $end_uid}})
    MATCH path = (start)-[r:{rel_pattern}*1..{max_depth}]-(end)

    WITH path,
         relationships(path) as rels,
         nodes(path) as path_nodes,
         length(path) as path_length

    // Calculate aggregated weight
    WITH path,
         path_nodes,
         path_length,
         rels,
         {weight_expr} as path_weight

    // Return paths ordered by weight
    RETURN
        [n in path_nodes | n.uid] as path_uids,
        [n in path_nodes | n.title] as path_titles,
        [r in rels | type(r)] as relationship_types,
        [r in rels | coalesce(r.{weight_property}, 1.0)] as edge_weights,
        path_length,
        path_weight,
        '{weight_mode}' as aggregation_mode
    ORDER BY
        CASE '$weight_mode'
            WHEN 'min' THEN -path_weight  // Higher min is better
            WHEN 'sum' THEN path_weight   // Lower sum is better (cost)
            ELSE -path_weight             // Higher product/avg is better
        END
    LIMIT 10
    """

    params = {"start_uid": start_uid, "end_uid": end_uid}
    return cypher.strip(), params


def build_normalized_centrality_query(
    label: str,
    relationship_types: list[str] | None = None,
    weight_property: str = "confidence",
    min_weight: float = 0.0,
    limit: int = 20,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for weighted degree centrality with normalized scores.

    Calculates centrality considering:
    - Number of connections (degree)
    - Quality of connections (weighted by confidence/strength)
    - Normalized to 0.0-1.0 scale

    Args:
        label: Node label to analyze (e.g., "Ku", "Goal")
        relationship_types: Optional filter for specific relationship types
        weight_property: Property to use as edge weight (default "confidence")
        min_weight: Minimum weight threshold (default 0.0)
        limit: Maximum results (default 20)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    # Build relationship pattern
    if relationship_types:
        rel_pattern = "|".join(relationship_types)
        rel_clause = f"[r:{rel_pattern}]"
    else:
        rel_clause = "[r]"

    cypher = f"""
    // Calculate weighted degree centrality
    MATCH (n:{label})
    OPTIONAL MATCH (n)-{rel_clause}-(neighbor)
    WHERE coalesce(r.{weight_property}, 1.0) >= $min_weight

    WITH n,
         count(DISTINCT neighbor) as degree,
         sum(coalesce(r.{weight_property}, 1.0)) as weighted_degree

    // Get max values for normalization
    WITH collect({{
        node: n,
        degree: degree,
        weighted_degree: weighted_degree
    }}) as all_nodes,
    max(degree) as max_degree,
    max(weighted_degree) as max_weighted_degree

    // Normalize scores
    UNWIND all_nodes as item
    WITH item.node as n,
         item.degree as degree,
         item.weighted_degree as weighted_degree,
         max_degree,
         max_weighted_degree,
         CASE WHEN max_degree > 0
              THEN toFloat(item.degree) / max_degree
              ELSE 0.0
         END as normalized_degree,
         CASE WHEN max_weighted_degree > 0
              THEN item.weighted_degree / max_weighted_degree
              ELSE 0.0
         END as normalized_weighted_degree

    // Combined centrality score (average of degree and weighted)
    WITH n,
         degree,
         weighted_degree,
         normalized_degree,
         normalized_weighted_degree,
         (normalized_degree + normalized_weighted_degree) / 2.0 as centrality_score

    RETURN
        n.uid as uid,
        n.title as title,
        degree,
        weighted_degree,
        round(normalized_degree * 1000) / 1000.0 as normalized_degree,
        round(normalized_weighted_degree * 1000) / 1000.0 as normalized_weighted_degree,
        round(centrality_score * 1000) / 1000.0 as centrality_score
    ORDER BY centrality_score DESC
    LIMIT $limit
    """

    params = {"min_weight": min_weight, "limit": limit}
    return cypher.strip(), params


def build_relationship_weight_stats_query(
    source_label: str,
    relationship_type: str,
    weight_properties: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Build query to analyze weight distribution for a relationship type.

    Useful for understanding weight distributions before normalization
    and for detecting anomalies in relationship properties.

    Args:
        source_label: Source node label (e.g., "Task", "Ku")
        relationship_type: Relationship type to analyze
        weight_properties: Properties to analyze (default: common weight props)

    Returns:
        Tuple of (cypher_query, parameters)
    """
    if not weight_properties:
        weight_properties = [
            "confidence",
            "strength",
            "alignment_score",
            "contribution_percentage",
        ]

    # Build property analysis expressions
    prop_stats = []
    for prop in weight_properties:
        prop_stats.append(f"""
            {{
                property: '{prop}',
                min_value: min(r.{prop}),
                max_value: max(r.{prop}),
                avg_value: avg(r.{prop}),
                count_with_value: sum(CASE WHEN r.{prop} IS NOT NULL THEN 1 ELSE 0 END),
                count_null: sum(CASE WHEN r.{prop} IS NULL THEN 1 ELSE 0 END)
            }}""")

    prop_stats_str = ",\n            ".join(prop_stats)

    cypher = f"""
    // Analyze weight properties for {source_label} -[{relationship_type}]-> *
    MATCH (source:{source_label})-[r:{relationship_type}]->(target)

    WITH count(r) as total_relationships,
         collect(r) as all_rels

    UNWIND all_rels as r

    WITH total_relationships,
         r

    RETURN
        total_relationships,
        '{source_label}' as source_label,
        '{relationship_type}' as relationship_type,
        [
        {prop_stats_str}
        ] as property_stats
    """

    params: dict[str, Any] = {}
    return cypher.strip(), params


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def search[T](entity_class: type[T], **filters: Any) -> tuple[str, dict[str, Any]]:
    """
    Shorthand for building search queries.

    Example:
        query, params = search(TaskPure, priority='high', status='in_progress')
        query, params = search(TaskPure, due_date__gte=date.today())
    """
    from .crud_queries import build_search_query

    return build_search_query(entity_class, filters)


def get_by[T](entity_class: type[T], field_name: str, value: Any) -> tuple[str, dict[str, Any]]:
    """
    Shorthand for getting by field value.

    Example:
        query, params = get_by(TaskPure, 'uid', 'task-123')
    """
    from .crud_queries import build_get_by_field_query

    return build_get_by_field_query(entity_class, field_name, value)


def list_entities[T](
    entity_class: type[T], limit: int = 100, order_by: str | None = None
) -> tuple[str, dict[str, Any]]:
    """
    Shorthand for listing entities.

    Example:
        query, params = list_entities(TaskPure, 10, order_by='created_at')
    """
    from .crud_queries import build_list_query

    return build_list_query(entity_class, limit=limit, order_by=order_by)


def count[T](entity_class: type[T], **filters: Any) -> tuple[str, dict[str, Any]]:
    """
    Shorthand for counting entities.

    Example:
        query, params = count(TaskPure, priority='high', status='completed')
    """
    from .crud_queries import build_count_query

    return build_count_query(entity_class, filters if filters else None)
