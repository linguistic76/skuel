"""
Ordered Relationships Mixin
============================

Curriculum-domain-specific operations for ordered relationships and edge metadata.

Supports patterns like LP → LS → KU hierarchy with sequence properties on edges.

Provides:
    get_ordered_related_uids: Get related UIDs ordered by edge property
    get_related_with_metadata: Get related entities with edge property metadata
    reorder_relationships: Update edge sequence properties to new order
    create_relationship_with_properties: Create relationship with edge properties
    get_hierarchical_children: Multi-hop traversal for curriculum patterns

Requires on concrete class:
    config, backend, logger (set by UnifiedRelationshipService.__init__)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.relationship_registry import DomainRelationshipConfig


class OrderedRelationshipsMixin:
    """
    Mixin providing ordered relationship and edge metadata methods.

    Methods support curriculum domain patterns:
    - Ordered relationships (HAS_STEP with sequence property)
    - Edge metadata retrieval (return entity + edge properties)
    - Hierarchical traversal (LP → LS → KU)

    Requires on concrete class:
        config: DomainRelationshipConfig
        backend: Protocol-based backend
        logger: Logger instance
    """

    # Provided by UnifiedRelationshipService.__init__ — declared for mypy
    config: DomainRelationshipConfig
    backend: Any
    logger: Any

    @with_error_handling("get_ordered_related_uids", error_type="database", uid_param="entity_uid")
    async def get_ordered_related_uids(
        self,
        relationship_key: str,
        entity_uid: str,
    ) -> Result[list[str]]:
        """
        Get related entity UIDs in order defined by edge property.

        Uses order_by_property from RelationshipSpec if configured.
        Falls back to unordered query if no ordering configured.

        Args:
            relationship_key: Key from config (e.g., "steps")
            entity_uid: Entity UID

        Returns:
            Result[list[str]] of related UIDs in order

        Example:
            # Get LP steps in sequence order
            result = await lp_rel.get_ordered_related_uids("steps", "lp:python-basics")
            # Returns: ["ls:intro", "ls:syntax", "ls:functions", ...]
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        # Build ORDER BY clause if configured
        order_clause = ""
        if spec.order_by_property:
            order_clause = f"ORDER BY r.{spec.order_by_property} {spec.order_direction}"

        query = f"""
        MATCH (e:{self.config.entity_label} {{uid: $entity_uid}}){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN related.uid AS uid
        {order_clause}
        """

        params = {
            "entity_uid": entity_uid,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok([str(record["uid"]) for record in result.value if record.get("uid")])

    @with_error_handling("get_related_with_metadata", error_type="database", uid_param="entity_uid")
    async def get_related_with_metadata(
        self,
        relationship_key: str,
        entity_uid: str,
        edge_properties: list[str] | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get related entities WITH edge property metadata.

        Returns list of dicts containing entity data and edge properties.
        Uses include_edge_properties from RelationshipSpec if edge_properties not provided.
        Uses order_by_property from RelationshipSpec if configured.

        Args:
            relationship_key: Key from config (e.g., "steps")
            entity_uid: Entity UID
            edge_properties: Optional override of edge properties to return

        Returns:
            Result[list[dict]] with structure:
            [{"uid": "ls:1", "title": "...", "edge": {"sequence": 0, ...}}, ...]

        Example:
            # Get LP steps with sequence numbers
            result = await lp_rel.get_related_with_metadata("steps", "lp:python-basics")
            # Returns: [
            #     {"uid": "ls:intro", "title": "Introduction", "edge": {"sequence": 0}},
            #     {"uid": "ls:syntax", "title": "Basic Syntax", "edge": {"sequence": 1}},
            # ]
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        # Determine which edge properties to return
        props_to_return = edge_properties or list(spec.include_edge_properties)

        # Build edge properties return clause
        if props_to_return:
            edge_props_clause = ", ".join(f"{p}: r.{p}" for p in props_to_return)
            edge_return = f"{{{edge_props_clause}}}"
        else:
            edge_return = "properties(r)"

        # Build ORDER BY clause if configured
        order_clause = ""
        if spec.order_by_property:
            order_clause = f"ORDER BY r.{spec.order_by_property} {spec.order_direction}"

        query = f"""
        MATCH (e:{self.config.entity_label} {{uid: $entity_uid}}){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN related.uid AS uid,
               related.title AS title,
               {edge_return} AS edge
        {order_clause}
        """

        params = {
            "entity_uid": entity_uid,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            [
                {
                    "uid": str(record["uid"]),
                    "title": record.get("title"),
                    "edge": dict(record.get("edge", {})) if record.get("edge") else {},
                }
                for record in result.value
                if record.get("uid")
            ]
        )

    @with_error_handling("reorder_relationships", error_type="database", uid_param="entity_uid")
    async def reorder_relationships(
        self,
        relationship_key: str,
        entity_uid: str,
        target_uid_sequence: list[str],
        sequence_property: str = "sequence",
    ) -> Result[int]:
        """
        Reorder relationships by updating edge sequence properties.

        Updates the sequence property on each relationship edge to match
        the order of target_uid_sequence (0-indexed).

        Args:
            relationship_key: Key from config (e.g., "steps")
            entity_uid: Source entity UID
            target_uid_sequence: List of target UIDs in desired order
            sequence_property: Edge property name for sequence (default: "sequence")

        Returns:
            Result[int] with count of relationships updated

        Example:
            # Reorder LP steps
            await lp_rel.reorder_relationships(
                "steps",
                "lp:python-basics",
                ["ls:syntax", "ls:intro", "ls:functions"],  # New order
            )
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        if not target_uid_sequence:
            return Result.ok(0)

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        # Build ordering data: [(uid, sequence), ...]
        ordering_data = [{"uid": uid, "seq": idx} for idx, uid in enumerate(target_uid_sequence)]

        query = f"""
        UNWIND $ordering AS item
        MATCH (e:{self.config.entity_label} {{uid: $entity_uid}}){direction_clause}(target {{uid: item.uid}})
        WHERE type(r) = $relationship_type
        SET r.{sequence_property} = item.seq
        RETURN count(*) AS updated_count
        """

        params = {
            "entity_uid": entity_uid,
            "ordering": ordering_data,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        updated = sum(record.get("updated_count", 0) for record in result.value)

        self.logger.info(f"Reordered {updated} {relationship_key} relationships for {entity_uid}")

        return Result.ok(updated)

    @with_error_handling(
        "create_relationship_with_properties", error_type="database", uid_param="from_uid"
    )
    async def create_relationship_with_properties(
        self,
        relationship_key: str,
        from_uid: str,
        to_uid: str,
        edge_properties: dict[str, Any],
    ) -> Result[bool]:
        """
        Create a relationship with specific edge properties.

        Useful for curriculum relationships that need metadata like sequence numbers.

        Args:
            relationship_key: Key from config (e.g., "steps")
            from_uid: Source entity UID
            to_uid: Target entity UID
            edge_properties: Properties to set on the relationship edge

        Returns:
            Result[bool] indicating success

        Example:
            # Attach step to path with sequence
            await lp_rel.create_relationship_with_properties(
                "steps",
                "lp:python-basics",
                "ls:new-step",
                {"sequence": 5, "completed": False},
            )
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        query = f"""
        MATCH (from {{uid: $from_uid}})
        MATCH (to {{uid: $to_uid}})
        MERGE (from){direction_clause.replace("[r]", f"[r:{spec.relationship.value}]")}(to)
        SET r += $properties
        RETURN r IS NOT NULL AS success
        """

        params = {
            "from_uid": from_uid,
            "to_uid": to_uid,
            "properties": edge_properties,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        success = records[0].get("success", False) if records else False

        if success:
            self.logger.info(
                f"Created {spec.relationship.value} relationship: {from_uid} → {to_uid} "
                f"with properties: {edge_properties}"
            )

        return Result.ok(success)

    @with_error_handling("get_hierarchical_children", error_type="database", uid_param="entity_uid")
    async def get_hierarchical_children(
        self,
        entity_uid: str,
        relationship_chain: list[tuple[str, str]],
        max_depth: int = 3,
    ) -> Result[list[dict[str, Any]]]:
        """
        Multi-hop hierarchical traversal for curriculum patterns.

        Traverses relationship chain and returns nested structure with edge metadata.
        Supports patterns like LP → LS → KU.

        Args:
            entity_uid: Root entity UID
            relationship_chain: List of (relationship_key, target_label) tuples
                Example: [("steps", "Ls"), ("knowledge", "Entity")]
            max_depth: Maximum traversal depth (default: 3)

        Returns:
            Result[list[dict]] with hierarchical structure including edge metadata

        Example:
            # Get LP with steps and their knowledge units
            result = await lp_rel.get_hierarchical_children(
                "lp:python-basics",
                [("steps", "Ls"), ("knowledge", "Entity")],
            )
            # Returns: [
            #     {
            #         "uid": "ls:intro",
            #         "title": "Introduction",
            #         "edge": {"sequence": 0},
            #         "children": [
            #             {"uid": "ku:python-overview", "title": "Python Overview"},
            #         ]
            #     },
            # ]
        """
        if not relationship_chain:
            return Result.ok([])

        if len(relationship_chain) > max_depth:
            return Result.fail(
                Errors.validation(f"Relationship chain exceeds max_depth of {max_depth}")
            )

        # Build the MATCH pattern dynamically
        match_parts = [f"(root:{self.config.entity_label} {{uid: $entity_uid}})"]
        return_parts = []
        order_expressions = []  # Store ordering for each level

        for idx, (rel_key, target_label) in enumerate(relationship_chain):
            spec = self.config.get_relationship_by_method(rel_key)
            if not spec:
                return Result.fail(Errors.validation(f"Unknown relationship key '{rel_key}'"))

            direction = "-[r{idx}]->" if spec.direction == "outgoing" else "<-[r{idx}]-"
            direction = direction.format(idx=idx)
            node_alias = f"n{idx}"

            match_parts.append(f"{direction}({node_alias}:{target_label})")

            # Add ordering expression for this level
            order_expr = (
                f"r{idx}.{spec.order_by_property}"
                if spec.order_by_property
                else f"{node_alias}.uid"
            )
            order_expressions.append(order_expr)

            return_parts.append(f"{node_alias}.uid AS uid{idx}")
            return_parts.append(f"{node_alias}.title AS title{idx}")

            if spec.include_edge_properties:
                edge_props = ", ".join(f"{p}: r{idx}.{p}" for p in spec.include_edge_properties)
                return_parts.append(f"{{{edge_props}}} AS edge{idx}")
            else:
                return_parts.append(f"properties(r{idx}) AS edge{idx}")

        # For simplicity, handle 1-2 levels explicitly
        # More complex hierarchies would need recursive CTEs
        if len(relationship_chain) == 1:
            rel_key, target_label = relationship_chain[0]
            spec = self.config.get_relationship_by_method(rel_key)
            if not spec:
                return Result.fail(Errors.validation(f"Unknown relationship key '{rel_key}'"))

            direction_clause = (
                "-[r]->"
                if spec.direction == "outgoing"
                else "<-[r]-"
                if spec.direction == "incoming"
                else "-[r]-"
            )

            order_clause = ""
            if spec.order_by_property:
                order_clause = f"ORDER BY r.{spec.order_by_property} {spec.order_direction}"

            query = f"""
            MATCH (root:{self.config.entity_label} {{uid: $entity_uid}}){direction_clause}(child:{target_label})
            WHERE type(r) = $rel_type
            RETURN child.uid AS uid,
                   child.title AS title,
                   properties(r) AS edge
            {order_clause}
            """

            params = {"entity_uid": entity_uid, "rel_type": spec.relationship.value}
            result = await self.backend.execute_query(query, params)

            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(
                [
                    {
                        "uid": str(record["uid"]),
                        "title": record.get("title"),
                        "edge": dict(record.get("edge", {})) if record.get("edge") else {},
                        "children": [],
                    }
                    for record in result.value
                    if record.get("uid")
                ]
            )

        elif len(relationship_chain) == 2:
            # Two-level hierarchy: LP → LS → KU
            rel_key1, target_label1 = relationship_chain[0]
            rel_key2, target_label2 = relationship_chain[1]

            spec1 = self.config.get_relationship_by_method(rel_key1)
            spec2 = self.config.get_relationship_by_method(rel_key2)

            if not spec1 or not spec2:
                return Result.fail(Errors.validation("Unknown relationship key in chain"))

            dir1 = "-[r1]->" if spec1.direction == "outgoing" else "<-[r1]-"
            dir2 = "-[r2]->" if spec2.direction == "outgoing" else "<-[r2]-"

            order1 = f"r1.{spec1.order_by_property}" if spec1.order_by_property else "n1.uid"

            query = f"""
            MATCH (root:{self.config.entity_label} {{uid: $entity_uid}}){dir1}(n1:{target_label1})
            WHERE type(r1) = $rel_type1
            OPTIONAL MATCH (n1){dir2}(n2:{target_label2})
            WHERE type(r2) = $rel_type2
            WITH n1, r1, collect({{uid: n2.uid, title: n2.title, edge: properties(r2)}}) AS children
            RETURN n1.uid AS uid,
                   n1.title AS title,
                   properties(r1) AS edge,
                   children
            ORDER BY {order1} {spec1.order_direction}
            """

            params = {
                "entity_uid": entity_uid,
                "rel_type1": spec1.relationship.value,
                "rel_type2": spec2.relationship.value,
            }

            result = await self.backend.execute_query(query, params)

            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(
                [
                    {
                        "uid": str(record["uid"]),
                        "title": record.get("title"),
                        "edge": dict(record.get("edge", {})) if record.get("edge") else {},
                        "children": [
                            {
                                "uid": str(c["uid"]) if c.get("uid") else None,
                                "title": c.get("title"),
                                "edge": dict(c.get("edge", {})) if c.get("edge") else {},
                            }
                            for c in (record.get("children") or [])
                            if c.get("uid")
                        ],
                    }
                    for record in result.value
                    if record.get("uid")
                ]
            )

        else:
            # For 3+ levels, use the dynamically built query parts
            # Build the full MATCH pattern
            full_match = "".join(match_parts)

            # Build relationship type parameters
            rel_types_params: dict[str, str] = {}
            for idx, (rel_key, _) in enumerate(relationship_chain):
                spec = self.config.get_relationship_by_method(rel_key)
                if spec is not None:
                    rel_types_params[f"rel_type{idx}"] = spec.relationship.value

            # Use the first order expression for top-level ordering
            order_clause = f"ORDER BY {order_expressions[0]}" if order_expressions else ""

            query = f"""
            MATCH {full_match}
            WHERE {" AND ".join(f"type(r{idx}) = $rel_type{idx}" for idx in range(len(relationship_chain)))}
            WITH *, {return_parts[0]} AS uid0
            RETURN {", ".join(return_parts)}
            {order_clause}
            """

            params = {"entity_uid": entity_uid, **rel_types_params}
            result = await self.backend.execute_query(query, params)

            if result.is_error:
                return Result.fail(result.expect_error())

            # For 3+ levels, return flat results (nested structure requires more complex handling)
            return Result.ok(
                [
                    {
                        "uid": str(record.get("uid0", "")),
                        "title": record.get("title0"),
                        "edge": dict(record.get("edge0", {})) if record.get("edge0") else {},
                        "children": [],  # Flat structure for 3+ levels
                    }
                    for record in result.value
                    if record.get("uid0")
                ]
            )
