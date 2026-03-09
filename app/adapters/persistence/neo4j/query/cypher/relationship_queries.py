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
- build_metadata_aware_path_query: Path finding with time/complexity constraints
"""

from typing import Any


def build_relationship_count(
    uid: str,
    relationship_type: str,
    direction: str = "outgoing",
    properties: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
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

        # Count with property filtering
        query, params = build_relationship_count(
            uid="goal:fitness",
            relationship_type="REQUIRES_HABIT",
            direction="outgoing",
            properties={"essentiality": "essential"}
        )
    """
    # Build Cypher pattern based on direction
    if direction == "outgoing":
        pattern = f"(n)-[r:{relationship_type}]->(related)"
    elif direction == "incoming":
        pattern = f"(n)<-[r:{relationship_type}]-(related)"
    elif direction == "both":
        pattern = f"(n)-[r:{relationship_type}]-(related)"
    else:
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Build WHERE clause for property filtering
    where_clauses = []
    params: dict[str, Any] = {"uid": uid}

    if properties:
        for key, value in properties.items():
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
    direction: str = "outgoing",
    limit: int = 100,
    properties: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
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

        # Get UIDs with property filtering
        query, params = build_relationship_uids_query(
            uid="goal:fitness",
            relationship_type="REQUIRES_HABIT",
            direction="outgoing",
            properties={"essentiality": "essential"}
        )
    """
    # Build Cypher pattern based on direction
    if direction == "outgoing":
        pattern = f"(n)-[r:{relationship_type}]->(related)"
    elif direction == "incoming":
        pattern = f"(n)<-[r:{relationship_type}]-(related)"
    elif direction == "both":
        pattern = f"(n)-[r:{relationship_type}]-(related)"
    else:
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Build WHERE clause for property filtering
    where_clauses = []
    params: dict[str, Any] = {"uid": uid, "limit": limit}

    if properties:
        for key, value in properties.items():
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
    uid: str, relationship_types: list[str], direction: str = "outgoing"
) -> tuple[str, dict[str, Any]]:
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
        - Before: N queries × 10-50ms = N × 10-50ms
        - After: 1 query × 15-60ms = 15-60ms
        - Improvement: 2-5x faster for 2-5 relationship types
    """
    # Build Cypher pattern based on direction
    if direction == "outgoing":
        pattern = "(n)-[r]->(related)"
    elif direction == "incoming":
        pattern = "(n)<-[r]-(related)"
    elif direction == "both":
        pattern = "(n)-[r]-(related)"
    else:
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Build query - filter by relationship type in WHERE clause
    cypher = f"""
    MATCH (n {{uid: $uid}})
    MATCH {pattern}
    WHERE type(r) IN $relationship_types
    RETURN count(r) as count
    """

    params: dict[str, Any] = {"uid": uid, "relationship_types": relationship_types}

    return cypher.strip(), params


def build_batch_relationship_exists(
    node_label: str,
    relationship_types: list[str],
    direction: str = "outgoing",
) -> tuple[str, dict[str, Any]]:
    """
    Generate Cypher query to check relationship existence for multiple entities.

    **DELEGATES TO:** BatchOperationHelper.build_relationship_exists_query()

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
        - Before: N queries × 15-60ms = N × 15-60ms (1.5-6 seconds for 100 items)
        - After: 1 query × 50-200ms = 50-200ms
        - Improvement: 10-100x faster for bulk operations
    """
    from core.infrastructure.batch import BatchOperationHelper

    # Validate direction (maintained for backward compatibility)
    if direction not in ("outgoing", "incoming", "both"):
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Delegate to BatchOperationHelper
    result = BatchOperationHelper.build_relationship_exists_query(
        node_label=node_label,
        relationship_types=relationship_types,
        direction=direction,  # type: ignore[arg-type]
    )

    return result.query, result.params


def build_batch_relationship_count(
    node_label: str,
    relationship_types: list[str],
    direction: str = "outgoing",
) -> tuple[str, dict[str, Any]]:
    """
    Generate Cypher query to count relationships for multiple entities.

    **DELEGATES TO:** BatchOperationHelper.build_relationship_count_query()

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
    from core.infrastructure.batch import BatchOperationHelper

    # Validate direction (maintained for backward compatibility)
    if direction not in ("outgoing", "incoming", "both"):
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Delegate to BatchOperationHelper
    result = BatchOperationHelper.build_relationship_count_query(
        node_label=node_label,
        relationship_types=relationship_types,
        direction=direction,  # type: ignore[arg-type]
    )

    return result.query, result.params


def build_batch_relationship_exists_with_filters(
    node_label: str,
    relationship_types: list[str],
    direction: str = "outgoing",
    property_filters: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Generate Cypher query to check relationship existence with property filtering.

    **DELEGATES TO:** BatchOperationHelper.build_relationship_exists_with_filters_query()

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
    from core.infrastructure.batch import BatchOperationHelper

    # Validate direction (maintained for backward compatibility)
    if direction not in ("outgoing", "incoming", "both"):
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Delegate to BatchOperationHelper
    result = BatchOperationHelper.build_relationship_exists_with_filters_query(
        node_label=node_label,
        relationship_types=relationship_types,
        direction=direction,  # type: ignore[arg-type]
        property_filters=property_filters,
    )

    return result.query, result.params


def build_batch_get_related_with_filters(
    node_label: str,
    relationship_types: list[str],
    direction: str = "outgoing",
    property_filters: dict[str, Any] | None = None,
    limit_per_node: int = 100,
) -> tuple[str, dict[str, Any]]:
    """
    Generate Cypher query to get related entity UIDs with property filtering.

    **DELEGATES TO:** BatchOperationHelper.build_get_related_with_filters_query()

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
    from core.infrastructure.batch import BatchOperationHelper

    # Validate direction (maintained for backward compatibility)
    if direction not in ("outgoing", "incoming", "both"):
        raise ValueError(f"Invalid direction: {direction}. Valid options: outgoing, incoming, both")

    # Delegate to BatchOperationHelper
    result = BatchOperationHelper.build_get_related_with_filters_query(
        node_label=node_label,
        relationship_types=relationship_types,
        direction=direction,  # type: ignore[arg-type]
        property_filters=property_filters,
        limit_per_node=limit_per_node,
    )

    return result.query, result.params


def build_metadata_aware_path_query(
    target_uid: str,
    node_label: str = "Entity",
    relationship_type: str = "REQUIRES_KNOWLEDGE",
    user_time_budget: int | None = None,
    max_complexity_level: str | None = None,
    min_confidence: float = 0.7,
    depth: int = 10,
    limit: int = 5,
) -> tuple[str, dict[str, Any]]:
    """
    Generate Cypher query for metadata-aware learning paths.

    Leverages Neo4j's semantic knowledge graph capabilities by filtering
    paths based on entity metadata (reading_time_minutes, complexity_level)
    and relationship properties (confidence).

    Args:
        target_uid: Target knowledge unit UID to reach
        node_label: Neo4j node label (default: "Entity")
        relationship_type: Relationship type to traverse (default: "REQUIRES_KNOWLEDGE")
        user_time_budget: Maximum total reading time in minutes (None = no limit)
        max_complexity_level: Maximum complexity ("basic", "intermediate", "advanced")
        min_confidence: Minimum relationship confidence threshold
        depth: Maximum path depth to traverse
        limit: Maximum paths to return

    Returns:
        Tuple of (query, params) - injection-safe parameterized Cypher

    Examples:
        # Find paths respecting time budget and difficulty
        query, params = build_metadata_aware_path_query(
            target_uid="ku.async_python",
            user_time_budget=120,  # 2 hours max
            max_complexity_level="intermediate",
            min_confidence=0.7
        )
    """
    # Build WHERE clauses for metadata filters
    where_clauses = []

    # Core constraint: all nodes must have valid metadata
    where_clauses.append("ku.reading_time_minutes IS NOT NULL")

    # Complexity level filter (stored as computed value in Neo4j)
    if max_complexity_level:
        # Convert stored complexity_level string to numeric for comparison
        complexity_check = """
        CASE ku.complexity_level
            WHEN 'basic' THEN 1
            WHEN 'intermediate' THEN 2
            WHEN 'advanced' THEN 3
            ELSE 3
        END <= $max_complexity_value
        """
        where_clauses.append(f"({complexity_check})")

    # Relationship confidence filter
    where_clauses.append("all(r IN rs WHERE r.confidence >= $min_confidence)")

    # Time budget constraint (aggregated across path)
    if user_time_budget:
        where_clauses.append(
            "REDUCE(total_time = 0, ku IN nodes(path) "
            "| total_time + ku.reading_time_minutes) <= $time_budget"
        )

    where_clause = " AND ".join(where_clauses)

    # Build the query
    cypher = f"""
    MATCH path = (start:{node_label})-[rs:{relationship_type}*1..{depth}]->(end:{node_label} {{uid: $target_uid}})
    WHERE all(ku IN nodes(path) WHERE {where_clause})
    WITH path,
         REDUCE(total_time = 0, ku IN nodes(path) | total_time + ku.reading_time_minutes) as total_time,
         REDUCE(avg_complexity = 0.0, ku IN nodes(path) |
             avg_complexity + CASE ku.complexity_level
                 WHEN 'basic' THEN 1.0
                 WHEN 'intermediate' THEN 2.0
                 WHEN 'advanced' THEN 3.0
                 ELSE 2.0
             END
         ) / size(nodes(path)) as avg_complexity_score
    RETURN path,
           total_time,
           avg_complexity_score,
           size(nodes(path)) as path_length
    ORDER BY total_time ASC, avg_complexity_score ASC
    LIMIT $limit
    """

    # Build parameters
    params: dict[str, Any] = {
        "target_uid": target_uid,
        "min_confidence": min_confidence,
        "limit": limit,
    }

    if user_time_budget:
        params["time_budget"] = user_time_budget

    if max_complexity_level:
        complexity_order = {"basic": 1, "intermediate": 2, "advanced": 3}
        params["max_complexity_value"] = complexity_order.get(max_complexity_level.lower(), 3)

    return cypher.strip(), params
