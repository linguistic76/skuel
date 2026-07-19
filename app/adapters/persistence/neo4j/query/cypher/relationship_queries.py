"""
Relationship Queries - Counting, Batch Operations, and Path Queries
====================================================================

Cypher query builders for relationship counting, batch existence checks,
and metadata-aware path finding.

Methods:
- build_relationship_count: Count related entities via relationship
- build_relationship_uids_query: Get UIDs of related entities
- build_multi_relationship_count: Count across multiple relationship types
- build_batch_relationship_exists: Batch check relationship existence
- build_batch_relationship_count: Batch count relationships
- build_batch_relationship_exists_with_filters: Batch check with property filters
- build_batch_get_related_with_filters: Batch get related UIDs with filters
"""

from typing import Any

from adapters.persistence.neo4j._backend_helpers import direction_clause
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import Neo4jValue
from core.ports.base_protocols import Direction

from ._helpers import validate_identifier


def build_relationship_count(
    uid: str,
    relationship_type: str,
    direction: Direction = "outgoing",
    properties: dict[str, Neo4jValue] | None = None,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Generate Cypher query to count related entities via graph relationships.

    Graph-native query pattern that counts relationships without loading entities.
    Used by UniversalNeo4jBackend.count_related() implementation.

    Args:
        uid: Entity UID
        relationship_type: Neo4j relationship type (e.g., "REQUIRES_KNOWLEDGE", "APPLIES_KNOWLEDGE")
        direction: Traversal direction ("outgoing", "incoming", or "both")
        properties: Optional dict of relationship properties to filter by

    Returns:
        Tuple of (query, params) - injection-safe parameterized Cypher

    Examples:
        # Count outgoing APPLIES_KNOWLEDGE relationships
        query, params = build_relationship_count(
            uid="task:123",
            relationship_type="APPLIES_KNOWLEDGE",
            direction="outgoing"
        )

        # Count a goal's essential habits (incoming SUPPORTS_GOAL, filtered by tier)
        query, params = build_relationship_count(
            uid="goal:fitness",
            relationship_type="SUPPORTS_GOAL",
            direction="incoming",
            properties={"essentiality": "essential"}
        )
    """
    validate_identifier(relationship_type, "relationship type")

    # Build Cypher pattern based on direction
    pattern = f"(n){direction_clause(direction, 'r', relationship_type)}(related)"

    # Build WHERE clause for property filtering
    where_clauses = []
    params: dict[str, Neo4jValue] = {"uid": uid}

    if properties:
        for key, value in properties.items():
            validate_identifier(key, "property")
            param_name = f"prop_{key}"
            where_clauses.append(f"r.{key} = ${param_name}")
            params[param_name] = value

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Build query
    cypher = f"""
    MATCH (n {{uid: $uid}})
    MATCH {pattern}
    {where_clause}
    RETURN count(related) as count
    """

    return cypher.strip(), params


def build_relationship_uids_query(
    uid: str,
    relationship_type: str,
    direction: Direction = "outgoing",
    limit: int = 100,
    properties: dict[str, Neo4jValue] | None = None,
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Generate Cypher query to get UIDs of related entities via graph relationships.

    Graph-native query pattern that retrieves related entity UIDs without loading properties.
    Used by UniversalNeo4jBackend.get_related_uids() implementation.

    Args:
        uid: Source entity UID
        relationship_type: Neo4j relationship type (e.g., "REQUIRES_KNOWLEDGE", "ENABLES_KNOWLEDGE")
        direction: Traversal direction ("outgoing", "incoming", or "both")
        limit: Max results to return (default 100)
        properties: Optional dict of relationship properties to filter by

    Returns:
        Tuple of (query, params) - injection-safe parameterized Cypher

    Examples:
        # Get UIDs of knowledge units this task applies
        query, params = build_relationship_uids_query(
            uid="task:123",
            relationship_type="APPLIES_KNOWLEDGE",
            direction="outgoing"
        )

        # Get a goal's essential habits (incoming SUPPORTS_GOAL, filtered by tier)
        query, params = build_relationship_uids_query(
            uid="goal:fitness",
            relationship_type="SUPPORTS_GOAL",
            direction="incoming",
            properties={"essentiality": "essential"}
        )
    """
    validate_identifier(relationship_type, "relationship type")

    # Build Cypher pattern based on direction
    pattern = f"(n){direction_clause(direction, 'r', relationship_type)}(related)"

    # Build WHERE clause for property filtering
    where_clauses = []
    params: dict[str, Neo4jValue] = {"uid": uid, "limit": limit}

    if properties:
        for key, value in properties.items():
            validate_identifier(key, "property")
            param_name = f"prop_{key}"
            where_clauses.append(f"r.{key} = ${param_name}")
            params[param_name] = value

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Build query
    cypher = f"""
    MATCH (n {{uid: $uid}})
    MATCH {pattern}
    {where_clause}
    RETURN related.uid as uid
    LIMIT $limit
    """

    return cypher.strip(), params


def build_multi_relationship_count(
    uid: str, relationship_types: list[str], direction: Direction = "outgoing"
) -> tuple[str, dict[str, Neo4jValue]]:
    """
    Generate Cypher query to count relationships across multiple types.

    **PERFORMANCE OPTIMIZATION:**
    Eliminates sequential relationship count queries by checking multiple
    relationship types in a single database round trip.

    Args:
        uid: Entity UID
        relationship_types: List of relationship types to count
                          (e.g., ["REQUIRES_KNOWLEDGE", "REQUIRES_PREREQUISITE"])
        direction: Traversal direction ("outgoing", "incoming", or "both")

    Returns:
        Tuple of (query, params) - injection-safe parameterized Cypher

    Examples:
        # Check if task has ANY prerequisites (knowledge OR tasks)
        query, params = build_multi_relationship_count(
            uid="task:123",
            relationship_types=["REQUIRES_KNOWLEDGE", "REQUIRES_PREREQUISITE"],
            direction="outgoing"
        )

    Performance:
        - Before: N queries x 10-50ms = N x 10-50ms
        - After: 1 query x 15-60ms = 15-60ms
        - Improvement: 2-5x faster for 2-5 relationship types
    """
    # Build Cypher pattern based on direction
    pattern = f"(n){direction_clause(direction)}(related)"

    # Build query - filter by relationship type in WHERE clause
    cypher = f"""
    MATCH (n {{uid: $uid}})
    MATCH {pattern}
    WHERE type(r) IN $relationship_types
    RETURN count(r) as count
    """

    rel_types: list[str | int | float] = list(relationship_types)
    params: dict[str, Neo4jValue] = {"uid": uid, "relationship_types": rel_types}

    return cypher.strip(), params


def build_batch_relationship_exists(
    node_label: NeoLabel,
    relationship_types: list[str],
    direction: Direction = "outgoing",
) -> tuple[str, dict[str, Any]]:
    """
    Generate Cypher query to check relationship existence for multiple entities.

    **DELEGATES TO:** BatchCypherBuilder.build_relationship_exists_query()

    **PERFORMANCE OPTIMIZATION:**
    Eliminates N sequential existence checks by processing multiple entities
    in a single database round trip using UNWIND.

    Args:
        node_label: Neo4j node label (e.g., "Task", "Goal", "Habit")
        relationship_types: List of relationship types to check
        direction: Traversal direction ("outgoing", "incoming", or "both")

    Returns:
        Tuple of (query_template, params) - query uses $uids parameter at runtime

    Examples:
        # Batch check prerequisites for 100 tasks
        query, params = build_batch_relationship_exists(
            node_label="Task",
            relationship_types=["REQUIRES_KNOWLEDGE", "REQUIRES_PREREQUISITE"],
            direction="outgoing"
        )
        result = await backend.execute_query(query, {"uids": task_uids})
        # Returns: [{"uid": "task:1", "has_relationships": True}, ...]

    Performance:
        - Before: N queries x 15-60ms = N x 15-60ms (1.5-6 seconds for 100 items)
        - After: 1 query x 50-200ms = 50-200ms
        - Improvement: 10-100x faster for bulk operations
    """
    from adapters.persistence.neo4j.batch_cypher_builder import BatchCypherBuilder

    # Validate direction (maintained for backward compatibility)
    if direction not in ("outgoing", "incoming", "both"):
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Delegate to BatchCypherBuilder
    result = BatchCypherBuilder.build_relationship_exists_query(
        node_label=node_label,
        relationship_types=relationship_types,
        direction=direction,
    )

    return result.query, result.params


def build_batch_relationship_count(
    node_label: NeoLabel,
    relationship_types: list[str],
    direction: Direction = "outgoing",
) -> tuple[str, dict[str, Any]]:
    """
    Generate Cypher query to count relationships for multiple entities.

    **DELEGATES TO:** BatchCypherBuilder.build_relationship_count_query()

    Similar to build_batch_relationship_exists() but returns actual counts
    instead of boolean existence.

    Args:
        node_label: Neo4j node label (e.g., "Task", "Goal", "Habit")
        relationship_types: List of relationship types to count
        direction: Traversal direction ("outgoing", "incoming", or "both")

    Returns:
        Tuple of (query_template, params) - query uses $uids parameter at runtime

    Examples:
        # Get prerequisite counts for multiple tasks
        query, params = build_batch_relationship_count(
            node_label="Task",
            relationship_types=["REQUIRES_KNOWLEDGE", "REQUIRES_PREREQUISITE"],
            direction="outgoing"
        )
        result = await backend.execute_query(query, {"uids": task_uids})
        # Returns: [{"uid": "task:1", "count": 3}, {"uid": "task:2", "count": 0}, ...]
    """
    from adapters.persistence.neo4j.batch_cypher_builder import BatchCypherBuilder

    # Validate direction (maintained for backward compatibility)
    if direction not in ("outgoing", "incoming", "both"):
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Delegate to BatchCypherBuilder
    result = BatchCypherBuilder.build_relationship_count_query(
        node_label=node_label,
        relationship_types=relationship_types,
        direction=direction,
    )

    return result.query, result.params


def build_batch_relationship_exists_with_filters(
    node_label: NeoLabel,
    relationship_types: list[str],
    direction: Direction = "outgoing",
    property_filters: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Generate Cypher query to check relationship existence with property filtering.

    **DELEGATES TO:** BatchCypherBuilder.build_relationship_exists_with_filters_query()

    Enhanced version of build_batch_relationship_exists() that supports
    filtering relationships by their properties (e.g., confidence, strength).

    Args:
        node_label: Neo4j node label (e.g., "Entity", "Task")
        relationship_types: List of relationship types to check
        direction: Traversal direction ("outgoing", "incoming", or "both")
        property_filters: Optional filters for relationship properties
                        Format: {"property_name__operator": value}
                        Operators: gte, lte, gt, lt, eq, ne
                        Example: {"strength__gte": 0.8, "confidence__gt": 0.7}

    Returns:
        Tuple of (query_template, params) - query uses $uids parameter at runtime

    Examples:
        # Find knowledge units with high-confidence prerequisites
        query, params = build_batch_relationship_exists_with_filters(
            node_label="Entity",
            relationship_types=["REQUIRES_KNOWLEDGE"],
            direction="outgoing",
            property_filters={"strength__gte": 0.8}
        )
    """
    from adapters.persistence.neo4j.batch_cypher_builder import BatchCypherBuilder

    # Validate direction (maintained for backward compatibility)
    if direction not in ("outgoing", "incoming", "both"):
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Delegate to BatchCypherBuilder
    result = BatchCypherBuilder.build_relationship_exists_with_filters_query(
        node_label=node_label,
        relationship_types=relationship_types,
        direction=direction,
        property_filters=property_filters,
    )

    return result.query, result.params


def build_batch_get_related_with_filters(
    node_label: NeoLabel,
    relationship_types: list[str],
    direction: Direction = "outgoing",
    property_filters: dict[str, Any] | None = None,
    limit_per_node: int = 100,
) -> tuple[str, dict[str, Any]]:
    """
    Generate Cypher query to get related entity UIDs with property filtering.

    **DELEGATES TO:** BatchCypherBuilder.build_get_related_with_filters_query()

    Batch query that returns lists of related entity UIDs for multiple source nodes,
    with optional filtering by relationship properties.

    Args:
        node_label: Neo4j node label (e.g., "Entity", "Task")
        relationship_types: List of relationship types to traverse
        direction: Traversal direction ("outgoing", "incoming", or "both")
        property_filters: Optional filters for relationship properties
        limit_per_node: Maximum related entities to return per source node

    Returns:
        Tuple of (query_template, params) - query uses $uids parameter at runtime

    Examples:
        # Get high-strength prerequisites for multiple knowledge units
        query, params = build_batch_get_related_with_filters(
            node_label="Entity",
            relationship_types=["REQUIRES_KNOWLEDGE"],
            direction="outgoing",
            property_filters={"strength__gte": 0.8},
            limit_per_node=50
        )
        # Returns: [{"uid": "ku:python", "related_uids": ["ku:basics", "ku:functions"]}, ...]
    """
    from adapters.persistence.neo4j.batch_cypher_builder import BatchCypherBuilder

    # Validate direction (maintained for backward compatibility)
    if direction not in ("outgoing", "incoming", "both"):
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Delegate to BatchCypherBuilder
    result = BatchCypherBuilder.build_get_related_with_filters_query(
        node_label=node_label,
        relationship_types=relationship_types,
        direction=direction,
        property_filters=property_filters,
        limit_per_node=limit_per_node,
    )

    return result.query, result.params
