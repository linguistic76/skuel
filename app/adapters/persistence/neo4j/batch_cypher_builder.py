"""
BatchCypherBuilder - UNWIND Batch Operations for Neo4j
======================================================

One builder for the UNWIND-based batch Cypher the relationship mixins run.

Core Principle: "One query builder, many consumers"

Pattern Categories:
==================

1. **Batch Properties Fetch** - Get relationship properties for multiple edges
   - Used by: ``_RelationshipQueryMixin.get_relationships_batch``
   - Query: UNWIND $rels → fetch properties → return properties list

2. **Batch Deletion** - Delete multiple relationships in single transaction
   - Used by: ``_RelationshipCrudMixin.delete_relationships_batch``
   - Query: UNWIND $rels → delete matches → return deleted count

3. **Multi-Direction Counts** - Count relationships per (uid, type) in each direction
   - Used by: ``_RelationshipQueryMixin.count_relationships_batch``
   - Query: one UNWIND $pairs statement per direction → count map

4. **Batch Relationship Creation** - One UNWIND MERGE statement per relationship type
   - Used by: ``_RelationshipCrudMixin.create_relationships_batch``,
     ``Neo4jQueryExecutor.create_relationships_batch``
   - Query: group by type → UNWIND $rels → MERGE → return created count

5. **Batch Relationship Building** - Flatten UID lists into the
   (from, to, type, props) tuples ``create_relationships_batch`` takes
   - Pure Python; unit-tested, no production call site

Existence checks and counts over a list of uids are backend reads, not builders
here: ``batch_get_related_uids`` (``_RelationshipCrudMixin``, under the owner
far-node scope) and ``count_relationships_batch`` (``_RelationshipQueryMixin``,
one count per (uid, type, direction) request).

Performance Impact:
==================
- Before: N queries x 15-60ms = N x 15-60ms (1.5-6 seconds for 100 items)
- After: 1 query x 50-200ms = 50-200ms
- Improvement: 10-100x faster for bulk operations
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BatchQueryResult:
    """
    Standardized result from batch query builders.

    Attributes:
        query: The Cypher query string (parameterized)
        params: Dictionary of query parameters

    Usage:
        result = BatchCypherBuilder.build_relationship_delete_query(relationships)
        records = await backend.execute_query(result.query, result.params)
    """

    query: str
    params: dict[str, Any]


class BatchCypherBuilder:
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

    **Batch Properties Fetch:**
    ```python
    from adapters.persistence.neo4j.batch_cypher_builder import BatchCypherBuilder

    result = BatchCypherBuilder.build_relationship_properties_query(
        [("task_1", "ku.python.basics", "APPLIES_KNOWLEDGE")],
    )
    records = await backend.execute_query(result.query, result.params)
    ```

    **Batch Relationship Building:**
    ```python
    relationships = BatchCypherBuilder.build_relationships_list(
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
            result = BatchCypherBuilder.build_relationship_properties_query(rels)
            records = await backend.execute_query(result.query, result.params)
        """
        # NOT :Content — chunk-store shadow nodes share their entity's uid; an
        # unguarded uid MATCH binds both and duplicates rows (G13).
        query = """
        UNWIND $rels as rel
        OPTIONAL MATCH (a {uid: rel.from_uid})-[r]->(b {uid: rel.to_uid})
        WHERE type(r) = rel.rel_type AND NOT a:Content AND NOT b:Content
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
            result = BatchCypherBuilder.build_relationship_delete_query(rels)
            records = await backend.execute_query(result.query, result.params)
            deleted_count = records[0]["deleted_count"] if records else 0
        """
        # NOT :Content — G13 shadow-uid guard (see build_relationship_create_query).
        query = """
        UNWIND $rels as rel
        MATCH (a {uid: rel.from_uid})-[r]-(b {uid: rel.to_uid})
        WHERE type(r) = rel.rel_type AND NOT a:Content AND NOT b:Content
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
            queries = BatchCypherBuilder.build_multi_direction_count_queries(requests)

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

        # NOT :Content in all three below — G13 shadow-uid guard
        # (see build_relationship_create_query).
        if outgoing:
            query = """
            UNWIND $pairs as pair
            MATCH (n {uid: pair.uid})-[r]->(related)
            WHERE type(r) = pair.rel_type AND NOT n:Content
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
            WHERE type(r) = pair.rel_type AND NOT n:Content
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
            WHERE type(r) = pair.rel_type AND NOT n:Content
            RETURN pair.uid as uid, pair.rel_type as rel_type, count(r) as count
            """
            pairs_data = [{"uid": uid, "rel_type": rel_type} for uid, rel_type in both]
            results["both"] = BatchQueryResult(query=query.strip(), params={"pairs": pairs_data})

        return results

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
                ("task:1", "goal:1", "CONTRIBUTES_TO_GOAL", None),
            ]
            grouped = BatchCypherBuilder.group_relationships_by_type(rels)
            # {"APPLIES_KNOWLEDGE": [("task:1", "ku:a", {}), ("task:1", "ku:b", {"confidence": 0.9})],
            #  "CONTRIBUTES_TO_GOAL": [("task:1", "goal:1", {})]}
        """
        by_type: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
        for from_uid, to_uid, rel_type, props in relationships:
            if rel_type not in by_type:
                by_type[rel_type] = []
            by_type[rel_type].append((from_uid, to_uid, props or {}))
        return by_type

    @staticmethod
    def build_relationship_create_query(
        rel_type: str, endpoint_label: str | None = "Entity"
    ) -> str:
        """
        Build UNWIND query for creating relationships of a specific type.

        Pure Cypher approach - relationship type is literal in the query.

        ``endpoint_label`` guards against the chunk store's ``:Content`` shadow
        nodes, which keep the SAME uid as their entity — an unguarded
        ``MATCH {uid}`` binds both and duplicates every edge (found live:
        doubled INTERACTION_DURING, systems review 2026-07-03):

        - ``"Entity"`` (default) — both endpoints bound to ``:Entity``. Right
          for registry-validated entity↔entity edges
          (``create_relationships_batch`` on the universal backend).
        - ``None`` — unlabeled endpoints for mixed-label batches
          (User→Goal PURSUING_GOAL, User→User FOLLOWS, User→Group MEMBER_OF via
          ``Neo4jQueryExecutor``), with an explicit ``NOT :Content`` exclusion
          so entity endpoints in those batches still can't double-bind.

        Args:
            rel_type: The relationship type (e.g., "APPLIES_KNOWLEDGE")

        Returns:
            Cypher query string expecting $rels parameter with
            [{from_uid, to_uid, properties}, ...] format

        Example:
            query = BatchCypherBuilder.build_relationship_create_query("APPLIES_KNOWLEDGE")
            rels_data = [{"from_uid": "task:1", "to_uid": "ku:a", "properties": {}}]
            result = await session.run(query, {"rels": rels_data})
        """
        if endpoint_label is not None:
            return f"""
        UNWIND $rels AS rel
        MATCH (a:{endpoint_label} {{uid: rel.from_uid}})
        MATCH (b:{endpoint_label} {{uid: rel.to_uid}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += rel.properties
        RETURN count(r) as created_count
        """.strip()
        return f"""
        UNWIND $rels AS rel
        MATCH (a {{uid: rel.from_uid}})
        WHERE NOT a:Content
        MATCH (b {{uid: rel.to_uid}})
        WHERE NOT b:Content
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += rel.properties
        RETURN count(r) as created_count
        """.strip()

    @staticmethod
    def build_relationship_create_queries(
        relationships: list[tuple[str, str, str, dict[str, Any] | None]],
        endpoint_label: str | None = "Entity",
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        """
        Build all queries needed to create a batch of relationships.

        Groups relationships by type and generates (query, params) tuples
        for each type. This is the main entry point for batch creation.

        Args:
            relationships: List of (from_uid, to_uid, rel_type, properties) tuples
            endpoint_label: Endpoint binding forwarded to
                ``build_relationship_create_query`` — ``"Entity"`` for
                entity↔entity batches, ``None`` for mixed User/Group batches
                (see that method's docstring for the :Content-shadow rationale)

        Returns:
            List of (query, rels_data) tuples ready for execution.
            Each query creates relationships of one type.

        Example:
            queries = BatchCypherBuilder.build_relationship_create_queries([
                ("task:1", "ku:a", "APPLIES_KNOWLEDGE", None),
                ("task:1", "goal:1", "CONTRIBUTES_TO_GOAL", None),
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

        by_type = BatchCypherBuilder.group_relationships_by_type(relationships)

        queries: list[tuple[str, list[dict[str, Any]]]] = []
        for rel_type, rels in by_type.items():
            query = BatchCypherBuilder.build_relationship_create_query(
                rel_type, endpoint_label=endpoint_label
            )
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
            # Before (per-domain relationship service - 15+ lines)
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
            relationships = BatchCypherBuilder.build_relationships_list(
                source_uid=task_uid,
                relationship_specs=[
                    (applies_knowledge_uids, "APPLIES_KNOWLEDGE", None),
                    (prerequisite_knowledge_uids, "REQUIRES_KNOWLEDGE", None),
                    (prerequisite_task_uids, "BLOCKED_BY", None),
                    (aligned_principle_uids, "ALIGNED_WITH_PRINCIPLE", None),
                    (subtask_uids, "HAS_SUBTASK", None),
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
