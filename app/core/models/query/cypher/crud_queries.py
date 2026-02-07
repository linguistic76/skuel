"""
CRUD Queries - Dynamic Query Generation for Neo4j
==================================================

Model-introspection based query builders for CRUD operations.
These are infrastructure-level utilities used by services.

Methods:
- build_search_query: Dynamic filtering with operators (eq, gt, lt, contains, in)
- build_text_search_query: Multi-field text search with OR semantics
- build_relationship_traversal_query: Single-query traversal (eliminates N+1)
- build_get_by_field_query: Get entities by field value
- build_list_query: Paginated listing with sorting
- build_count_query: Count entities with optional filters
"""

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, get_origin, get_type_hints

from core.utils.logging import get_logger

from ._types import T

logger = get_logger(__name__)


def convert_value_for_neo4j(value: Any) -> Any:
    """
    Convert Python value to Neo4j-compatible value.

    Handles:
    - Enum -> .value
    - date/datetime -> ISO string
    - Other -> passthrough
    """
    if isinstance(value, Enum):
        return value.value
    elif isinstance(value, date | datetime):
        return value.isoformat()
    else:
        return value


def build_search_query(
    entity_class: type[T], filters: dict[str, Any], label: str | None = None
) -> tuple[str, dict[str, Any]]:
    """
    Auto-generate search query based on model fields.

    The plant grows on the lattice: Add a field to your model ->
    it's automatically queryable via this method!

    Args:
        entity_class: Domain model class (must be dataclass)
        filters: Dictionary of field_name: value to filter by
        label: Neo4j label (defaults to class name)

    Returns:
        Tuple of (cypher_query, parameters)

    Supported operators (via double underscore):
        - eq (default): Exact match
        - gt, lt, gte, lte: Comparisons
        - contains: String matching
        - in: List membership

    Examples:
        # Simple equality
        query, params = build_search_query(
            TaskPure,
            {'priority': 'high', 'status': 'in_progress'}
        )

        # Comparison operators
        query, params = build_search_query(
            TaskPure,
            {'due_date__gte': date.today(), 'estimated_hours__lt': 5.0}
        )
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    label = label or entity_class.__name__
    field_names = {f.name for f in fields(entity_class)}

    where_clauses = []
    params = {}

    for filter_key, filter_value in filters.items():
        # Parse operator from filter key (e.g., "due_date__gte" -> "due_date", "gte")
        if "__" in filter_key:
            field_name, operator = filter_key.rsplit("__", 1)
        else:
            field_name, operator = filter_key, "eq"

        # Validate field exists in model
        if field_name not in field_names:
            logger.warning(f"Filter field '{field_name}' not in {entity_class.__name__}, skipping")
            continue

        # Convert value for Neo4j
        param_name = filter_key.replace("__", "_")
        neo4j_value = convert_value_for_neo4j(filter_value)

        # Build WHERE clause based on operator
        if operator == "eq":
            where_clauses.append(f"n.{field_name} = ${param_name}")
            params[param_name] = neo4j_value
        elif operator == "gt":
            where_clauses.append(f"n.{field_name} > ${param_name}")
            params[param_name] = neo4j_value
        elif operator == "lt":
            where_clauses.append(f"n.{field_name} < ${param_name}")
            params[param_name] = neo4j_value
        elif operator == "gte":
            where_clauses.append(f"n.{field_name} >= ${param_name}")
            params[param_name] = neo4j_value
        elif operator == "lte":
            where_clauses.append(f"n.{field_name} <= ${param_name}")
            params[param_name] = neo4j_value
        elif operator == "contains":
            # Detect if field is a list/array type
            try:
                type_hints = get_type_hints(entity_class)
                field_type = type_hints.get(field_name)
                origin = get_origin(field_type) if field_type else None
                is_list_field = origin is list
            except Exception:
                is_list_field = False

            # For list/array fields, use IN operator (reversed: value IN array)
            # For string fields, use CONTAINS (substring matching)
            if is_list_field:
                where_clauses.append(f"${param_name} IN n.{field_name}")
            else:
                where_clauses.append(f"n.{field_name} CONTAINS ${param_name}")

            params[param_name] = neo4j_value
        elif operator == "in":
            where_clauses.append(f"n.{field_name} IN ${param_name}")
            params[param_name] = [convert_value_for_neo4j(v) for v in filter_value]
        else:
            logger.warning(f"Unknown operator '{operator}', skipping")
            continue

    # Build final query
    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

    query = f"""
    MATCH (n:{label})
    WHERE {where_clause}
    RETURN n
    """

    return query, params


def build_text_search_query(
    entity_class: type[T],
    query: str,
    search_fields: tuple[str, ...] | list[str] | None = None,
    label: str | None = None,
    limit: int = 50,
    order_by: str = "created_at",
    order_desc: bool = True,
) -> tuple[str, dict[str, Any]]:
    """
    Build text search query across multiple fields with OR semantics.

    Generates case-insensitive CONTAINS search across specified fields.
    This eliminates the need for hand-written text search Cypher in search services.

    Args:
        entity_class: Domain model class (must be dataclass)
        query: Search text (case-insensitive)
        search_fields: Fields to search (default: ("title", "description"))
        label: Neo4j label (defaults to class name)
        limit: Maximum results (default 50)
        order_by: Field to sort by (default "created_at")
        order_desc: Sort descending (default True)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Search goals by title and description
        query, params = build_text_search_query(
            Goal,
            "health improvement",
            search_fields=("title", "description"),
            limit=20
        )
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    label = label or entity_class.__name__

    # Default to title and description if not specified
    if search_fields is None:
        search_fields = ("title", "description")

    # Validate search fields exist in model
    valid_fields = {f.name for f in fields(entity_class)}
    validated_search_fields = []
    for field in search_fields:
        if field in valid_fields:
            validated_search_fields.append(field)
        else:
            logger.warning(f"Search field '{field}' not in {entity_class.__name__}, skipping")

    if not validated_search_fields:
        raise ValueError(
            f"No valid search fields for {entity_class.__name__}. "
            f"Requested: {search_fields}, Available: {valid_fields}"
        )

    # Build OR clauses for text search
    where_clauses = [
        f"toLower(n.{field}) CONTAINS toLower($query)" for field in validated_search_fields
    ]
    where_clause = " OR ".join(where_clauses)

    # Build ORDER BY clause
    direction = "DESC" if order_desc else "ASC"
    order_clause = ""
    if order_by and order_by in valid_fields:
        order_clause = f"ORDER BY n.{order_by} {direction}"
    elif order_by:
        logger.warning(f"Order field '{order_by}' not in {entity_class.__name__}, ignoring")

    cypher = f"""
    MATCH (n:{label})
    WHERE {where_clause}
    RETURN n
    {order_clause}
    LIMIT $limit
    """

    return cypher, {"query": query, "limit": limit}


def build_relationship_traversal_query(
    source_uid: str,
    relationship_type: str,
    target_label: str,
    direction: str = "outgoing",
    limit: int = 100,
) -> tuple[str, dict[str, Any]]:
    """
    Build single-query relationship traversal returning full target entities.

    Eliminates N+1 pattern by returning complete entities in one query.

    Args:
        source_uid: UID of the source entity
        relationship_type: Relationship type name (e.g., "FULFILLS_GOAL")
        target_label: Neo4j label of target entities (e.g., "Task", "Goal")
        direction: "outgoing", "incoming", or "both" (default "outgoing")
        limit: Maximum results (default 100)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Get all tasks that fulfill a specific goal (incoming to goal)
        query, params = build_relationship_traversal_query(
            source_uid="goal:health-2025",
            relationship_type="FULFILLS_GOAL",
            target_label="Task",
            direction="incoming"
        )
    """
    # Build direction pattern
    if direction == "outgoing":
        pattern = f"(source {{uid: $source_uid}})-[:{relationship_type}]->(target:{target_label})"
    elif direction == "incoming":
        pattern = f"(source {{uid: $source_uid}})<-[:{relationship_type}]-(target:{target_label})"
    elif direction == "both":
        pattern = f"(source {{uid: $source_uid}})-[:{relationship_type}]-(target:{target_label})"
    else:
        raise ValueError(
            f"Invalid direction '{direction}'. Must be 'outgoing', 'incoming', or 'both'"
        )

    cypher = f"""
    MATCH {pattern}
    RETURN target
    LIMIT $limit
    """

    return cypher, {"source_uid": source_uid, "limit": limit}


def build_graph_aware_search_query(
    entity_class: type[T],
    query: str,
    source_uid: str,
    relationship_type: str,
    search_fields: tuple[str, ...] | list[str] | None = None,
    label: str | None = None,
    direction: str = "outgoing",
    limit: int = 50,
    order_by: str = "created_at",
    order_desc: bool = True,
) -> tuple[str, dict[str, Any]]:
    """
    Build graph-aware search: text search + relationship traversal in ONE query.

    This is Neo4j's unique value proposition - combining property search
    with graph traversal in a single query. Answers questions like:
    - "Find KUs containing 'python' that ENABLE content I've mastered"
    - "Find tasks containing 'review' that FULFILL my health goal"

    Args:
        entity_class: Domain model class (must be dataclass)
        query: Search text (case-insensitive)
        source_uid: UID of the related entity to traverse from
        relationship_type: Relationship type name (e.g., "ENABLES_KNOWLEDGE", "FULFILLS_GOAL")
        search_fields: Fields to search (default: ("title", "description"))
        label: Neo4j label (defaults to class name)
        direction: "outgoing", "incoming", or "both" (default "outgoing")
        limit: Maximum results (default 50)
        order_by: Field to sort by (default "created_at")
        order_desc: Sort descending (default True)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Find KUs containing "machine learning" connected to a mastered KU
        query, params = build_graph_aware_search_query(
            Ku,
            query="machine learning",
            source_uid="ku.python-basics",
            relationship_type="ENABLES_KNOWLEDGE",
            search_fields=("title", "content"),
            direction="incoming",  # KUs that are enabled BY python-basics
        )

        # Find tasks containing "review" that fulfill a specific goal
        query, params = build_graph_aware_search_query(
            Task,
            query="review",
            source_uid="goal:health-2025",
            relationship_type="FULFILLS_GOAL",
            direction="incoming",  # Tasks that fulfill this goal
        )
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    label = label or entity_class.__name__

    # Default to title and description if not specified
    if search_fields is None:
        search_fields = ("title", "description")

    # Validate search fields exist in model
    valid_fields = {f.name for f in fields(entity_class)}
    validated_search_fields = []
    for field in search_fields:
        if field in valid_fields:
            validated_search_fields.append(field)
        else:
            logger.warning(f"Search field '{field}' not in {entity_class.__name__}, skipping")

    if not validated_search_fields:
        raise ValueError(
            f"No valid search fields for {entity_class.__name__}. "
            f"Requested: {search_fields}, Available: {valid_fields}"
        )

    # Build direction pattern for relationship
    if direction == "outgoing":
        rel_pattern = f"(source {{uid: $source_uid}})-[:{relationship_type}]->(target:{label})"
    elif direction == "incoming":
        rel_pattern = f"(source {{uid: $source_uid}})<-[:{relationship_type}]-(target:{label})"
    elif direction == "both":
        rel_pattern = f"(source {{uid: $source_uid}})-[:{relationship_type}]-(target:{label})"
    else:
        raise ValueError(
            f"Invalid direction '{direction}'. Must be 'outgoing', 'incoming', or 'both'"
        )

    # Build OR clauses for text search on target
    text_where_clauses = [
        f"toLower(target.{field}) CONTAINS toLower($query)" for field in validated_search_fields
    ]
    text_where = " OR ".join(text_where_clauses)

    # Build ORDER BY clause
    direction_str = "DESC" if order_desc else "ASC"
    order_clause = ""
    if order_by and order_by in valid_fields:
        order_clause = f"ORDER BY target.{order_by} {direction_str}"
    elif order_by:
        logger.warning(f"Order field '{order_by}' not in {entity_class.__name__}, ignoring")

    # Combine relationship traversal with text search
    cypher = f"""
    MATCH {rel_pattern}
    WHERE {text_where}
    RETURN target
    {order_clause}
    LIMIT $limit
    """

    return cypher, {"source_uid": source_uid, "query": query, "limit": limit}


def build_array_contains_query(
    label: str,
    field: str,
    value: str,
    limit: int = 50,
    order_by: str | None = "created_at",
    order_desc: bool = True,
) -> tuple[str, dict[str, Any]]:
    """
    Build query to find entities where array field contains a value.

    Uses case-insensitive matching via ANY() predicate.
    Ideal for searching tags, categories, or other array properties.

    Args:
        label: Neo4j node label (e.g., "Ku", "Task")
        field: Array field name (e.g., "tags")
        value: Value to search for (case-insensitive)
        limit: Maximum results (default 50)
        order_by: Field to sort by (default "created_at")
        order_desc: Sort descending (default True)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Find KUs tagged with "python"
        query, params = build_array_contains_query(
            label="Ku",
            field="tags",
            value="python",
            limit=20
        )

        # Find tasks with "urgent" tag
        query, params = build_array_contains_query(
            label="Task",
            field="tags",
            value="urgent"
        )
    """
    # Build ORDER BY clause
    order_clause = ""
    if order_by:
        direction = "DESC" if order_desc else "ASC"
        order_clause = f"ORDER BY n.{order_by} {direction}"

    # Case-insensitive array contains using ANY()
    cypher = f"""
    MATCH (n:{label})
    WHERE ANY(item IN n.{field} WHERE toLower(item) CONTAINS toLower($value))
    RETURN n
    {order_clause}
    LIMIT $limit
    """

    return cypher, {"value": value, "limit": limit}


def build_array_any_match_query(
    label: str,
    field: str,
    values: list[str],
    match_all: bool = False,
    limit: int = 50,
    order_by: str | None = "created_at",
    order_desc: bool = True,
) -> tuple[str, dict[str, Any]]:
    """
    Build query to find entities matching any/all values in array field.

    Supports two modes:
    - match_all=False: OR semantics (any value matches)
    - match_all=True: AND semantics (all values must match)

    Args:
        label: Neo4j node label
        field: Array field name (e.g., "tags")
        values: List of values to search for
        match_all: If True, require ALL values; if False, ANY value
        limit: Maximum results (default 50)
        order_by: Field to sort by (default "created_at")
        order_desc: Sort descending (default True)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Find KUs with ANY of these tags
        query, params = build_array_any_match_query(
            label="Ku",
            field="tags",
            values=["python", "ml", "data-science"],
            match_all=False
        )

        # Find KUs with ALL of these tags
        query, params = build_array_any_match_query(
            label="Ku",
            field="tags",
            values=["python", "beginner"],
            match_all=True
        )
    """
    # Build ORDER BY clause
    order_clause = ""
    if order_by:
        direction = "DESC" if order_desc else "ASC"
        order_clause = f"ORDER BY n.{order_by} {direction}"

    if match_all:
        # AND semantics: ALL values must be in the array
        # Use ALL() predicate with case-insensitive matching
        cypher = f"""
        MATCH (n:{label})
        WHERE ALL(v IN $values WHERE
            ANY(item IN n.{field} WHERE toLower(item) = toLower(v))
        )
        RETURN n
        {order_clause}
        LIMIT $limit
        """
    else:
        # OR semantics: ANY value matches
        cypher = f"""
        MATCH (n:{label})
        WHERE ANY(v IN $values WHERE
            ANY(item IN n.{field} WHERE toLower(item) CONTAINS toLower(v))
        )
        RETURN n
        {order_clause}
        LIMIT $limit
        """

    return cypher, {"values": values, "limit": limit}


def build_get_by_field_query(
    entity_class: type[T], field_name: str, field_value: Any, label: str | None = None
) -> tuple[str, dict[str, Any]]:
    """
    Generate query to get entities by a specific field value.

    Args:
        entity_class: Domain model class
        field_name: Field to filter by
        field_value: Value to match
        label: Neo4j label (defaults to class name)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        query, params = build_get_by_field_query(TaskPure, 'uid', 'task-123')
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    field_names = {f.name for f in fields(entity_class)}
    if field_name not in field_names:
        raise ValueError(f"Field '{field_name}' not found in {entity_class.__name__}")

    label = label or entity_class.__name__
    neo4j_value = convert_value_for_neo4j(field_value)

    query = f"""
    MATCH (n:{label})
    WHERE n.{field_name} = $field_value
    RETURN n
    """

    return query, {"field_value": neo4j_value}


def build_list_query(
    entity_class: type[T],
    label: str | None = None,
    limit: int = 100,
    skip: int = 0,
    order_by: str | None = None,
    order_desc: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Generate query to list entities with pagination and sorting.

    Args:
        entity_class: Domain model class
        label: Neo4j label
        limit: Maximum number of results
        skip: Number of results to skip
        order_by: Field to order by
        order_desc: Sort descending

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        query, params = build_list_query(
            TaskPure,
            limit=20,
            order_by='created_at',
            order_desc=True
        )
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    label = label or entity_class.__name__

    # Validate order_by field if provided
    if order_by:
        field_names = {f.name for f in fields(entity_class)}
        if order_by not in field_names:
            logger.warning(f"Order field '{order_by}' not in {entity_class.__name__}, ignoring")
            order_by = None

    order_clause = ""
    if order_by:
        direction = "DESC" if order_desc else "ASC"
        order_clause = f"ORDER BY n.{order_by} {direction}"

    query = f"""
    MATCH (n:{label})
    RETURN n
    {order_clause}
    SKIP $skip
    LIMIT $limit
    """

    return query, {"limit": limit, "skip": skip}


def build_count_query(
    entity_class: type[T], filters: dict[str, Any] | None = None, label: str | None = None
) -> tuple[str, dict[str, Any]]:
    """
    Generate query to count entities with optional filters.

    Args:
        entity_class: Domain model class
        filters: Optional filters (uses same syntax as build_search_query)
        label: Neo4j label

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        query, params = build_count_query(
            TaskPure,
            {'priority': 'high', 'status': 'completed'}
        )
    """
    if filters:
        # Reuse search query logic but return count
        search_query, params = build_search_query(entity_class, filters, label)
        # Replace RETURN n with RETURN count(n)
        count_query = search_query.replace("RETURN n", "RETURN count(n) as count")
        return count_query, params
    else:
        label = label or entity_class.__name__
        query = f"MATCH (n:{label}) RETURN count(n) as count"
        return query, {}


def get_filterable_fields(entity_class: type[T]) -> list[str]:
    """
    Get list of field names that can be used for filtering.

    Args:
        entity_class: Domain model class

    Returns:
        List of field names

    Example:
        fields = get_filterable_fields(TaskPure)
        # ['uid', 'title', 'priority', 'status', 'due_date', ...]
    """
    if not is_dataclass(entity_class):
        raise ValueError(f"Entity class must be a dataclass, got {entity_class}")

    return [f.name for f in fields(entity_class)]


def get_supported_operators() -> list[str]:
    """Get list of supported filter operators."""
    return ["eq", "gt", "lt", "gte", "lte", "contains", "in"]


# =============================================================================
# PHASE 2 CONSOLIDATION - Extended Query Builders (January 2026)
# =============================================================================


def build_distinct_values_query(
    label: str,
    field: str,
    user_uid: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Build query to get distinct values from a field.

    Used for category listing and dynamic filter options.

    Args:
        label: Neo4j node label
        field: Field name to get distinct values from
        user_uid: Optional user filter (multi-tenant)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Get all categories for a user
        query, params = build_distinct_values_query("Task", "category", user_uid="user:123")

        # Get all categories globally (admin only)
        query, params = build_distinct_values_query("Task", "category")
    """
    params: dict[str, Any] = {}

    if user_uid:
        query = f"""
        MATCH (n:{label})
        WHERE n.user_uid = $user_uid AND n.{field} IS NOT NULL
        RETURN DISTINCT n.{field} as value
        ORDER BY value
        """
        params["user_uid"] = user_uid
    else:
        query = f"""
        MATCH (n:{label})
        WHERE n.{field} IS NOT NULL
        RETURN DISTINCT n.{field} as value
        ORDER BY value
        """

    return query, params


def build_hierarchy_query(
    label: str,
    uid: str,
    relationship_types: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for hierarchical structure (parents and children).

    Returns the entity's position in containment hierarchy.

    Args:
        label: Neo4j node label
        uid: Entity UID
        relationship_types: Relationship types for hierarchy (default: CONTAINS|AGGREGATES|HAS_STEP)

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        query, params = build_hierarchy_query("Lp", "lp:python-basics")
    """
    rel_types = "|".join(relationship_types or ["CONTAINS", "AGGREGATES", "HAS_STEP"])

    query = f"""
    MATCH (n:{label} {{uid: $uid}})

    // Find parent containers
    OPTIONAL MATCH (parent)-[:{rel_types}]->(n)
    WITH n, collect(DISTINCT {{
        uid: parent.uid,
        type: labels(parent)[0],
        title: parent.title
    }}) as parents

    // Find child elements
    OPTIONAL MATCH (n)-[:{rel_types}]->(child)
    WITH n, parents, collect(DISTINCT {{
        uid: child.uid,
        type: labels(child)[0],
        title: child.title,
        sequence: child.sequence
    }}) as children

    RETURN n, parents, children
    """

    return query, {"uid": uid}


def build_prerequisite_traversal_query(
    label: str,
    uid: str,
    relationship_types: list[str],
    depth: int = 3,
    direction: str = "outgoing",
) -> tuple[str, dict[str, Any]]:
    """
    Build query for prerequisite chain traversal.

    Supports both prerequisite chains (outgoing) and enabled-by queries (incoming).

    Args:
        label: Neo4j node label
        uid: Starting entity UID
        relationship_types: Relationship types for prerequisites (e.g., ["REQUIRES_KNOWLEDGE"])
        depth: Maximum traversal depth (1-10)
        direction: "outgoing" for prerequisites, "incoming" for enabled-by

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        # Get prerequisites
        query, params = build_prerequisite_traversal_query(
            "Ku", "ku:python-advanced", ["REQUIRES_KNOWLEDGE"], direction="outgoing"
        )

        # Get what this enables
        query, params = build_prerequisite_traversal_query(
            "Ku", "ku:python-basics", ["REQUIRES_KNOWLEDGE"], direction="incoming"
        )
    """
    rel_pattern = "|".join(relationship_types)

    if direction == "outgoing":
        # Prerequisites: start -> n (traversing forward)
        query = f"""
        MATCH (start:{label} {{uid: $uid}})
        MATCH path = (start)-[:{rel_pattern}*1..{depth}]->(n:{label})
        WITH DISTINCT n, length(path) as distance
        ORDER BY distance DESC
        RETURN n
        """
    else:
        # Enabled-by: n -> start (inverse traversal)
        query = f"""
        MATCH (start:{label} {{uid: $uid}})
        MATCH path = (n:{label})-[:{rel_pattern}*1..{depth}]->(start)
        WITH DISTINCT n, length(path) as distance
        ORDER BY distance ASC
        RETURN n
        """

    return query, {"uid": uid}


def build_user_progress_query(
    label: str,
    user_uid: str,
    entity_uid: str,
    mastery_threshold: float = 0.8,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for user progress/mastery data.

    Returns user's relationship to an entity with progress metadata.

    Args:
        label: Entity node label
        user_uid: User UID
        entity_uid: Entity UID
        mastery_threshold: Threshold for considering entity mastered

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        query, params = build_user_progress_query("Ku", "user:123", "ku:python-basics")
    """
    query = f"""
    MATCH (u:User {{uid: $user_uid}})-[r:MASTERED|STUDYING|COMPLETED]->(e:{label} {{uid: $entity_uid}})
    RETURN {{
        mastery_level: coalesce(r.level, 0.0),
        is_mastered: coalesce(r.level, 0.0) >= $mastery_threshold,
        last_accessed: r.last_accessed,
        time_spent: coalesce(r.time_spent, 0),
        attempts: coalesce(r.attempts, 0),
        relationship_type: type(r),
        started_at: r.started_at,
        completed_at: r.completed_at
    }} as progress
    """

    return query, {
        "user_uid": user_uid,
        "entity_uid": entity_uid,
        "mastery_threshold": mastery_threshold,
    }


def build_user_curriculum_query(
    label: str,
    user_uid: str,
    include_completed: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Build query for user's curriculum/learning entities.

    Returns entities the user is studying or has mastered.

    Args:
        label: Entity node label
        user_uid: User UID
        include_completed: Include completed/mastered entities

    Returns:
        Tuple of (cypher_query, parameters)

    Example:
        query, params = build_user_curriculum_query("Ku", "user:123", include_completed=False)
    """
    rel_filter = "" if include_completed else "WHERE NOT type(r) = 'MASTERED'"

    query = f"""
    MATCH (u:User {{uid: $user_uid}})-[r:STUDYING|MASTERED|ENROLLED_IN]->(n:{label})
    {rel_filter}
    RETURN n
    ORDER BY r.last_accessed DESC
    """

    return query, {"user_uid": user_uid}
