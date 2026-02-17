"""
Shared Intelligence Queries
============================

Pure utility functions for intelligence analysis across all domains.

These functions replace IntelligenceServiceHelper and cross-service dependencies,
providing shared intelligence logic without coupling services together.

Design Principles:
- Pure functions (no stored state)
- Single responsibility (one query per function)
- Protocol-based dependencies (GraphIntelligenceService)
- Type-safe with Result[T] returns

Usage:
    from core.utils.intelligence_queries import get_knowledge_prerequisites

    # In any intelligence service:
    prerequisites = await get_knowledge_prerequisites(
        graph=self.graph,
        entity_uid="task:123",
        GraphDepth.DEFAULT
    )
"""

from typing import Any

from core.services.infrastructure.graph_intelligence_service import (
    GraphIntelligenceService,
)
from core.utils.result_simplified import Errors, Result

# ============================================================================
# KNOWLEDGE INTELLIGENCE QUERIES
# ============================================================================


async def get_knowledge_prerequisites(
    graph: GraphIntelligenceService, entity_uid: str, depth: int = 3
) -> Result[dict[str, Any]]:
    """
    Analyze knowledge prerequisites for any entity using graph intelligence.

    Shared implementation used across all intelligence services.
    Extracts prerequisite knowledge units from graph context.

    Args:
        graph: Graph intelligence service for queries
        entity_uid: Entity identifier (any domain)
        depth: Graph traversal depth (default: 3)

    Returns:
        Result containing:
        - required_knowledge: List of prerequisite knowledge units
        - learning_path: Recommended learning sequence
        - estimated_prep_time: Estimated preparation time in hours

    Example:
        >>> result = await get_knowledge_prerequisites(
        ...     graph=graph_service, entity_uid="task:advanced-python", GraphDepth.DEFAULT
        ... )
        >>> if result.is_ok:
        ...     print(result.value["required_knowledge"])
    """
    # Query graph for prerequisite context
    context_result = await graph.get_entity_context(entity_uid, depth=depth)

    if context_result.is_error:
        return Result.fail(context_result.expect_error())

    # Extract prerequisites from graph context
    context = context_result.value
    prerequisites = [
        {
            "uid": node.uid,
            "title": node.properties.get("title", "Unknown"),
            "importance": "high",  # Could be calculated from relationship strength
            "domain": node.properties.get("domain", "unknown"),
        }
        for node in context.nodes
        if node.labels and "Ku" in node.labels
    ]

    return Result.ok(
        {
            "required_knowledge": prerequisites,
            "learning_path": [],  # Can be enhanced with path-finding algorithms
            "estimated_prep_time": f"{len(prerequisites) * 5} hours",  # 5 hours per KU
        }
    )


async def get_learning_state(
    graph: GraphIntelligenceService, user_uid: str
) -> Result[dict[str, Any]]:
    """
    Get user's current learning state from graph.

    Replaces cross-service dependency on LpIntelligenceService.
    Provides learning state analysis via direct graph queries.

    Args:
        graph: Graph intelligence service for queries
        user_uid: User identifier

    Returns:
        Result containing:
        - mastered_knowledge: List of mastered knowledge UIDs
        - in_progress_paths: List of active learning path UIDs
        - completion_rates: Dict mapping path UID to completion percentage
        - learning_velocity: Estimated concepts per week

    Example:
        >>> result = await get_learning_state(graph, "user:mike")
        >>> if result.is_ok:
        ...     mastered = result.value["mastered_knowledge"]
    """
    try:
        # Query graph for user's learning relationships
        query = """
        MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[:MASTERED]->(ku:Ku)
        OPTIONAL MATCH (u)-[:ENROLLED_IN]->(lp:Lp)
        OPTIONAL MATCH (lp)-[:CONTAINS]->(step:Ls)
        WITH u,
             collect(DISTINCT ku.uid) as mastered,
             collect(DISTINCT {
                 path_uid: lp.uid,
                 total_steps: count(DISTINCT step),
                 title: lp.title
             }) as paths
        RETURN mastered, paths
        """

        params = {"user_uid": user_uid}
        result = await graph.executor.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.ok(
                {
                    "mastered_knowledge": [],
                    "in_progress_paths": [],
                    "completion_rates": {},
                    "learning_velocity": 0.0,
                }
            )

        record = result.value[0]
        mastered = record.get("mastered", [])
        paths = record.get("paths", [])

        # Calculate completion rates (simplified - real implementation would query steps)
        completion_rates = {path["path_uid"]: 0.0 for path in paths if path.get("path_uid")}

        # Estimate learning velocity (concepts mastered per week)
        learning_velocity = len(mastered) / 52.0  # Rough estimate over a year

        return Result.ok(
            {
                "mastered_knowledge": mastered,
                "in_progress_paths": [p["path_uid"] for p in paths if p.get("path_uid")],
                "completion_rates": completion_rates,
                "learning_velocity": round(learning_velocity, 2),
            }
        )

    except Exception as e:
        return Result.fail(
            Errors.system(
                message="Failed to get learning state", exception=e, operation="get_learning_state"
            )
        )


async def analyze_knowledge_patterns(
    graph: GraphIntelligenceService, entity_uids: list[str]
) -> Result[dict[str, Any]]:
    """
    Analyze knowledge patterns across multiple entities.

    Identifies common knowledge requirements, learning themes, and gaps.
    Used for generating intelligent suggestions and recommendations.

    Args:
        graph: Graph intelligence service for queries
        entity_uids: List of entity identifiers to analyze

    Returns:
        Result containing:
        - common_knowledge: Knowledge units used across multiple entities
        - knowledge_gaps: Missing prerequisites identified
        - learning_themes: Identified learning themes/categories
        - suggested_paths: Recommended learning paths to address gaps

    Example:
        >>> result = await analyze_knowledge_patterns(graph, ["task:1", "task:2", "task:3"])
        >>> if result.is_ok:
        ...     print(result.value["common_knowledge"])
    """
    if not entity_uids:
        return Result.ok(
            {
                "common_knowledge": [],
                "knowledge_gaps": [],
                "learning_themes": [],
                "suggested_paths": [],
            }
        )

    try:
        # Query for knowledge relationships across all entities
        query = """
        MATCH (e)
        WHERE e.uid IN $entity_uids
        OPTIONAL MATCH (e)-[:APPLIES_KNOWLEDGE|REQUIRES_KNOWLEDGE]->(ku:Ku)
        WITH ku, count(DISTINCT e) as usage_count
        WHERE ku IS NOT NULL
        RETURN
            collect({
                uid: ku.uid,
                title: ku.title,
                usage_count: usage_count,
                domain: ku.domain
            }) as knowledge_units
        """

        params = {"entity_uids": entity_uids}
        result = await graph.executor.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.ok(
                {
                    "common_knowledge": [],
                    "knowledge_gaps": [],
                    "learning_themes": [],
                    "suggested_paths": [],
                }
            )

        knowledge_units = result.value[0].get("knowledge_units", [])

        # Identify common knowledge (used by 2+ entities)
        common_knowledge = [ku for ku in knowledge_units if ku.get("usage_count", 0) >= 2]

        # Extract learning themes from domains
        themes = list({ku.get("domain", "unknown") for ku in knowledge_units if ku.get("domain")})

        return Result.ok(
            {
                "common_knowledge": common_knowledge,
                "knowledge_gaps": [],  # Requires prerequisite chain analysis
                "learning_themes": themes,
                "suggested_paths": [],  # Requires path recommendation engine
            }
        )

    except Exception as e:
        return Result.fail(
            Errors.system(
                message="Failed to analyze knowledge patterns",
                exception=e,
                operation="analyze_knowledge_patterns",
            )
        )


# ============================================================================
# GRAPH CONTEXT QUERIES
# ============================================================================


async def get_entity_neighborhood(
    graph: GraphIntelligenceService,
    entity_uid: str,
    relationship_types: list[str] | None = None,
    depth: int = 2,
) -> Result[dict[str, Any]]:
    """
    Get entity's graph neighborhood for context awareness.

    Generic graph query for understanding entity context across domains.
    Replaces domain-specific context methods.

    Args:
        graph: Graph intelligence service
        entity_uid: Entity to analyze
        relationship_types: Optional list of relationship types to traverse
        depth: Traversal depth (default: 2)

    Returns:
        Result containing:
        - neighbors: List of neighboring entities with relationships
        - relationship_counts: Count by relationship type
        - domains_touched: Domains represented in neighborhood

    Example:
        >>> result = await get_entity_neighborhood(
        ...     graph, "task:deploy-app", relationship_types=["DEPENDS_ON", "BLOCKS"]
        ... )
    """
    # Fetch full context (filtering happens post-query for cleaner architecture)
    context_result = await graph.get_entity_context(entity_uid, depth=depth)

    if context_result.is_error:
        return Result.fail(context_result.expect_error())

    context = context_result.value

    # Filter relationships by type if specified (post-query filtering)
    relationships = context.relationships
    if relationship_types:
        relationship_types_set = set(relationship_types)
        relationships = [rel for rel in relationships if rel.type in relationship_types_set]

    # Group neighbors by relationship type
    relationship_counts: dict[str, int] = {}
    for rel in relationships:
        rel_type = rel.type
        relationship_counts[rel_type] = relationship_counts.get(rel_type, 0) + 1

    # Extract domains from node labels (filter nodes by relationship if types specified)
    if relationship_types:
        # Only include nodes connected via specified relationship types
        connected_uids = set()
        for rel in relationships:
            connected_uids.add(rel.source_uid)
            connected_uids.add(rel.target_uid)
        filtered_nodes = [node for node in context.nodes if node.uid in connected_uids]
        domains = {label for node in filtered_nodes for label in (node.labels or [])}
    else:
        domains = {label for node in context.nodes for label in (node.labels or [])}

    # Use filtered nodes if relationship_types specified, otherwise all nodes
    output_nodes = filtered_nodes if relationship_types else context.nodes

    return Result.ok(
        {
            "neighbors": [
                {
                    "uid": node.uid,
                    "labels": node.labels,
                    "properties": node.properties,
                }
                for node in output_nodes
            ],
            "relationship_counts": relationship_counts,
            "domains_touched": list(domains),
            "total_neighbors": len(output_nodes),
        }
    )


# ============================================================================
# CROSS-DOMAIN ANALYSIS
# ============================================================================


async def find_cross_domain_connections(
    graph: GraphIntelligenceService, entity_uid: str, target_domains: list[str]
) -> Result[dict[str, Any]]:
    """
    Find connections between entity and other domains.

    Enables cross-domain intelligence without service dependencies.
    Identifies how an entity relates to other domain entities.

    Args:
        graph: Graph intelligence service
        entity_uid: Source entity
        target_domains: Domain labels to search for connections

    Returns:
        Result containing:
        - connections: List of cross-domain connections found
        - connection_types: Relationship types used
        - strength_scores: Connection strength by domain

    Example:
        >>> result = await find_cross_domain_connections(
        ...     graph, "task:study-python", target_domains=["Ku", "Goal"]
        ... )
    """
    try:
        query = """
        MATCH (source {uid: $entity_uid})
        MATCH (source)-[r]-(target)
        WHERE any(label IN labels(target) WHERE label IN $target_domains)
        RETURN
            collect({
                target_uid: target.uid,
                target_labels: labels(target),
                relationship_type: type(r),
                properties: properties(target)
            }) as connections
        """

        params = {"entity_uid": entity_uid, "target_domains": target_domains}

        result = await graph.executor.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.ok({"connections": [], "connection_types": [], "strength_scores": {}})

        connections = result.value[0].get("connections", [])

        # Extract relationship types
        connection_types = list({conn["relationship_type"] for conn in connections})

        # Calculate strength by domain (count of connections)
        strength_scores = {}
        for domain in target_domains:
            count = sum(1 for conn in connections if domain in conn.get("target_labels", []))
            if count > 0:
                strength_scores[domain] = count

        return Result.ok(
            {
                "connections": connections,
                "connection_types": connection_types,
                "strength_scores": strength_scores,
            }
        )

    except Exception as e:
        return Result.fail(
            Errors.system(
                message="Failed to find cross-domain connections",
                exception=e,
                operation="find_cross_domain_connections",
            )
        )
