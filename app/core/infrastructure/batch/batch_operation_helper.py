"""
BatchOperationHelper - DRY Batch Operations for Neo4j
=====================================================

Consolidates UNWIND-based batch patterns used across:
- UniversalNeo4jBackend (4 patterns)
- CypherGenerator (2 patterns)
- 12 relationship services (batch creation)

Core Principle: "One query builder, many consumers"

This module implements the DRY principle for batch operations, eliminating
~120-150 lines of duplicated UNWIND query patterns across the codebase.

Pattern Categories:
==================

1. **Batch Existence Checks** - Check if relationships exist for multiple entities
   - Used by: batch_has_prerequisites(), batch_is_blocked(), etc.
   - Query: UNWIND $uids → check relationship existence → return boolean map

2. **Batch Counts** - Count relationships for multiple entities
   - Used by: batch_prerequisite_count(), batch_dependency_count(), etc.
   - Query: UNWIND $uids → count relationships → return count map

3. **Batch Properties Fetch** - Get relationship properties for multiple edges
   - Used by: get_relationships_batch_metadata()
   - Query: UNWIND $rels → fetch properties → return properties list

4. **Batch Deletion** - Delete multiple relationships in single transaction
   - Used by: delete_relationships_batch()
   - Query: UNWIND $rels → delete matches → return deleted count

5. **Batch Relationship Building** - Build relationship tuples from UID lists
   - Used by: create_*_relationships() in all 12 relationship services
   - Pure Python: Flatten UID lists into (from, to, type, props) tuples

Performance Impact:
==================
- Before: N queries × 15-60ms = N × 15-60ms (1.5-6 seconds for 100 items)
- After: 1 query × 50-200ms = 50-200ms
- Improvement: 10-100x faster for bulk operations

See Also:
- /docs/patterns/BATCH_OPERATIONS_IMPLEMENTATION.md
- /docs/optimizations/N_PLUS_1_BATCH_OPTIMIZATION.md
"""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class BatchQueryResult:
    """
    Standardized result from batch query builders.

    Attributes:
        query: The Cypher query string (parameterized)
        params: Dictionary of query parameters

    Usage:
        result = BatchOperationHelper.build_relationship_exists_query(...)
        records = await backend.execute_query(result.query, result.params)
    """

    query: str
    params: dict[str, Any]


class BatchOperationHelper:
    """
    Helper for generating efficient UNWIND-based batch Cypher queries.

    Benefits:
    - DRY: Single implementation of each batch pattern
    - Type-safe: Dataclass results, proper typing
    - Testable: Pure functions, no side effects
    - Performant: UNWIND > N individual queries

    All methods are static - no instance state needed.

    Usage Examples:
    ==============

    **Batch Existence Check:**
    ```python
    from core.infrastructure.batch import BatchOperationHelper

    # Generate batch existence check query
    result = BatchOperationHelper.build_relationship_exists_query(
        node_label="Task",
        relationship_types=["REQUIRES_KNOWLEDGE", "DEPENDS_ON"],
        direction="outgoing",
        uids=task_uids,
    )
    records = await backend.execute_query(result.query, result.params)
    prereq_map = {r["uid"]: r["has_relationships"] for r in records}
    ```

    **Batch Relationship Building:**
    ```python
    relationships = BatchOperationHelper.build_relationships_list(
        source_uid=task_uid,
        relationship_specs=[
            (applies_knowledge_uids, "APPLIES_KNOWLEDGE", None),
            (prerequisite_uids, "REQUIRES_KNOWLEDGE", None),
        ],
    )
    await backend.create_relationships_batch(relationships)
    ```
    """

    # ========================================================================
    # BATCH QUERY BUILDERS
    # ========================================================================

    @staticmethod
    def build_relationship_exists_query(
        node_label: str,
        relationship_types: list[str],
        direction: Literal["incoming", "outgoing", "both"] = "outgoing",
        uids: list[str] | None = None,
    ) -> BatchQueryResult:
        """
        Generate UNWIND query to check relationship existence for multiple entities.

        **PERFORMANCE OPTIMIZATION:**
        Eliminates N sequential existence checks by processing multiple entities
        in a single database round trip using UNWIND.

        Args:
            node_label: Neo4j node label (e.g., "Task", "Goal", "Habit")
            relationship_types: List of relationship types to check
            direction: Traversal direction ("outgoing", "incoming", or "both")
            uids: Optional list of UIDs to check (passed as parameter at runtime)

        Returns:
            BatchQueryResult with query and params ready for execution

        Result Format:
            [{"uid": "task:1", "has_relationships": True}, ...]

        Examples:
            # Batch check prerequisites for 100 tasks
            result = BatchOperationHelper.build_relationship_exists_query(
                node_label="Task",
                relationship_types=["REQUIRES_KNOWLEDGE", "REQUIRES_PREREQUISITE"],
                direction="outgoing"
            )
            records = await backend.execute_query(result.query, {"uids": task_uids})
            # Returns: [{"uid": "task:1", "has_relationships": True}, ...]

            # Batch check if goals have habit support
            result = BatchOperationHelper.build_relationship_exists_query(
                node_label="Goal",
                relationship_types=["REQUIRES_HABIT"],
                direction="outgoing"
            )
        """
        pattern = _build_match_pattern(direction)

        query = f"""
        UNWIND $uids as uid
        MATCH (n:{node_label} {{uid: uid}})
        OPTIONAL MATCH {pattern}
        WHERE type(r) IN $relationship_types
        WITH uid, count(r) as rel_count
        RETURN uid, rel_count > 0 as has_relationships
        """

        return BatchQueryResult(
            query=query.strip(),
            params={"uids": uids or [], "relationship_types": relationship_types},
        )

    @staticmethod
    def build_relationship_count_query(
        node_label: str,
        relationship_types: list[str],
        direction: Literal["incoming", "outgoing", "both"] = "outgoing",
        uids: list[str] | None = None,
    ) -> BatchQueryResult:
        """
        Generate UNWIND query to count relationships for multiple entities.

        Similar to build_relationship_exists_query() but returns actual counts
        instead of boolean existence.

        Args:
            node_label: Neo4j node label (e.g., "Task", "Goal", "Habit")
            relationship_types: List of relationship types to count
            direction: Traversal direction ("outgoing", "incoming", or "both")
            uids: Optional list of UIDs to check (passed as parameter at runtime)

        Returns:
            BatchQueryResult with query and params ready for execution

        Result Format:
            [{"uid": "task:1", "count": 5}, ...]

        Examples:
            # Batch count prerequisites for 100 tasks
            result = BatchOperationHelper.build_relationship_count_query(
                node_label="Task",
                relationship_types=["REQUIRES_KNOWLEDGE", "DEPENDS_ON"],
                direction="outgoing"
            )
            records = await backend.execute_query(result.query, {"uids": task_uids})
            count_map = {r["uid"]: r["count"] for r in records}
        """
        pattern = _build_match_pattern(direction)

        query = f"""
        UNWIND $uids as uid
        MATCH (n:{node_label} {{uid: uid}})
        OPTIONAL MATCH {pattern}
        WHERE type(r) IN $relationship_types
        WITH uid, count(r) as rel_count
        RETURN uid, rel_count as count
        """

        return BatchQueryResult(
            query=query.strip(),
            params={"uids": uids or [], "relationship_types": relationship_types},
        )

    @staticmethod
    def build_relationship_properties_query(
        relationships: list[tuple[str, str, str]],
    ) -> BatchQueryResult:
        """
        Generate UNWIND query to fetch properties for multiple relationships.

        Used for bulk retrieval of relationship metadata (confidence, timestamps, etc.)

        Args:
            relationships: List of (from_uid, to_uid, rel_type) tuples

        Returns:
            BatchQueryResult with query and params ready for execution

        Result Format:
            [{"from_uid": "...", "to_uid": "...", "rel_type": "...", "props": {...}}, ...]

        Example:
            rels = [
                ("task:123", "ku:python", "APPLIES_KNOWLEDGE"),
                ("task:123", "ku:algorithms", "REQUIRES_KNOWLEDGE"),
            ]
            result = BatchOperationHelper.build_relationship_properties_query(rels)
            records = await backend.execute_query(result.query, result.params)
        """
        query = """
        UNWIND $rels as rel
        OPTIONAL MATCH (a {uid: rel.from_uid})-[r]->(b {uid: rel.to_uid})
        WHERE type(r) = rel.rel_type
        RETURN rel.from_uid as from_uid, rel.to_uid as to_uid, rel.rel_type as rel_type, properties(r) as props
        """

        rels_data = [
            {"from_uid": from_uid, "to_uid": to_uid, "rel_type": rel_type}
            for from_uid, to_uid, rel_type in relationships
        ]

        return BatchQueryResult(query=query.strip(), params={"rels": rels_data})

    @staticmethod
    def build_relationship_delete_query(
        relationships: list[tuple[str, str, str]],
    ) -> BatchQueryResult:
        """
        Generate UNWIND query to delete multiple relationships.

        Idempotent - no error if relationships don't exist.

        Args:
            relationships: List of (from_uid, to_uid, rel_type) tuples

        Returns:
            BatchQueryResult with query and params ready for execution

        Result Format:
            Single record with {"deleted_count": N}

        Example:
            rels = [
                ("task:123", "ku:python", "APPLIES_KNOWLEDGE"),
                ("task:123", "ku:algorithms", "REQUIRES_KNOWLEDGE"),
            ]
            result = BatchOperationHelper.build_relationship_delete_query(rels)
            records = await backend.execute_query(result.query, result.params)
            deleted_count = records[0]["deleted_count"] if records else 0
        """
        query = """
        UNWIND $rels as rel
        MATCH (a {uid: rel.from_uid})-[r]-(b {uid: rel.to_uid})
        WHERE type(r) = rel.rel_type
        DELETE r
        RETURN count(r) as deleted_count
        """

        rels_data = [
            {"from_uid": from_uid, "to_uid": to_uid, "rel_type": rel_type}
            for from_uid, to_uid, rel_type in relationships
        ]

        return BatchQueryResult(query=query.strip(), params={"rels": rels_data})

    @staticmethod
    def build_multi_direction_count_queries(
        requests: list[tuple[str, str, str | None]],
    ) -> dict[str, BatchQueryResult]:
        """
        Generate optimized UNWIND queries for multi-direction relationship counts.

        Groups requests by direction and generates one query per direction,
        reducing 3N queries to 3 queries maximum.

        Args:
            requests: List of (uid, rel_type, direction) tuples
                     direction is "outgoing", "incoming", "both", or None (defaults to "outgoing")

        Returns:
            Dict mapping direction to BatchQueryResult:
            {"outgoing": BatchQueryResult, "incoming": BatchQueryResult, "both": BatchQueryResult}

        Example:
            requests = [
                ("task:1", "DEPENDS_ON", "outgoing"),
                ("task:2", "DEPENDS_ON", "outgoing"),
                ("goal:1", "SUPPORTS_GOAL", "incoming"),
            ]
            queries = BatchOperationHelper.build_multi_direction_count_queries(requests)

            # Execute each direction's query
            for direction, query_result in queries.items():
                records = await backend.execute_query(query_result.query, query_result.params)
        """
        # Group by direction
        outgoing: list[tuple[str, str]] = []
        incoming: list[tuple[str, str]] = []
        both: list[tuple[str, str]] = []

        for uid, rel_type, direction in requests:
            dir_normalized = direction or "outgoing"
            if dir_normalized == "outgoing":
                outgoing.append((uid, rel_type))
            elif dir_normalized == "incoming":
                incoming.append((uid, rel_type))
            else:
                both.append((uid, rel_type))

        results: dict[str, BatchQueryResult] = {}

        if outgoing:
            query = """
            UNWIND $pairs as pair
            MATCH (n {uid: pair.uid})-[r]->(related)
            WHERE type(r) = pair.rel_type
            RETURN pair.uid as uid, pair.rel_type as rel_type, count(r) as count
            """
            pairs_data = [{"uid": uid, "rel_type": rel_type} for uid, rel_type in outgoing]
            results["outgoing"] = BatchQueryResult(
                query=query.strip(), params={"pairs": pairs_data}
            )

        if incoming:
            query = """
            UNWIND $pairs as pair
            MATCH (n {uid: pair.uid})<-[r]-(related)
            WHERE type(r) = pair.rel_type
            RETURN pair.uid as uid, pair.rel_type as rel_type, count(r) as count
            """
            pairs_data = [{"uid": uid, "rel_type": rel_type} for uid, rel_type in incoming]
            results["incoming"] = BatchQueryResult(
                query=query.strip(), params={"pairs": pairs_data}
            )

        if both:
            query = """
            UNWIND $pairs as pair
            MATCH (n {uid: pair.uid})-[r]-(related)
            WHERE type(r) = pair.rel_type
            RETURN pair.uid as uid, pair.rel_type as rel_type, count(r) as count
            """
            pairs_data = [{"uid": uid, "rel_type": rel_type} for uid, rel_type in both]
            results["both"] = BatchQueryResult(query=query.strip(), params={"pairs": pairs_data})

        return results

    # ========================================================================
    # BATCH QUERY BUILDERS WITH PROPERTY FILTERS
    # ========================================================================

    @staticmethod
    def build_relationship_exists_with_filters_query(
        node_label: str,
        relationship_types: list[str],
        direction: Literal["incoming", "outgoing", "both"] = "outgoing",
        property_filters: dict[str, Any] | None = None,
        uids: list[str] | None = None,
    ) -> BatchQueryResult:
        """
        Generate UNWIND query to check relationship existence with property filtering.

        Enhanced version of build_relationship_exists_query() that supports
        filtering relationships by their properties (e.g., confidence, strength).

        Args:
            node_label: Neo4j node label (e.g., "Ku", "Task")
            relationship_types: List of relationship types to check
            direction: Traversal direction ("outgoing", "incoming", or "both")
            property_filters: Optional filters for relationship properties
                            Format: {"property_name__operator": value}
                            Operators: gte, lte, gt, lt, eq, ne
                            Example: {"strength__gte": 0.8, "confidence__gt": 0.7}
            uids: Optional list of UIDs to check (passed as parameter at runtime)

        Returns:
            BatchQueryResult with query and params ready for execution

        Result Format:
            [{"uid": "ku:1", "has_relationships": True}, ...]

        Examples:
            # Find knowledge units with high-confidence prerequisites
            result = BatchOperationHelper.build_relationship_exists_with_filters_query(
                node_label="Ku",
                relationship_types=["REQUIRES_KNOWLEDGE"],
                direction="outgoing",
                property_filters={"strength__gte": 0.8}
            )
            records = await backend.execute_query(result.query, {"uids": ku_uids})

            # Find tasks with critical knowledge requirements
            result = BatchOperationHelper.build_relationship_exists_with_filters_query(
                node_label="Task",
                relationship_types=["REQUIRES_KNOWLEDGE"],
                direction="outgoing",
                property_filters={"knowledge_score_required__gte": 0.7}
            )

        Use Cases:
            - Knowledge graphs: Filter by relationship confidence/strength
            - Task prioritization: Find tasks requiring high mastery
            - Learning paths: Filter by prerequisite strength
            - Quality control: Only consider high-confidence relationships
        """
        # Validate direction
        if direction not in ("outgoing", "incoming", "both"):
            raise ValueError(
                f"Invalid direction: {direction}. Valid options: outgoing, incoming, both"
            )

        pattern = _build_match_pattern(direction)

        # Build WHERE clause with type and property filters
        where_clauses = ["type(r) IN $relationship_types"]
        params: dict[str, Any] = {
            "uids": uids or [],
            "relationship_types": relationship_types,
        }

        # Parse and add property filters
        filter_clauses, filter_params = _parse_property_filters(property_filters)
        where_clauses.extend(filter_clauses)
        params.update(filter_params)

        where_clause = " AND ".join(where_clauses)

        query = f"""
        UNWIND $uids as uid
        MATCH (n:{node_label} {{uid: uid}})
        OPTIONAL MATCH {pattern}
        WHERE {where_clause}
        WITH uid, count(r) as rel_count
        RETURN uid, rel_count > 0 as has_relationships
        """

        return BatchQueryResult(query=query.strip(), params=params)

    @staticmethod
    def build_get_related_with_filters_query(
        node_label: str,
        relationship_types: list[str],
        direction: Literal["incoming", "outgoing", "both"] = "outgoing",
        property_filters: dict[str, Any] | None = None,
        limit_per_node: int = 100,
        uids: list[str] | None = None,
    ) -> BatchQueryResult:
        """
        Generate UNWIND query to get related entity UIDs with property filtering.

        Batch query that returns lists of related entity UIDs for multiple source nodes,
        with optional filtering by relationship properties.

        Args:
            node_label: Neo4j node label (e.g., "Ku", "Task")
            relationship_types: List of relationship types to traverse
            direction: Traversal direction ("outgoing", "incoming", or "both")
            property_filters: Optional filters for relationship properties
            limit_per_node: Maximum related entities to return per source node
            uids: Optional list of UIDs to query (passed as parameter at runtime)

        Returns:
            BatchQueryResult with query and params ready for execution

        Result Format:
            [{"uid": "ku:python", "related_uids": ["ku:basics", "ku:functions"]}, ...]

        Examples:
            # Get high-strength prerequisites for multiple knowledge units
            result = BatchOperationHelper.build_get_related_with_filters_query(
                node_label="Ku",
                relationship_types=["REQUIRES_KNOWLEDGE"],
                direction="outgoing",
                property_filters={"strength__gte": 0.8},
                limit_per_node=50
            )
            records = await backend.execute_query(result.query, {"uids": ku_uids})

            # Get tasks with high knowledge requirements
            result = BatchOperationHelper.build_get_related_with_filters_query(
                node_label="Task",
                relationship_types=["REQUIRES_KNOWLEDGE"],
                direction="outgoing",
                property_filters={"knowledge_score_required__gte": 0.7}
            )

        Use Cases:
            - Knowledge graphs: Get strong prerequisites for learning paths
            - Dependency analysis: Find critical dependencies
            - Recommendation systems: Filter by relationship quality
        """
        # Validate direction
        if direction not in ("outgoing", "incoming", "both"):
            raise ValueError(
                f"Invalid direction: {direction}. Valid options: outgoing, incoming, both"
            )

        pattern = _build_match_pattern(direction)

        # Build WHERE clause
        where_clauses = ["type(r) IN $relationship_types"]
        params: dict[str, Any] = {
            "uids": uids or [],
            "relationship_types": relationship_types,
            "limit_per_node": limit_per_node,
        }

        # Parse and add property filters
        filter_clauses, filter_params = _parse_property_filters(property_filters)
        where_clauses.extend(filter_clauses)
        params.update(filter_params)

        where_clause = " AND ".join(where_clauses)

        query = f"""
        UNWIND $uids as uid
        MATCH (n:{node_label} {{uid: uid}})
        OPTIONAL MATCH {pattern}
        WHERE {where_clause}
        WITH uid, collect(related.uid)[0..$limit_per_node] as related_uids
        RETURN uid, related_uids
        """

        return BatchQueryResult(query=query.strip(), params=params)

    # ========================================================================
    # BATCH RELATIONSHIP CREATION (Pure Cypher)
    # ========================================================================

    @staticmethod
    def group_relationships_by_type(
        relationships: list[tuple[str, str, str, dict[str, Any] | None]],
    ) -> dict[str, list[tuple[str, str, dict[str, Any]]]]:
        """
        Group relationships by type for pure Cypher batch creation.

        Pure Cypher requires literal relationship types in queries. This groups
        relationships so we can generate one UNWIND query per relationship type.

        Args:
            relationships: List of (from_uid, to_uid, rel_type, properties) tuples

        Returns:
            Dict mapping rel_type to list of (from_uid, to_uid, properties) tuples

        Example:
            rels = [
                ("task:1", "ku:a", "APPLIES_KNOWLEDGE", None),
                ("task:1", "ku:b", "APPLIES_KNOWLEDGE", {"confidence": 0.9}),
                ("task:1", "goal:1", "FULFILLS_GOAL", None),
            ]
            grouped = BatchOperationHelper.group_relationships_by_type(rels)
            # {"APPLIES_KNOWLEDGE": [("task:1", "ku:a", {}), ("task:1", "ku:b", {"confidence": 0.9})],
            #  "FULFILLS_GOAL": [("task:1", "goal:1", {})]}
        """
        by_type: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
        for from_uid, to_uid, rel_type, props in relationships:
            if rel_type not in by_type:
                by_type[rel_type] = []
            by_type[rel_type].append((from_uid, to_uid, props or {}))
        return by_type

    @staticmethod
    def build_relationship_create_query(rel_type: str) -> str:
        """
        Build UNWIND query for creating relationships of a specific type.

        Pure Cypher approach - relationship type is literal in the query.

        Args:
            rel_type: The relationship type (e.g., "APPLIES_KNOWLEDGE")

        Returns:
            Cypher query string expecting $rels parameter with
            [{from_uid, to_uid, properties}, ...] format

        Example:
            query = BatchOperationHelper.build_relationship_create_query("APPLIES_KNOWLEDGE")
            rels_data = [{"from_uid": "task:1", "to_uid": "ku:a", "properties": {}}]
            result = await session.run(query, {"rels": rels_data})
        """
        return f"""
        UNWIND $rels AS rel
        MATCH (a {{uid: rel.from_uid}})
        MATCH (b {{uid: rel.to_uid}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += rel.properties
        RETURN count(r) as created_count
        """.strip()

    @staticmethod
    def build_relationship_create_queries(
        relationships: list[tuple[str, str, str, dict[str, Any] | None]],
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        """
        Build all queries needed to create a batch of relationships.

        Groups relationships by type and generates (query, params) tuples
        for each type. This is the main entry point for batch creation.

        Args:
            relationships: List of (from_uid, to_uid, rel_type, properties) tuples

        Returns:
            List of (query, rels_data) tuples ready for execution.
            Each query creates relationships of one type.

        Example:
            queries = BatchOperationHelper.build_relationship_create_queries([
                ("task:1", "ku:a", "APPLIES_KNOWLEDGE", None),
                ("task:1", "goal:1", "FULFILLS_GOAL", None),
            ])

            # Execute each query
            total_created = 0
            async with driver.session() as session:
                for query, rels_data in queries:
                    result = await session.run(query, {"rels": rels_data})
                    record = await result.single()
                    total_created += record["created_count"] if record else 0
        """
        if not relationships:
            return []

        by_type = BatchOperationHelper.group_relationships_by_type(relationships)

        queries: list[tuple[str, list[dict[str, Any]]]] = []
        for rel_type, rels in by_type.items():
            query = BatchOperationHelper.build_relationship_create_query(rel_type)
            rels_data = [{"from_uid": f, "to_uid": t, "properties": p} for f, t, p in rels]
            queries.append((query, rels_data))

        return queries

    # ========================================================================
    # RELATIONSHIP LIST BUILDERS (Pure Python)
    # ========================================================================

    @staticmethod
    def build_relationships_list(
        source_uid: str,
        relationship_specs: list[tuple[list[str] | None, str, dict[str, Any] | None]],
    ) -> list[tuple[str, str, str, dict[str, Any] | None]]:
        """
        Build flattened relationship list for batch creation.

        This replaces the repeated pattern in all 12 relationship services:
            if applies_knowledge_uids:
                relationships.extend(...)
            if prerequisite_knowledge_uids:
                relationships.extend(...)

        **DRY Benefit:** Reduces ~10-15 lines per service method to 1 line.

        Args:
            source_uid: The source entity UID (e.g., task_uid, goal_uid)
            relationship_specs: List of (target_uids, rel_type, properties) tuples
                - target_uids: List of target UIDs (can be None/empty - will be skipped)
                - rel_type: Relationship type string (e.g., "APPLIES_KNOWLEDGE")
                - properties: Optional dict of relationship properties

        Returns:
            Flattened list of (from_uid, to_uid, rel_type, properties) tuples
            ready for backend.create_relationships_batch()

        Example:
            # Before (TasksRelationshipService - 15+ lines)
            relationships = []
            if applies_knowledge_uids:
                relationships.extend(
                    (task_uid, ku_uid, "APPLIES_KNOWLEDGE", None)
                    for ku_uid in applies_knowledge_uids
                )
            if prerequisite_knowledge_uids:
                relationships.extend(
                    (task_uid, ku_uid, "REQUIRES_KNOWLEDGE", None)
                    for ku_uid in prerequisite_knowledge_uids
                )
            # ... 7 more similar blocks

            # After (1 line)
            relationships = BatchOperationHelper.build_relationships_list(
                source_uid=task_uid,
                relationship_specs=[
                    (applies_knowledge_uids, "APPLIES_KNOWLEDGE", None),
                    (prerequisite_knowledge_uids, "REQUIRES_KNOWLEDGE", None),
                    (prerequisite_task_uids, "REQUIRES_PREREQUISITE", None),
                    (aligned_principle_uids, "ALIGNED_WITH_PRINCIPLE", None),
                    (subtask_uids, "HAS_CHILD", None),
                    (enables_task_uids, "ENABLES_TASK", None),
                    (completion_triggers_tasks, "TRIGGERS_ON_COMPLETION", None),
                    (completion_unlocks_knowledge, "UNLOCKS_KNOWLEDGE", None),
                    (inferred_knowledge_uids, "INFERRED_KNOWLEDGE", None),
                ]
            )
        """
        relationships: list[tuple[str, str, str, dict[str, Any] | None]] = []

        for target_uids, rel_type, properties in relationship_specs:
            if target_uids:
                relationships.extend(
                    (source_uid, target_uid, rel_type, properties) for target_uid in target_uids
                )

        return relationships

    @staticmethod
    def build_relationships_list_with_essentiality(
        source_uid: str,
        relationship_specs: list[tuple[list[str] | None, str, str]],
    ) -> list[tuple[str, str, str, dict[str, Any] | None]]:
        """
        Build flattened relationship list with essentiality property.

        Specialized version for Goal→Habit relationships where essentiality
        varies by category (essential, critical, supporting, optional).

        Args:
            source_uid: The source entity UID (e.g., goal_uid)
            relationship_specs: List of (target_uids, rel_type, essentiality) tuples
                - target_uids: List of target UIDs
                - rel_type: Relationship type (typically "REQUIRES_HABIT")
                - essentiality: String value (essential/critical/supporting/optional)

        Returns:
            Flattened list with {"essentiality": value} in properties

        Example:
            # Before (GoalsRelationshipService - 20+ lines)
            if essential_habit_uids:
                relationships.extend(
                    (goal_uid, habit_uid, "REQUIRES_HABIT", {"essentiality": "essential"})
                    for habit_uid in essential_habit_uids
                )
            if critical_habit_uids:
                relationships.extend(...)
            # ... more blocks

            # After (1 line)
            relationships = BatchOperationHelper.build_relationships_list_with_essentiality(
                source_uid=goal_uid,
                relationship_specs=[
                    (essential_habit_uids, "REQUIRES_HABIT", "essential"),
                    (critical_habit_uids, "REQUIRES_HABIT", "critical"),
                    (supporting_habit_uids, "REQUIRES_HABIT", "supporting"),
                    (optional_habit_uids, "REQUIRES_HABIT", "optional"),
                ]
            )
        """
        relationships: list[tuple[str, str, str, dict[str, Any] | None]] = []

        for target_uids, rel_type, essentiality in relationship_specs:
            if target_uids:
                properties = {"essentiality": essentiality}
                relationships.extend(
                    (source_uid, target_uid, rel_type, properties) for target_uid in target_uids
                )

        return relationships


# ============================================================================
# PRIVATE HELPER FUNCTIONS
# ============================================================================


def _build_match_pattern(direction: str) -> str:
    """
    Build Neo4j OPTIONAL MATCH pattern for direction.

    Used in batch queries where we match nodes with uid variable.

    Args:
        direction: "incoming", "outgoing", or "both"

    Returns:
        Full OPTIONAL MATCH pattern like "(n)-[r]->(related)"
    """
    if direction == "outgoing":
        return "(n)-[r]->(related)"
    elif direction == "incoming":
        return "(n)<-[r]-(related)"
    else:  # both
        return "(n)-[r]-(related)"


# Operator mapping for property filters
_FILTER_OP_MAP = {
    "gte": ">=",
    "lte": "<=",
    "gt": ">",
    "lt": "<",
    "eq": "=",
    "ne": "<>",
}


def _parse_property_filters(
    property_filters: dict[str, Any] | None,
) -> tuple[list[str], dict[str, Any]]:
    """
    Parse property filters into WHERE clauses and parameters.

    Args:
        property_filters: Dict of {property__operator: value} filters
            Operators: gte, lte, gt, lt, eq, ne

    Returns:
        Tuple of (where_clauses, params)
        - where_clauses: List of SQL-like conditions (e.g., "r.strength >= $filter_strength")
        - params: Dict of parameter values (e.g., {"filter_strength": 0.8})

    Example:
        filters = {"strength__gte": 0.8, "confidence__gt": 0.7}
        clauses, params = _parse_property_filters(filters)
        # clauses = ["r.strength >= $filter_strength", "r.confidence > $filter_confidence"]
        # params = {"filter_strength": 0.8, "filter_confidence": 0.7}
    """
    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if not property_filters:
        return where_clauses, params

    for filter_expr, value in property_filters.items():
        # Parse filter expression (e.g., "strength__gte" -> property="strength", op="gte")
        if "__" in filter_expr:
            property_name, operator = filter_expr.rsplit("__", 1)
        else:
            property_name = filter_expr
            operator = "eq"

        if operator not in _FILTER_OP_MAP:
            raise ValueError(f"Invalid operator: {operator}. Valid: {list(_FILTER_OP_MAP.keys())}")

        # Add property filter to WHERE clause
        param_name = f"filter_{property_name}"
        where_clauses.append(f"r.{property_name} {_FILTER_OP_MAP[operator]} ${param_name}")
        params[param_name] = value

    return where_clauses, params


def _build_direction_pattern(direction: str) -> str:
    """
    Build Neo4j relationship pattern for direction (partial pattern).

    Args:
        direction: "incoming", "outgoing", or "both"

    Returns:
        Cypher pattern string with [r] relationship variable
    """
    if direction == "incoming":
        return "<-[r]-"
    elif direction == "outgoing":
        return "-[r]->"
    else:  # both
        return "-[r]-"
