"""
Traversal Mixin
===============

GraphTraversalOperations protocol compliance methods.

Provides:
    add_relationship: Protocol-compliant wrapper around create_relationship()
    get_relationships: Get all relationships for an entity
    traverse: Multi-hop graph traversal from a start node
    find_path: Shortest path between two entities

Requires on concrete class:
    driver, logger, create_relationship
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j._backend_helpers import direction_clause
from core.models.relationship_names import RelationshipName
from core.utils.error_boundary import safe_backend_operation
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel
    from core.ports.base_protocols import Direction


class _TraversalMixin:
    """
    GraphTraversalOperations protocol methods.

    Requires on concrete class:
        driver: AsyncDriver — Neo4j async driver
        logger: logging.Logger — Logger instance
        create_relationship: async method
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        logger: logging.Logger

        async def create_relationship(
            self,
            from_uid: str,
            to_uid: str,
            relationship_type: RelationshipName,
            properties: dict[str, Any] | None = None,
        ) -> Result[bool]: ...

        async def execute_query(
            self,
            query: str,
            params: dict[str, Any] | None = None,
        ) -> Result[list[dict[str, Any]]]: ...

    # ============================================================================
    # PROTOCOL COMPLIANCE METHODS (November 28, 2025)
    # ============================================================================
    # These methods implement the Supports* protocols required by BaseService.
    # They provide protocol-compliant signatures that delegate to existing methods.

    async def add_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Add a relationship between entities.

        Protocol: RelationshipCrudOperations, SupportsRelationships

        Delegates to create_relationship() with protocol-compliant signature.

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            relationship_type: Relationship type (e.g., RelationshipName.APPLIES_KNOWLEDGE)
            properties: Optional relationship properties

        Returns:
            Result[bool]: True if relationship created/updated
        """
        return await self.create_relationship(
            from_uid=from_uid,
            to_uid=to_uid,
            relationship_type=relationship_type,
            properties=properties,
        )

    @safe_backend_operation("get_relationships")
    async def get_relationships(
        self,
        uid: str,
        rel_type: RelationshipName | None = None,
        direction: Direction = "both",
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get relationships for an entity.

        Protocol: SupportsRelationships

        Args:
            uid: Entity UID to get relationships for
            rel_type: Optional relationship type filter (e.g., RelationshipName.BLOCKS)
            direction: "outgoing", "incoming", or "both" (default)

        Returns:
            Result[list[dict]]: List of relationship data with:
                - type: Relationship type
                - target_uid: Connected entity UID
                - direction: "outgoing" or "incoming"
                - properties: Relationship properties
        """
        # Build direction-specific query; the WHERE clause is a no-op when
        # rel_type is None (no filter) and narrows to the named type otherwise.
        # NOT n:Content — the chunk store's shadow node shares its entity's
        # uid, so an unguarded uid MATCH double-binds and duplicates every
        # relationship row (G13). For directed traversals the direction is a
        # literal; "both" derives it per-edge from startNode().
        dir_expr = (
            "CASE WHEN startNode(r).uid = $uid THEN 'outgoing' ELSE 'incoming' END"
            if direction == "both"
            else f"'{direction}'"
        )
        cypher = f"""
        MATCH (n {{uid: $uid}}){direction_clause(direction)}(other)
        WHERE NOT n:Content AND ($rel_type IS NULL OR type(r) = $rel_type)
        RETURN type(r) as type, other.uid as target_uid,
               {dir_expr} as direction, properties(r) as properties
        """

        params = {"uid": uid, "rel_type": str(rel_type) if rel_type is not None else None}
        async with self.driver.session() as session:
            result = await session.run(cypher, params)
            records = await result.data()

        return Result.ok(records)

    @safe_backend_operation("traverse")
    async def traverse(
        self,
        start_uid: str,
        rel_pattern: str,
        max_depth: int = 3,
        include_properties: bool = False,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Traverse the graph from a starting point.

        Protocol: SupportsTraversal

        Args:
            start_uid: Starting entity UID
            rel_pattern: Relationship pattern (e.g., "REQUIRES", "REQUIRES|ENABLES")
            max_depth: Maximum traversal depth (default: 3)
            include_properties: Whether to include node properties in results

        Returns:
            Result[list[dict]]: List of traversed nodes with:
                - uid: Node UID
                - labels: Node labels
                - depth: Distance from start node
                - properties: Node properties (if include_properties=True)
        """
        # Validate rel_pattern segments before Cypher interpolation
        if rel_pattern:
            from core.utils.validation_helpers import validate_relationship_type

            for segment in rel_pattern.split("|"):
                if not validate_relationship_type(segment):
                    from core.utils.result_simplified import Errors

                    return Result.fail(
                        Errors.validation(
                            message=f"Invalid relationship type in pattern: {segment}",
                            field="rel_pattern",
                        )
                    )

        # Build relationship filter
        rel_filter = f":{rel_pattern}" if rel_pattern else ""

        if include_properties:
            cypher = f"""
            MATCH path = (start {{uid: $start_uid}})-[{rel_filter}*1..{max_depth}]-(node)
            UNWIND range(1, length(path)) as depth
            WITH node, depth, labels(node) as node_labels, properties(node) as props
            RETURN DISTINCT node.uid as uid, node_labels as labels,
                   min(depth) as depth, props as properties
            ORDER BY depth
            """
        else:
            cypher = f"""
            MATCH path = (start {{uid: $start_uid}})-[{rel_filter}*1..{max_depth}]-(node)
            UNWIND range(1, length(path)) as depth
            WITH node, depth, labels(node) as node_labels
            RETURN DISTINCT node.uid as uid, node_labels as labels, min(depth) as depth
            ORDER BY depth
            """

        async with self.driver.session() as session:
            result = await session.run(cypher, {"start_uid": start_uid})
            records = await result.data()

        return Result.ok(records)

    @safe_backend_operation("find_path")
    async def find_path(
        self,
        from_uid: str,
        to_uid: str,
        rel_types: builtins.list[str],
        max_depth: int = 5,
    ) -> Result[builtins.list[dict[str, Any]] | None]:
        """
        Find a path between two entities.

        Protocol: SupportsPathfinding

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            rel_types: Allowed relationship types for path
            max_depth: Maximum path length (default: 5)

        Returns:
            Result[list[dict] | None]: Path as list of nodes, or None if no path exists.
                Each node dict contains:
                - uid: Node UID
                - labels: Node labels
        """
        # Validate rel_types before Cypher interpolation
        if rel_types:
            from core.utils.validation_helpers import validate_relationship_type

            for rel_type in rel_types:
                if not validate_relationship_type(rel_type):
                    from core.utils.result_simplified import Errors

                    return Result.fail(
                        Errors.validation(
                            message=f"Invalid relationship type: {rel_type}",
                            field="rel_types",
                        )
                    )

        # Build relationship filter
        rel_filter = "|".join(rel_types) if rel_types else ""
        rel_clause = f":{rel_filter}" if rel_filter else ""

        cypher = f"""
        MATCH path = shortestPath(
            (start {{uid: $from_uid}})-[{rel_clause}*..{max_depth}]-(end {{uid: $to_uid}})
        )
        UNWIND nodes(path) as node
        RETURN node.uid as uid, labels(node) as labels
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"from_uid": from_uid, "to_uid": to_uid})
                records = await result.data()
        except NEO4J_EXCEPTIONS as e:
            # Neo4j returns error if no path exists in some versions
            if "no path" in str(e).lower():
                return Result.ok(None)
            raise  # Let @safe_backend_operation handle other errors

        if not records:
            return Result.ok(None)

        return Result.ok(records)

    # ========================================================================
    # SEMANTIC & CROSS-DOMAIN TRAVERSAL QUERIES
    # ========================================================================

    async def find_uids_by_semantic_filter(
        self,
        pattern: str,
        target_uid: str,
        min_confidence: float,
    ) -> Result[list[str]]:
        """Find entity UIDs matching a semantic relationship pattern."""
        cypher = f"""
        MATCH {pattern}
        WHERE target.uid = $target_uid
          AND r.confidence >= $min_confidence
        RETURN DISTINCT n.uid as uid
        """
        params = {"target_uid": target_uid, "min_confidence": min_confidence}
        result = await self.execute_query(cypher, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([str(row["uid"]) for row in result.value or [] if row.get("uid")])

    async def get_batch_cross_domain_context(
        self,
        entity_label: NeoLabel,
        entity_uids: list[str],
    ) -> Result[list[dict[str, Any]]]:
        """Batch-retrieve cross-domain relationship context for entities."""
        query = f"""
        UNWIND $entity_uids AS entity_uid
        MATCH (entity:{entity_label} {{uid: entity_uid}})
        OPTIONAL MATCH (entity)-[:SUPPORTS_GOAL]->(goal:Goal)
        OPTIONAL MATCH (entity)-[:ENABLES_KNOWLEDGE|:APPLIES_KNOWLEDGE]->(ku:Entity)
        OPTIONAL MATCH (entity)-[:FUNDS_HABIT]->(habit:Habit)
        OPTIONAL MATCH (entity)-[:FUNDS_TASK|:ENABLES_TASK]->(task:Task)
        OPTIONAL MATCH (entity)-[:INFORMED_BY_PRINCIPLE]->(principle:Principle)
        RETURN
            entity_uid,
            collect(DISTINCT goal) as goals,
            collect(DISTINCT ku) as knowledge,
            collect(DISTINCT habit) as habits,
            collect(DISTINCT task) as tasks,
            collect(DISTINCT principle) as principles
        """
        return await self.execute_query(query, {"entity_uids": entity_uids})

    async def get_goal_aligned_entities(
        self,
        user_uid: str,
        domain_name: str,
        entity_label: NeoLabel,
        goal_uid: str | None,
        limit: int,
    ) -> Result[list[dict[str, Any]]]:
        """Get entities aligned with user's goals via goal relationships."""
        goal_rels = [
            RelationshipName.FULFILLS_GOAL.value,
            RelationshipName.SUPPORTS_GOAL.value,
            RelationshipName.CONTRIBUTES_TO_GOAL.value,
        ]
        rel_pattern = "|".join(goal_rels)
        goal_filter = "WHERE g.uid = $goal_uid" if goal_uid else ""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:HAS_{domain_name.upper()}]->(e:{entity_label})
        MATCH (e)-[:{rel_pattern}]->(g:Goal)
        {goal_filter}
        RETURN DISTINCT e, collect(g.uid) as goal_uids
        ORDER BY size(collect(g.uid)) DESC
        LIMIT $limit
        """
        params: dict[str, Any] = {"user_uid": user_uid, "limit": limit}
        if goal_uid:
            params["goal_uid"] = goal_uid
        return await self.execute_query(query, params)

    async def get_citation_export(
        self,
        node_uid: str,
        node_label: NeoLabel,
        relationship_type: str,
        depth: int,
    ) -> Result[list[dict[str, Any]]]:
        """Execute a citation/provenance export query."""
        from adapters.persistence.neo4j.query._provenance_queries import ProvenanceQueries

        query, params = ProvenanceQueries.build_citation_export_query(
            node_uid=node_uid,
            node_label=node_label,
            relationship_type=relationship_type,
            depth=depth,
        )
        return await self.execute_query(query, params)
