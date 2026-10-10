"""
Relationship Queries - Batch Relationship Operations
====================================================

Cypher query builders for batch relationship existence checks and counts
(UNWIND over many entity uids in one round trip). The single-entity reads
build their own Cypher: ``get_related_uids`` (``_relationship_query_mixin.py``,
under ``_link_far_node_scope``) and ``count_related``
(``_relationship_crud_mixin.py``, through ``_build_direction_pattern``).

Methods:
- build_batch_relationship_exists: Batch check relationship existence
- build_batch_relationship_count: Batch count relationships
- build_batch_relationship_exists_with_filters: Batch check with property filters
- build_batch_get_related_with_filters: Batch get related UIDs with filters
"""

from typing import Any

from core.models.enums.neo_labels import NeoLabel
from core.ports.base_protocols import Direction


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
