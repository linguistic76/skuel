"""
Generic Query Building Patterns
================================

Reusable Cypher query patterns used across SKUEL services.

This module provides static methods for common graph traversal patterns,
eliminating duplication across relationship services and intelligence APIs.

Design Principles:
- Static methods (no state required)
- Generic across all entity types
- Return (query, params) tuples
- Focus on common patterns, not domain-specific logic
- Compatible with both direct Neo4j and UniversalBackend usage

Core Patterns:
1. User entity retrieval (e.g., get all tasks/habits/goals for a user)
2. Entity with relationships (e.g., task with knowledge units)
3. Prerequisite/dependency chains
4. Relationship creation/updates
5. UID collection patterns
6. Filtered entity queries

Estimated Reduction: ~500-1,000 lines across services
"""

from typing import Any


class QueryPatterns:
    """
    Common graph traversal patterns used across services.

    All methods are static and return (query, params) tuples that can be
    executed against Neo4j driver or wrapped in services.

    Usage:
        query, params = QueryPatterns.get_user_entities("Task", user_uid)
        result = await session.run(query, params)
    """

    # ========================================================================
    # USER-ENTITY RETRIEVAL PATTERNS
    # ========================================================================

    @staticmethod
    def get_user_entities(
        entity_label: str,
        user_uid: str,
        relationship: str | None = None,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Generic pattern for retrieving entities associated with a user.

        Handles two patterns:
        1. Direct ownership: (User)-[relationship]->(Entity {user_uid: $user_uid})
        2. Relationship-based: (User {uid: $user_uid})-[relationship]->(Entity)

        Args:
            entity_label: Neo4j label (e.g., "Task", "Habit", "Entity")
            user_uid: User identifier
            relationship: Optional relationship type (e.g., "MASTERED", "IN_PROGRESS")
                         If None, uses Entity.user_uid property instead
            filters: Optional additional filters (e.g., {"status": "active"})
            order_by: Optional property to order by (e.g., "created_at DESC")
            limit: Optional result limit

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Get user's tasks via property
            query, params = QueryPatterns.get_user_entities(
                "Task", user_uid,
                filters={"status": "active"},
                order_by="created_at DESC",
                QueryLimit.SMALL
            )

            # Get user's mastered knowledge via relationship
            query, params = QueryPatterns.get_user_entities(
                "Entity", user_uid,
                relationship="MASTERED",
                order_by="r.achieved_at DESC"
            )
        """
        params: dict[str, Any] = {"user_uid": user_uid}

        # Build MATCH clause based on pattern
        if relationship:
            # Relationship-based pattern
            match_clause = (
                f"MATCH (u:User {{uid: $user_uid}})-[r:{relationship}]->(e:{entity_label})"
            )
        else:
            # Property-based pattern
            match_clause = f"MATCH (e:{entity_label} {{user_uid: $user_uid}})"

        # Build WHERE clause from filters
        where_conditions = []
        if filters:
            for key, value in filters.items():
                param_key = f"filter_{key}"
                where_conditions.append(f"e.{key} = ${param_key}")
                params[param_key] = value

        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        # Build ORDER BY clause
        order_clause = f"ORDER BY {order_by}" if order_by else ""

        # Build LIMIT clause
        limit_clause = ""
        if limit:
            limit_clause = "LIMIT $limit"
            params["limit"] = limit

        # Combine all clauses
        query_parts = [
            match_clause,
            where_clause,
            "RETURN e" + (", r" if relationship else ""),
            order_clause,
            limit_clause,
        ]

        query = "\n".join(part for part in query_parts if part)

        return query, params

    @staticmethod
    def get_user_entity_uids(
        entity_label: str,
        user_uid: str,
        relationship: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Get UIDs of entities associated with a user (optimized for UID collection).

        Same pattern as get_user_entities but returns only UIDs as a list.

        Args:
            entity_label: Neo4j label
            user_uid: User identifier
            relationship: Optional relationship type
            filters: Optional additional filters

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Get UIDs of mastered knowledge
            query, params = QueryPatterns.get_user_entity_uids(
                "Entity", user_uid, relationship="MASTERED"
            )
            # Returns: ["ku.123", "ku.456", ...]
        """
        params: dict[str, Any] = {"user_uid": user_uid}

        # Build MATCH clause
        if relationship:
            match_clause = (
                f"MATCH (u:User {{uid: $user_uid}})-[:{relationship}]->(e:{entity_label})"
            )
        else:
            match_clause = f"MATCH (e:{entity_label} {{user_uid: $user_uid}})"

        # Build WHERE clause from filters
        where_conditions = []
        if filters:
            for key, value in filters.items():
                param_key = f"filter_{key}"
                where_conditions.append(f"e.{key} = ${param_key}")
                params[param_key] = value

        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        # Return collection of UIDs
        query = f"""
        {match_clause}
        {where_clause}
        RETURN collect(e.uid) as entity_uids
        """.strip()

        return query, params

    # ========================================================================
    # ENTITY WITH RELATIONSHIPS PATTERN
    # ========================================================================

    @staticmethod
    def get_entity_with_relationships(
        entity_label: str, entity_uid: str, rel_types: list[str], rel_direction: str = "outgoing"
    ) -> tuple[str, dict[str, Any]]:
        """
        Get entity with related entities via specified relationships.

        Args:
            entity_label: Primary entity label (e.g., "Task")
            entity_uid: Entity UID
            rel_types: List of relationship types to follow (e.g., ["APPLIES_KNOWLEDGE", "DEPENDS_ON"])
            rel_direction: "outgoing" (->), "incoming" (<-), or "both" (-)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Get task with related knowledge and dependencies
            query, params = QueryPatterns.get_entity_with_relationships(
                "Task", task_uid,
                rel_types=["APPLIES_KNOWLEDGE", "DEPENDS_ON"]
            )
        """
        params = {"entity_uid": entity_uid}

        # Build relationship pattern based on direction
        if rel_direction == "outgoing":
            rel_pattern = "-[r]->"
        elif rel_direction == "incoming":
            rel_pattern = "<-[r]-"
        else:  # both
            rel_pattern = "-[r]-"

        # Build relationship type filter
        "|".join(rel_types)

        query = f"""
        MATCH (e:{entity_label} {{uid: $entity_uid}})
        OPTIONAL MATCH (e){rel_pattern}(related)
        WHERE type(r) IN [{", ".join(f"'{rt}'" for rt in rel_types)}]
        RETURN e,
               collect(DISTINCT {{
                   relationship_type: type(r),
                   related_entity: related,
                   related_label: labels(related)[0],
                   related_uid: related.uid
               }}) as relationships
        """

        return query, params

    # ========================================================================
    # PREREQUISITE/DEPENDENCY CHAIN PATTERN
    # ========================================================================

    @staticmethod
    def get_prerequisite_chain(
        entity_label: str,
        entity_uid: str,
        relationship_type: str = "REQUIRES_KNOWLEDGE",
        max_depth: int = 5,
        user_uid: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Get complete prerequisite/dependency chain for an entity.

        Args:
            entity_label: Entity label (e.g., "Entity", "Task")
            entity_uid: Target entity UID
            relationship_type: Prerequisite relationship (e.g., "REQUIRES_KNOWLEDGE", "DEPENDS_ON")
            max_depth: Maximum traversal depth
            user_uid: Optional user UID to check mastery/completion status

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Get knowledge prerequisites with user mastery status
            query, params = QueryPatterns.get_prerequisite_chain(
                "Entity", ku_uid,
                relationship_type="REQUIRES_KNOWLEDGE",
                user_uid=user_uid
            )
        """
        params = {"entity_uid": entity_uid, "max_depth": max_depth}

        if user_uid:
            params["user_uid"] = user_uid
            user_match = "MATCH (user:User {uid: $user_uid})"
            user_check = """
            WITH prereq, depth,
                 exists((user)-[:MASTERED|COMPLETED]->(prereq)) AS is_completed
            """
        else:
            user_match = ""
            user_check = "WITH prereq, depth"

        query = f"""
        {user_match}
        MATCH path = (target:{entity_label} {{uid: $entity_uid}})<-[:{relationship_type}*0..{max_depth}]-(prereq:{entity_label})
        WITH prereq, length(path) as depth
        {user_check}

        RETURN
            prereq.uid AS entity_uid,
            prereq.title AS title,
            depth AS prerequisite_depth,
            {"is_completed," if user_uid else ""}
            CASE
                WHEN depth = 0 THEN 'TARGET'
                WHEN depth = 1 THEN 'DIRECT_PREREQUISITE'
                ELSE 'TRANSITIVE_PREREQUISITE'
            END AS prerequisite_type

        ORDER BY depth, prereq.title
        """

        return query, params

    @staticmethod
    def get_completed_prerequisites(
        entity_label: str,
        user_uid: str,
        mastery_relationship: str = "MASTERED",
        prerequisite_relationship: str = "REQUIRES_KNOWLEDGE",
    ) -> tuple[str, dict[str, Any]]:
        """
        Get all prerequisites that user has completed.

        Critical for readiness/eligibility calculations.

        Args:
            entity_label: Entity label (e.g., "Entity")
            user_uid: User identifier
            mastery_relationship: Relationship indicating completion (e.g., "MASTERED", "COMPLETED")
            prerequisite_relationship: Prerequisite relationship type

        Returns:
            Tuple of (cypher_query, parameters)
        """
        params = {"user_uid": user_uid}

        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{mastery_relationship}]->(completed:{entity_label})
        MATCH (target:{entity_label})-[:{prerequisite_relationship}]->(completed)
        RETURN DISTINCT completed.uid as prereq_uid
        """

        return query, params

    # ========================================================================
    # RELATIONSHIP CREATION/UPDATE PATTERNS
    # ========================================================================

    @staticmethod
    def create_user_entity_relationship(
        entity_label: str,
        user_uid: str,
        entity_uid: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Create or update relationship between user and entity.

        Uses MERGE for idempotency.

        Args:
            entity_label: Entity label
            user_uid: User identifier
            entity_uid: Entity identifier
            relationship_type: Relationship type to create
            properties: Optional relationship properties

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Record knowledge mastery
            query, params = QueryPatterns.create_user_entity_relationship(
                "Entity", user_uid, ku_uid,
                relationship_type="MASTERED",
                properties={
                    "mastery_score": 0.95,
                    "achieved_at": datetime.now()
                }
            )
        """
        params = {"user_uid": user_uid, "entity_uid": entity_uid}

        # Build property assignments
        on_create_props = ["r.created_at = datetime()"]
        on_match_props = ["r.updated_at = datetime()"]

        if properties:
            for key, value in properties.items():
                param_key = f"prop_{key}"
                params[param_key] = value
                on_create_props.append(f"r.{key} = ${param_key}")
                on_match_props.append(f"r.{key} = ${param_key}")

        query = f"""
        MATCH (u:User {{uid: $user_uid}}), (e:{entity_label} {{uid: $entity_uid}})
        MERGE (u)-[r:{relationship_type}]->(e)
        ON CREATE SET
            {", ".join(on_create_props)}
        ON MATCH SET
            {", ".join(on_match_props)}
        RETURN r
        """

        return query, params

    @staticmethod
    def create_entity_relationship(
        source_label: str,
        target_label: str,
        source_uid: str,
        target_uid: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Create relationship between two entities (non-user).

        Args:
            source_label: Source entity label
            target_label: Target entity label
            source_uid: Source entity UID
            target_uid: Target entity UID
            relationship_type: Relationship type
            properties: Optional relationship properties

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Link task to knowledge
            query, params = QueryPatterns.create_entity_relationship(
                "Task", "Entity",
                task_uid, ku_uid,
                relationship_type="APPLIES_KNOWLEDGE",
                properties={"confidence": 0.8}
            )
        """
        params = {"source_uid": source_uid, "target_uid": target_uid}

        # Build property assignments
        on_create_props = ["r.created_at = datetime()"]

        if properties:
            for key, value in properties.items():
                param_key = f"prop_{key}"
                params[param_key] = value
                on_create_props.append(f"r.{key} = ${param_key}")

        query = f"""
        MATCH (source:{source_label} {{uid: $source_uid}})
        MATCH (target:{target_label} {{uid: $target_uid}})
        MERGE (source)-[r:{relationship_type}]->(target)
        ON CREATE SET
            {", ".join(on_create_props)}
        RETURN r
        """

        return query, params

    @staticmethod
    def delete_relationship(
        source_label: str,
        target_label: str,
        source_uid: str,
        target_uid: str,
        relationship_type: str,
    ) -> tuple[str, dict[str, Any]]:
        """
        DETACH DELETE specific relationship between entities.

        Args:
            source_label: Source entity label
            target_label: Target entity label
            source_uid: Source UID
            target_uid: Target UID
            relationship_type: Relationship to DETACH DELETE

        Returns:
            Tuple of (cypher_query, parameters)
        """
        params = {"source_uid": source_uid, "target_uid": target_uid}

        query = f"""
        MATCH (source:{source_label} {{uid: $source_uid}})-[r:{relationship_type}]->(target:{target_label} {{uid: $target_uid}})
        DETACH DELETE r
        RETURN count(r) as deleted_count
        """

        return query, params

    # ========================================================================
    # FILTERING AND AGGREGATION PATTERNS
    # ========================================================================

    @staticmethod
    def build_filter_clause(
        filters: dict[str, Any], entity_alias: str = "e"
    ) -> tuple[str, dict[str, Any]]:
        """
        Build WHERE clause from filter dictionary.

        Supports operators via double-underscore syntax:
        - field: value -> field = value
        - field__gt: value -> field > value
        - field__lt: value -> field < value
        - field__gte: value -> field >= value
        - field__lte: value -> field <= value
        - field__in: [values] -> field IN [values]
        - field__contains: value -> field CONTAINS value

        Args:
            filters: Filter dictionary
            entity_alias: Cypher alias for entity (default: "e")

        Returns:
            Tuple of (where_clause, parameters)

        Example:
            filters = {
                "status": "active",
                "priority__gte": 3,
                "tags__contains": "urgent"
            }
            where_clause, params = QueryPatterns.build_filter_clause(filters)
            # Returns: "e.status = $filter_status AND e.priority >= $filter_priority__gte..."
        """
        if not filters:
            return "", {}

        conditions = []
        params = {}

        for key, value in filters.items():
            # Parse operator from key
            if "__" in key:
                field, operator = key.rsplit("__", 1)
            else:
                field, operator = key, "eq"

            param_key = f"filter_{key}"
            params[param_key] = value

            # Build condition based on operator
            if operator == "eq":
                conditions.append(f"{entity_alias}.{field} = ${param_key}")
            elif operator == "gt":
                conditions.append(f"{entity_alias}.{field} > ${param_key}")
            elif operator == "lt":
                conditions.append(f"{entity_alias}.{field} < ${param_key}")
            elif operator == "gte":
                conditions.append(f"{entity_alias}.{field} >= ${param_key}")
            elif operator == "lte":
                conditions.append(f"{entity_alias}.{field} <= ${param_key}")
            elif operator == "in":
                conditions.append(f"{entity_alias}.{field} IN ${param_key}")
            elif operator == "contains":
                conditions.append(f"{entity_alias}.{field} CONTAINS ${param_key}")
            else:
                # Unknown operator, treat as equality
                conditions.append(f"{entity_alias}.{field} = ${param_key}")

        where_clause = " AND ".join(conditions)
        return where_clause, params

    @staticmethod
    def count_entities(
        entity_label: str, user_uid: str | None = None, filters: dict[str, Any] | None = None
    ) -> tuple[str, dict[str, Any]]:
        """
        Count entities with optional filtering.

        Args:
            entity_label: Entity label
            user_uid: Optional user filter
            filters: Optional additional filters

        Returns:
            Tuple of (cypher_query, parameters)
        """
        params: dict[str, Any] = {}

        if user_uid:
            match_clause = f"MATCH (e:{entity_label} {{user_uid: $user_uid}})"
            params["user_uid"] = user_uid
        else:
            match_clause = f"MATCH (e:{entity_label})"

        where_clause = ""
        if filters:
            filter_where, filter_params = QueryPatterns.build_filter_clause(filters)
            where_clause = f"WHERE {filter_where}"
            params.update(filter_params)

        query = f"""
        {match_clause}
        {where_clause}
        RETURN count(e) as entity_count
        """

        return query, params


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "QueryPatterns",
]
