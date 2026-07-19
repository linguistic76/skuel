"""
Relationship Ordered Mixin
==========================

Ordered and hierarchical relationship query methods plus lateral-getter
convenience wrappers. Split out of `_relationship_query_mixin.py` to keep
both files under the readability threshold.

Provides:
    get_ordered_related_uids: Ordered UID fetch via edge property
    get_related_with_metadata: Related entities plus edge metadata
    reorder_relationships: Bulk sequence-property update
    create_relationship_with_properties: MERGE with edge properties
    get_hierarchical_children_single: 1-level hierarchical traversal
    get_hierarchical_children_two_level: 2-level hierarchical traversal
    get_hierarchical_children_deep: 3+ level dynamic traversal
    get_prerequisites, get_enables, get_related, get_children, get_parent,
    get_depends_on, get_blocks: Lateral-getter convenience wrappers

Requires on concrete class (via MRO from `_RelationshipQueryMixin`):
    driver, get_related_entities
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.utils.error_boundary import safe_backend_operation
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins

    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel


class _RelationshipOrderedMixin[T: DomainModelProtocol]:
    """
    Ordered/hierarchical relationship queries and lateral-getter wrappers.

    Requires on concrete class:
        driver: AsyncDriver
        get_related_entities: provided by _RelationshipQueryMixin via MRO
    """

    if TYPE_CHECKING:
        driver: AsyncDriver

        async def get_related_entities(
            self,
            uid: str,
            relationship_type: RelationshipName,
            direction: str = "outgoing",
            limit: int | None = None,
        ) -> Result[builtins.list[T]]: ...

    # ============================================================================
    # ORDERED RELATIONSHIP QUERIES
    # ============================================================================
    # Used by UnifiedRelationshipService's OrderedRelationshipsMixin.
    # Config-driven: entity_label, relationship type, direction, ordering
    # come from DomainRelationshipConfig specs.

    @safe_backend_operation("get_ordered_related_uids")
    async def get_ordered_related_uids(
        self,
        entity_label: NeoLabel,
        entity_uid: str,
        relationship_type: str,
        direction: str,
        order_by_property: str | None = None,
        order_direction: str = "ASC",
    ) -> Result[builtins.list[str]]:
        """
        Get related entity UIDs ordered by an edge property.

        Args:
            entity_label: Label of the source entity node
            entity_uid: UID of the source entity
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"
            order_by_property: Edge property to order by (None = unordered)
            order_direction: "ASC" or "DESC"

        Returns:
            Result[list[str]] of related UIDs in order
        """
        direction_clause = (
            "-[r]->"
            if direction == "outgoing"
            else "<-[r]-"
            if direction == "incoming"
            else "-[r]-"
        )

        order_clause = ""
        if order_by_property:
            order_clause = f"ORDER BY r.{order_by_property} {order_direction}"

        query = f"""
        MATCH (e:{entity_label} {{uid: $entity_uid}}){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN related.uid AS uid
        {order_clause}
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {"entity_uid": entity_uid, "relationship_type": relationship_type},
            )
            records = [dict(record) async for record in result]

        return Result.ok([str(r["uid"]) for r in records if r.get("uid")])

    @safe_backend_operation("get_related_with_metadata")
    async def get_related_with_metadata(
        self,
        entity_label: NeoLabel,
        entity_uid: str,
        relationship_type: str,
        direction: str,
        edge_properties: builtins.list[str] | None = None,
        order_by_property: str | None = None,
        order_direction: str = "ASC",
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get related entities WITH edge property metadata.

        Args:
            entity_label: Label of the source entity node
            entity_uid: UID of the source entity
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"
            edge_properties: Specific edge properties to return (None = all)
            order_by_property: Edge property to order by (None = unordered)
            order_direction: "ASC" or "DESC"

        Returns:
            Result[list[dict]] with structure:
            [{"uid": "ps:1", "title": "...", "edge": {"sequence": 0, ...}}, ...]
        """
        direction_clause = (
            "-[r]->"
            if direction == "outgoing"
            else "<-[r]-"
            if direction == "incoming"
            else "-[r]-"
        )

        if edge_properties:
            edge_props_clause = ", ".join(f"{p}: r.{p}" for p in edge_properties)
            edge_return = f"{{{edge_props_clause}}}"
        else:
            edge_return = "properties(r)"

        order_clause = ""
        if order_by_property:
            order_clause = f"ORDER BY r.{order_by_property} {order_direction}"

        query = f"""
        MATCH (e:{entity_label} {{uid: $entity_uid}}){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN related.uid AS uid,
               related.title AS title,
               {edge_return} AS edge
        {order_clause}
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {"entity_uid": entity_uid, "relationship_type": relationship_type},
            )
            records = [dict(record) async for record in result]

        return Result.ok(
            [
                {
                    "uid": str(r["uid"]),
                    "title": r.get("title"),
                    "edge": dict(r.get("edge", {})) if r.get("edge") else {},
                }
                for r in records
                if r.get("uid")
            ]
        )

    @safe_backend_operation("reorder_relationships")
    async def reorder_relationships(
        self,
        entity_label: NeoLabel,
        entity_uid: str,
        relationship_type: str,
        direction: str,
        target_uid_sequence: builtins.list[str],
        sequence_property: str = "sequence",
    ) -> Result[int]:
        """
        Reorder relationships by updating edge sequence properties.

        Args:
            entity_label: Label of the source entity node
            entity_uid: Source entity UID
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"
            target_uid_sequence: List of target UIDs in desired order
            sequence_property: Edge property name for sequence (default: "sequence")

        Returns:
            Result[int] with count of relationships updated
        """
        if not target_uid_sequence:
            return Result.ok(0)

        direction_clause = (
            "-[r]->"
            if direction == "outgoing"
            else "<-[r]-"
            if direction == "incoming"
            else "-[r]-"
        )

        ordering_data = [{"uid": uid, "seq": idx} for idx, uid in enumerate(target_uid_sequence)]

        query = f"""
        UNWIND $ordering AS item
        MATCH (e:{entity_label} {{uid: $entity_uid}}){direction_clause}(target {{uid: item.uid}})
        WHERE type(r) = $relationship_type
        SET r.{sequence_property} = item.seq
        RETURN count(*) AS updated_count
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "entity_uid": entity_uid,
                    "ordering": ordering_data,
                    "relationship_type": relationship_type,
                },
            )
            records = [dict(record) async for record in result]

        updated = sum(r.get("updated_count", 0) for r in records)
        return Result.ok(updated)

    @safe_backend_operation("create_relationship_with_properties")
    async def create_relationship_with_properties(
        self,
        entity_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        direction: str,
        edge_properties: dict[str, Any],
    ) -> Result[bool]:
        """
        Create a relationship with specific edge properties.

        Args:
            entity_uid: Source entity UID
            target_uid: Target entity UID
            relationship_type: Neo4j relationship type (RelationshipName enum)
            direction: "outgoing", "incoming", or "both"
            edge_properties: Properties to set on the relationship edge

        Returns:
            Result[bool] indicating success
        """
        if direction == "outgoing":
            merge_clause = f"MERGE (from)-[r:{relationship_type}]->(to)"
        elif direction == "incoming":
            merge_clause = f"MERGE (from)<-[r:{relationship_type}]-(to)"
        else:
            merge_clause = f"MERGE (from)-[r:{relationship_type}]-(to)"

        # NOT :Content — same G13 shadow-uid guard as create_relationship: an
        # unguarded MERGE would create the edge to BOTH the entity and its
        # chunk-store shadow (the doubled-edge bug class).
        query = f"""
        MATCH (from {{uid: $from_uid}}) WHERE NOT from:Content
        MATCH (to {{uid: $to_uid}}) WHERE NOT to:Content
        {merge_clause}
        SET r += $properties
        RETURN r IS NOT NULL AS success
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "from_uid": entity_uid,
                    "to_uid": target_uid,
                    "properties": edge_properties,
                },
            )
            record = await result.single()

        success = record["success"] if record else False
        return Result.ok(success)

    @safe_backend_operation("get_hierarchical_children_single")
    async def get_hierarchical_children_single(
        self,
        entity_label: NeoLabel,
        entity_uid: str,
        relationship_type: str,
        direction: str,
        target_label: NeoLabel,
        order_by_property: str | None = None,
        order_direction: str = "ASC",
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Single-level hierarchical traversal returning children with edge metadata.

        Args:
            entity_label: Label of the source entity node
            entity_uid: Root entity UID
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"
            target_label: Label of the target nodes
            order_by_property: Edge property to order by (None = unordered)
            order_direction: "ASC" or "DESC"

        Returns:
            Result[list[dict]] with structure:
            [{"uid": "...", "title": "...", "edge": {...}, "children": []}, ...]
        """
        direction_clause = (
            "-[r]->"
            if direction == "outgoing"
            else "<-[r]-"
            if direction == "incoming"
            else "-[r]-"
        )

        order_clause = ""
        if order_by_property:
            order_clause = f"ORDER BY r.{order_by_property} {order_direction}"

        query = f"""
        MATCH (root:{entity_label} {{uid: $entity_uid}}){direction_clause}(child:{target_label})
        WHERE type(r) = $rel_type
        RETURN child.uid AS uid,
               child.title AS title,
               properties(r) AS edge
        {order_clause}
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, {"entity_uid": entity_uid, "rel_type": relationship_type}
            )
            records = [dict(record) async for record in result]

        return Result.ok(
            [
                {
                    "uid": str(r["uid"]),
                    "title": r.get("title"),
                    "edge": dict(r.get("edge", {})) if r.get("edge") else {},
                    "children": [],
                }
                for r in records
                if r.get("uid")
            ]
        )

    @safe_backend_operation("get_hierarchical_children_two_level")
    async def get_hierarchical_children_two_level(
        self,
        entity_label: NeoLabel,
        entity_uid: str,
        rel_type1: str,
        dir1: str,
        target_label1: NeoLabel,
        rel_type2: str,
        dir2: str,
        target_label2: NeoLabel,
        order_by_property1: str | None = None,
        order_direction1: str = "ASC",
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Two-level hierarchical traversal (e.g., LP -> PS -> KU).

        Args:
            entity_label: Label of the root entity node
            entity_uid: Root entity UID
            rel_type1: First relationship type
            dir1: First direction ("outgoing", "incoming", "both")
            target_label1: Label of first-level targets
            rel_type2: Second relationship type
            dir2: Second direction
            target_label2: Label of second-level targets
            order_by_property1: Edge property to order first level
            order_direction1: Order direction for first level

        Returns:
            Result[list[dict]] with nested children structure
        """
        dir1_clause = "-[r1]->" if dir1 == "outgoing" else "<-[r1]-"
        dir2_clause = "-[r2]->" if dir2 == "outgoing" else "<-[r2]-"

        order1 = f"r1.{order_by_property1}" if order_by_property1 else "n1.uid"

        query = f"""
        MATCH (root:{entity_label} {{uid: $entity_uid}}){dir1_clause}(n1:{target_label1})
        WHERE type(r1) = $rel_type1
        OPTIONAL MATCH (n1){dir2_clause}(n2:{target_label2})
        WHERE type(r2) = $rel_type2
        WITH n1, r1, collect({{uid: n2.uid, title: n2.title, edge: properties(r2)}}) AS children
        RETURN n1.uid AS uid,
               n1.title AS title,
               properties(r1) AS edge,
               children
        ORDER BY {order1} {order_direction1}
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "entity_uid": entity_uid,
                    "rel_type1": rel_type1,
                    "rel_type2": rel_type2,
                },
            )
            records = [dict(record) async for record in result]

        return Result.ok(
            [
                {
                    "uid": str(r["uid"]),
                    "title": r.get("title"),
                    "edge": dict(r.get("edge", {})) if r.get("edge") else {},
                    "children": [
                        {
                            "uid": str(c["uid"]) if c.get("uid") else None,
                            "title": c.get("title"),
                            "edge": dict(c.get("edge", {})) if c.get("edge") else {},
                        }
                        for c in (r.get("children") or [])
                        if c.get("uid")
                    ],
                }
                for r in records
                if r.get("uid")
            ]
        )

    @safe_backend_operation("get_hierarchical_children_deep")
    async def get_hierarchical_children_deep(
        self,
        entity_label: NeoLabel,  # noqa: ARG002 — kept for API consistency with sibling methods
        entity_uid: str,
        match_pattern: str,
        rel_type_params: dict[str, str],
        return_parts: builtins.list[str],
        order_expression: str | None = None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Multi-level (3+) hierarchical traversal with dynamic query construction.

        Args:
            entity_label: Label of the root entity node (unused — embedded in match_pattern)
            entity_uid: Root entity UID
            match_pattern: Pre-built MATCH pattern string
            rel_type_params: Parameter dict mapping rel_type0/1/... to relationship type strings
            return_parts: List of RETURN clause expressions
            order_expression: Optional ORDER BY expression

        Returns:
            Result[list[dict]] with flat results keyed by uid0, title0, edge0
        """
        where_clauses = " AND ".join(
            f"type(r{idx}) = $rel_type{idx}" for idx in range(len(rel_type_params))
        )
        order_clause = f"ORDER BY {order_expression}" if order_expression else ""

        query = f"""
        MATCH {match_pattern}
        WHERE {where_clauses}
        WITH *, {return_parts[0]} AS uid0
        RETURN {", ".join(return_parts)}
        {order_clause}
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"entity_uid": entity_uid, **rel_type_params})
            records = [dict(record) async for record in result]

        return Result.ok(
            [
                {
                    "uid": str(r.get("uid0", "")),
                    "title": r.get("title0"),
                    "edge": dict(r.get("edge0", {})) if r.get("edge0") else {},
                    "children": [],
                }
                for r in records
                if r.get("uid0")
            ]
        )

    # Convenience methods for common relationship patterns

    async def get_depends_on(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all entities this depends on.

        Convenience method for tasks/events/habits.
        """
        return await self.get_related_entities(
            uid, RelationshipName.DEPENDS_ON, direction="outgoing"
        )

    async def get_blocks(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all entities this blocks.

        Convenience method for tasks/events/habits.
        """
        return await self.get_related_entities(uid, RelationshipName.BLOCKS, direction="outgoing")
