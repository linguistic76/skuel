"""
Ordered Relationships Mixin
============================

Curriculum-domain-specific operations for ordered relationships and edge metadata.

Supports patterns like LP → PS → KU hierarchy with sequence properties on edges.

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

from core.models.type_hints import EntityUID
from core.ports.base_protocols import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.enums.neo_labels import NeoLabel
    from core.models.relationship_registry import DomainRelationshipConfig


class OrderedRelationshipsMixin[Ops: BackendOperations]:
    """
    Mixin providing ordered relationship and edge metadata methods.

    Methods support curriculum domain patterns:
    - Ordered relationships (HAS_STEP with sequence property)
    - Edge metadata retrieval (return entity + edge properties)
    - Hierarchical traversal (LP → PS → KU)

    Requires on concrete class:
        config: DomainRelationshipConfig
        backend: Protocol-based backend
        logger: Logger instance
    """

    # Provided by UnifiedRelationshipService.__init__ — declared for mypy
    config: DomainRelationshipConfig
    backend: Ops
    logger: Any

    @with_error_handling("get_ordered_related_uids", error_type="database", uid_param="entity_uid")
    async def get_ordered_related_uids(
        self,
        relationship_key: str,
        entity_uid: EntityUID,
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
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        return await self.backend.get_ordered_related_uids(
            entity_label=self.config.entity_label,
            entity_uid=entity_uid,
            relationship_type=spec.relationship.value,
            direction=spec.direction,
            order_by_property=spec.order_by_property,
            order_direction=spec.order_direction,
        )

    @with_error_handling("get_related_with_metadata", error_type="database", uid_param="entity_uid")
    async def get_related_with_metadata(
        self,
        relationship_key: str,
        entity_uid: EntityUID,
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
            [{"uid": "ps:1", "title": "...", "edge": {"sequence": 0, ...}}, ...]
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        props_to_return = edge_properties or list(spec.include_edge_properties)

        return await self.backend.get_related_with_metadata(
            entity_label=self.config.entity_label,
            entity_uid=entity_uid,
            relationship_type=spec.relationship.value,
            direction=spec.direction,
            edge_properties=props_to_return if props_to_return else None,
            order_by_property=spec.order_by_property,
            order_direction=spec.order_direction,
        )

    @with_error_handling("reorder_relationships", error_type="database", uid_param="entity_uid")
    async def reorder_relationships(
        self,
        relationship_key: str,
        entity_uid: EntityUID,
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

        result = await self.backend.reorder_relationships(
            entity_label=self.config.entity_label,
            entity_uid=entity_uid,
            relationship_type=spec.relationship.value,
            direction=spec.direction,
            target_uid_sequence=target_uid_sequence,
            sequence_property=sequence_property,
        )

        if result.is_error:
            return Result.fail(result)

        self.logger.info(
            f"Reordered {result.value} {relationship_key} relationships for {entity_uid}"
        )
        return result

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
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        result = await self.backend.create_relationship_with_properties(
            entity_uid=from_uid,
            target_uid=to_uid,
            relationship_type=spec.relationship,
            direction=spec.direction,
            edge_properties=edge_properties,
        )

        if result.is_error:
            return Result.fail(result)

        if result.value:
            self.logger.info(
                f"Created {spec.relationship.value} relationship: {from_uid} → {to_uid} "
                f"with properties: {edge_properties}"
            )

        return result

    @with_error_handling("get_hierarchical_children", error_type="database", uid_param="entity_uid")
    async def get_hierarchical_children(
        self,
        entity_uid: EntityUID,
        relationship_chain: list[tuple[str, NeoLabel]],
        max_depth: int = 3,
    ) -> Result[list[dict[str, Any]]]:
        """
        Multi-hop hierarchical traversal for curriculum patterns.

        Traverses relationship chain and returns nested structure with edge metadata.
        Supports patterns like LP → PS → KU.

        Args:
            entity_uid: Root entity UID
            relationship_chain: List of (relationship_key, target_label) tuples
                Example: [("steps", NeoLabel.PATH_STEP), ("knowledge", NeoLabel.ENTITY)]
            max_depth: Maximum traversal depth (default: 3)

        Returns:
            Result[list[dict]] with hierarchical structure including edge metadata
        """
        if not relationship_chain:
            return Result.ok([])

        if len(relationship_chain) > max_depth:
            return Result.fail(
                Errors.validation(f"Relationship chain exceeds max_depth of {max_depth}")
            )

        if len(relationship_chain) == 1:
            rel_key, target_label = relationship_chain[0]
            spec = self.config.get_relationship_by_method(rel_key)
            if not spec:
                return Result.fail(Errors.validation(f"Unknown relationship key '{rel_key}'"))

            return await self.backend.get_hierarchical_children_single(
                entity_label=self.config.entity_label,
                entity_uid=entity_uid,
                relationship_type=spec.relationship.value,
                direction=spec.direction,
                target_label=target_label,
                order_by_property=spec.order_by_property,
                order_direction=spec.order_direction,
            )

        elif len(relationship_chain) == 2:
            rel_key1, target_label1 = relationship_chain[0]
            rel_key2, target_label2 = relationship_chain[1]

            spec1 = self.config.get_relationship_by_method(rel_key1)
            spec2 = self.config.get_relationship_by_method(rel_key2)

            if not spec1 or not spec2:
                return Result.fail(Errors.validation("Unknown relationship key in chain"))

            return await self.backend.get_hierarchical_children_two_level(
                entity_label=self.config.entity_label,
                entity_uid=entity_uid,
                rel_type1=spec1.relationship.value,
                dir1=spec1.direction,
                target_label1=target_label1,
                rel_type2=spec2.relationship.value,
                dir2=spec2.direction,
                target_label2=target_label2,
                order_by_property1=spec1.order_by_property,
                order_direction1=spec1.order_direction,
            )

        else:
            # For 3+ levels, build dynamic query parts and delegate
            match_parts = [f"(root:{self.config.entity_label} {{uid: $entity_uid}})"]
            return_parts: list[str] = []
            order_expressions: list[str] = []

            rel_type_params: dict[str, str] = {}
            for idx, (rel_key, target_label) in enumerate(relationship_chain):
                spec = self.config.get_relationship_by_method(rel_key)
                if not spec:
                    return Result.fail(Errors.validation(f"Unknown relationship key '{rel_key}'"))

                direction = "-[r{idx}]->" if spec.direction == "outgoing" else "<-[r{idx}]-"
                direction = direction.format(idx=idx)
                node_alias = f"n{idx}"

                match_parts.append(f"{direction}({node_alias}:{target_label})")

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

                rel_type_params[f"rel_type{idx}"] = spec.relationship.value

            match_pattern = "".join(match_parts)

            return await self.backend.get_hierarchical_children_deep(
                entity_label=self.config.entity_label,
                entity_uid=entity_uid,
                match_pattern=match_pattern,
                rel_type_params=rel_type_params,
                return_parts=return_parts,
                order_expression=order_expressions[0] if order_expressions else None,
            )
