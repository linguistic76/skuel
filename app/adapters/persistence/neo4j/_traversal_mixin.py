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

from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins

    from neo4j import AsyncDriver

    from core.ports.base_protocols import Direction


class _TraversalMixin:
    """
    GraphTraversalOperations protocol methods.

    Requires on concrete class:
        driver: AsyncDriver — Neo4j async driver
        logger: Any — Logger instance
        create_relationship: async method
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        logger: Any

        async def create_relationship(
            self,
            from_uid: str,
            to_uid: str,
            relationship_type: str,
            properties: dict[str, Any] | None = None,
        ) -> Result[bool]: ...

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
            relationship_type=relationship_type.value,
            properties=properties,
        )

    async def get_relationships(
        self, uid: str, direction: Direction = "both"
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get relationships for an entity.

        Protocol: SupportsRelationships

        Args:
            uid: Entity UID to get relationships for
            direction: "outgoing", "incoming", or "both" (default)

        Returns:
            Result[list[dict]]: List of relationship data with:
                - type: Relationship type
                - target_uid: Connected entity UID
                - direction: "outgoing" or "incoming"
                - properties: Relationship properties
        """
        try:
            # Build direction-specific query
            if direction == "outgoing":
                cypher = """
                MATCH (n {uid: $uid})-[r]->(target)
                RETURN type(r) as type, target.uid as target_uid,
                       'outgoing' as direction, properties(r) as properties
                """
            elif direction == "incoming":
                cypher = """
                MATCH (n {uid: $uid})<-[r]-(source)
                RETURN type(r) as type, source.uid as target_uid,
                       'incoming' as direction, properties(r) as properties
                """
            else:  # both
                cypher = """
                MATCH (n {uid: $uid})-[r]-(other)
                WITH r, other,
                     CASE WHEN startNode(r).uid = $uid THEN 'outgoing' ELSE 'incoming' END as dir
                RETURN type(r) as type, other.uid as target_uid,
                       dir as direction, properties(r) as properties
                """

            async with self.driver.session() as session:
                result = await session.run(cypher, {"uid": uid})
                records = await result.data()

            return Result.ok(records)

        except Exception as e:
            self.logger.error(f"Failed to get relationships for {uid}: {e}")
            return Result.fail(Errors.database(operation="get_relationships", message=str(e)))

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
        try:
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

        except Exception as e:
            self.logger.error(f"Failed to traverse from {start_uid}: {e}")
            return Result.fail(Errors.database(operation="traverse", message=str(e)))

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
        try:
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

            async with self.driver.session() as session:
                result = await session.run(cypher, {"from_uid": from_uid, "to_uid": to_uid})
                records = await result.data()

            if not records:
                return Result.ok(None)

            return Result.ok(records)

        except Exception as e:
            # Neo4j returns error if no path exists in some versions
            if "no path" in str(e).lower():
                return Result.ok(None)

            self.logger.error(f"Failed to find path from {from_uid} to {to_uid}: {e}")
            return Result.fail(Errors.database(operation="find_path", message=str(e)))
