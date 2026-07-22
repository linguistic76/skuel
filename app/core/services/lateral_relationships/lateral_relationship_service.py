"""
Lateral Relationship Service - Core Graph Operations
=====================================================

Domain-agnostic service for managing explicit lateral relationships between
entities (siblings, cousins, dependencies, etc.).

This is FUNDAMENTAL to SKUEL's graph model - provides the foundation for all
lateral relationship operations across all domains.

Architecture:
    - Protocol-based (LateralRelationshipOperations)
    - Domain-agnostic (works with any entity type)
    - Validation-first (ensures graph integrity)
    - Bidirectional support (auto-creates inverses)
    - Rich metadata (captures relationship semantics)
    - All Cypher delegated to LateralRelationshipBackend

Usage:
    # Domain services delegate to this core service
    lateral_service = LateralRelationshipService(backend)

    result = await lateral_service.create_lateral_relationship(
        source_uid="goal_a",
        target_uid="goal_b",
        relationship_type=RelationshipName.BLOCKS,
        metadata={"reason": "Must complete setup first", "severity": "required"}
    )

See: /docs/architecture/LATERAL_RELATIONSHIPS_CORE.md
"""

from typing import TYPE_CHECKING, Any

from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID

if TYPE_CHECKING:
    from core.ports.service_protocols import (
        LateralRelationshipBackendOperations,
        OwnershipVerifier,
    )
from core.models.relationship_registry import get_lateral_spec
from core.ports.query_types import (
    AlternativeComparisonItem,
    BlockingChainResult,
    LateralRelationshipItem,
    RelationshipGraphData,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class LateralRelationshipService:
    """
    Core service for managing lateral relationships in the graph.

    This service is domain-agnostic and provides the foundation for all
    lateral relationship operations. Routes pass domain_service for ownership
    verification. Relationship metadata is defined in LateralRelationshipSpec.

    Responsibilities:
    - Create/delete lateral relationships
    - Validate relationship constraints
    - Handle bidirectional relationships
    - Query lateral connections
    - Store relationship metadata
    """

    def __init__(self, backend: "LateralRelationshipBackendOperations") -> None:
        self.backend = backend

    async def create_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        metadata: dict[str, Any] | None = None,
        validate: bool = True,
        auto_inverse: bool = True,
        user_uid: UserUID | None = None,
        domain_service: "OwnershipVerifier | None" = None,
    ) -> Result[bool]:
        """
        Create explicit lateral relationship between two entities.

        Args:
            source_uid: Source entity UID
            target_uid: Target entity UID
            relationship_type: Type of lateral relationship
            metadata: Optional relationship properties (strength, reason, etc.)
            validate: Perform validation checks before creation
            auto_inverse: Auto-create inverse relationship if asymmetric
            user_uid: User creating the relationship (for ownership verification)
            domain_service: Domain service with verify_ownership() (None = shared content)

        Returns:
            Result[bool]: Success if relationship created
        """
        if source_uid == target_uid:
            return Result.fail(Errors.validation("Cannot create lateral relationship with self"))

        # Ownership verification (if domain_service provided)
        if user_uid and domain_service:
            for uid in [source_uid, target_uid]:
                ownership_result = await domain_service.verify_ownership(uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(Errors.not_found(f"Entity {uid} not found or access denied"))

        # Validation phase
        if validate:
            validation_result = await self._validate_lateral_relationship(
                source_uid, target_uid, relationship_type
            )
            if validation_result.is_error:
                return validation_result

        # Prepare metadata
        rel_metadata = metadata or {}
        rel_metadata["created_at"] = "timestamp()"
        spec = get_lateral_spec(relationship_type)
        rel_metadata["relationship_category"] = spec.category if spec else ""
        rel_metadata["is_symmetric"] = spec.is_symmetric if spec else False

        # Create the relationship
        result = await self.backend.create_relationship(
            source_uid=source_uid,
            target_uid=target_uid,
            relationship_type=relationship_type,
            metadata=rel_metadata,
        )

        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.fail(
                Errors.database(
                    operation="create_relationship",
                    message=f"Failed to create {relationship_type.value} relationship",
                )
            )

        logger.info(
            f"Created lateral relationship: {source_uid} -[{relationship_type.value}]-> {target_uid}"
        )

        # Auto-create inverse if asymmetric
        if auto_inverse and spec and not spec.is_symmetric:
            inverse_type = spec.inverse_type
            if inverse_type:
                await self._create_inverse_relationship(
                    source_uid=target_uid,  # Reversed
                    target_uid=source_uid,  # Reversed
                    relationship_type=inverse_type,
                    metadata=rel_metadata,
                )

        return Result.ok(True)

    async def delete_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        delete_inverse: bool = True,
        user_uid: UserUID | None = None,
        domain_service: "OwnershipVerifier | None" = None,
    ) -> Result[bool]:
        """
        Delete explicit lateral relationship.

        Args:
            source_uid: Source entity UID
            target_uid: Target entity UID
            relationship_type: Type of relationship to delete
            delete_inverse: Also delete inverse relationship if asymmetric
            user_uid: User deleting the relationship (for ownership verification)
            domain_service: Domain service with verify_ownership() (None = shared content)

        Returns:
            Result[bool]: Success if relationship deleted
        """
        # Ownership verification
        if user_uid and domain_service:
            for uid in [source_uid, target_uid]:
                ownership_result = await domain_service.verify_ownership(uid, user_uid)
                if ownership_result.is_error:
                    return Result.fail(Errors.not_found(f"Entity {uid} not found or access denied"))

        result = await self.backend.delete_relationship(
            source_uid=source_uid,
            target_uid=target_uid,
            relationship_type=relationship_type,
        )

        if result.is_error:
            return Result.fail(result)

        records = result.value
        deleted_count = records[0]["deleted_count"] if records else 0

        if deleted_count == 0:
            return Result.fail(
                Errors.not_found(
                    f"Relationship {relationship_type.value} not found between {source_uid} and {target_uid}"
                )
            )

        logger.info(
            f"Deleted lateral relationship: {source_uid} -[{relationship_type.value}]-> {target_uid}"
        )

        # Delete inverse if needed
        spec = get_lateral_spec(relationship_type)
        if delete_inverse and spec and not spec.is_symmetric:
            inverse_type = spec.inverse_type
            if inverse_type:
                await self._delete_inverse_relationship(
                    source_uid=target_uid,
                    target_uid=source_uid,
                    relationship_type=inverse_type,
                )

        return Result.ok(True)

    async def get_lateral_relationships(
        self,
        entity_uid: EntityUID,
        relationship_types: list[RelationshipName] | None = None,
        direction: str = "outgoing",  # "outgoing", "incoming", "both"
        include_metadata: bool = True,
        user_uid: UserUID | None = None,
        domain_service: "OwnershipVerifier | None" = None,
    ) -> Result[list[LateralRelationshipItem]]:
        """
        Get all lateral relationships for an entity.

        Args:
            entity_uid: Entity UID
            relationship_types: Filter by specific types (None = all types)
            direction: Relationship direction to query
            include_metadata: Include relationship properties in results

        Returns:
            Result with list of relationships
        """
        # Ownership verification
        if user_uid and domain_service:
            ownership_result = await domain_service.verify_ownership(entity_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Entity {entity_uid} not found or access denied")
                )

        # Build type filter
        if relationship_types:
            type_filter = "|".join([rt.value for rt in relationship_types])
        else:
            all_types = [rt.value for rt in RelationshipName if rt.is_lateral_relationship()]
            type_filter = "|".join(all_types)

        result = await self.backend.get_relationships(
            entity_uid=entity_uid,
            type_filter=type_filter,
            pattern=direction,
        )

        if result.is_error:
            return Result.fail(result)

        # Backend rows are typed LateralRelationshipRow TypedDicts.
        relationships: list[LateralRelationshipItem] = [
            {
                "type": record["relationship_type"],
                "target_uid": record["related_uid"],
                "target_title": record["related_title"],
                "metadata": record["metadata"] if include_metadata else {},
                "direction": record["direction"],
            }
            for record in result.value
        ]

        logger.info(f"Retrieved {len(relationships)} lateral relationships for {entity_uid}")
        return Result.ok(relationships)

    async def get_siblings(
        self,
        entity_uid: EntityUID,
        include_explicit_only: bool = False,
        user_uid: UserUID | None = None,
        domain_service: "OwnershipVerifier | None" = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling entities (same parent).

        Args:
            entity_uid: Entity UID
            include_explicit_only: Only return explicit SIBLING relationships
                                   (False = derive from hierarchy)
            user_uid: User requesting siblings (for ownership verification)
            domain_service: Domain service with verify_ownership() (None = shared content)

        Returns:
            Result with list of siblings
        """
        # Ownership verification
        if user_uid and domain_service:
            ownership_result = await domain_service.verify_ownership(entity_uid, user_uid)
            if ownership_result.is_error:
                return Result.fail(
                    Errors.not_found(f"Entity {entity_uid} not found or access denied")
                )

        if include_explicit_only:
            # Query explicit SIBLING relationships. get_siblings is a `# boundary`
            # method whose two branches return different shapes, so flatten the
            # typed relationship rows back to plain dicts for the union return.
            explicit = await self.get_lateral_relationships(
                entity_uid,
                relationship_types=[RelationshipName.SIBLING],
                direction="both",
            )
            if explicit.is_error:
                return Result.fail(explicit)
            explicit_siblings: list[dict[str, Any]] = [dict(item) for item in explicit.value]
            return Result.ok(explicit_siblings)
        else:
            # Derive from hierarchy (share same parent)
            result = await self.backend.get_siblings(entity_uid)

            if result.is_error:
                return Result.fail(result)

            siblings = [
                {
                    "uid": record["sibling_uid"],
                    "title": record["sibling_title"],
                    "hierarchy_type": record["hierarchy_type"],
                    "order": record["order"],
                    "relationship": "derived_sibling",
                }
                for record in result.value
            ]

            return Result.ok(siblings)

    async def get_cousins(
        self,
        entity_uid: EntityUID,
        degree: int = 1,  # 1st cousins, 2nd cousins, etc.
    ) -> Result[list[dict[str, Any]]]:
        """
        Get cousin entities (same depth, different parents, shared ancestor).

        Args:
            entity_uid: Entity UID
            degree: Cousin degree (1 = first cousins, 2 = second cousins, etc.)

        Returns:
            Result with list of cousins
        """
        if degree != 1:
            return Result.fail(
                Errors.validation("Only first cousins (degree=1) currently supported")
            )

        result = await self.backend.get_cousins(entity_uid)

        if result.is_error:
            return Result.fail(result)

        cousins = [
            {
                "uid": record["cousin_uid"],
                "title": record["cousin_title"],
                "shared_ancestor_uid": record["shared_ancestor_uid"],
                "shared_ancestor_title": record["shared_ancestor_title"],
                "degree": degree,
                "relationship": "derived_cousin",
            }
            for record in result.value
        ]

        return Result.ok(cousins)

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _validate_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
    ) -> Result[bool]:
        """
        Validate that lateral relationship can be created.

        Checks:
        - Both entities exist
        - Relationship constraints met (same parent, same depth, etc.)
        - No circular dependencies
        - No duplicate relationships
        """
        # Check entities exist
        exists_result = await self._check_entities_exist(source_uid, target_uid)
        if exists_result.is_error:
            return exists_result

        # Look up spec from registry
        spec = get_lateral_spec(relationship_type)
        if not spec:
            return Result.fail(
                Errors.validation(f"Not a lateral relationship type: {relationship_type.value}")
            )

        # Check same parent constraint
        if spec.requires_same_parent:
            same_parent_result = await self._check_same_parent(source_uid, target_uid)
            if same_parent_result.is_error:
                return same_parent_result

        # Check same depth constraint
        if spec.requires_same_depth:
            same_depth_result = await self._check_same_depth(source_uid, target_uid)
            if same_depth_result.is_error:
                return same_depth_result

        # Check for circular dependencies
        if spec.check_cycles:
            cycle_result = await self._check_no_cycles(source_uid, target_uid, relationship_type)
            if cycle_result.is_error:
                return cycle_result

        return Result.ok(True)

    async def _check_entities_exist(self, source_uid: str, target_uid: str) -> Result[bool]:
        """Verify both entities exist in the graph."""
        result = await self.backend.check_entities_exist(source_uid, target_uid)

        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records:
            return Result.fail(Errors.not_found("One or both entities not found"))

        record = records[0]
        if record["source_count"] == 0:
            return Result.fail(Errors.not_found(f"Source entity {source_uid} not found"))
        if record["target_count"] == 0:
            return Result.fail(Errors.not_found(f"Target entity {target_uid} not found"))

        return Result.ok(True)

    async def _check_same_parent(self, source_uid: str, target_uid: str) -> Result[bool]:
        """Verify entities share the same parent."""
        result = await self.backend.check_same_parent(source_uid, target_uid)

        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records or records[0]["shared_parent_count"] == 0:
            return Result.fail(
                Errors.validation("Entities must share same parent for this relationship type")
            )

        return Result.ok(True)

    async def _check_same_depth(self, source_uid: str, target_uid: str) -> Result[bool]:
        """Verify entities are at the same hierarchical depth."""
        result = await self.backend.check_same_depth(source_uid, target_uid)

        if result.is_error:
            return Result.fail(result)

        records = result.value
        if not records:
            # Entities might be roots (depth 0)
            return Result.ok(True)

        record = records[0]
        if record["source_depth"] != record["target_depth"]:
            return Result.fail(
                Errors.validation(
                    f"Entities must be at same depth for this relationship type "
                    f"(source depth: {record['source_depth']}, target depth: {record['target_depth']}))"
                )
            )

        return Result.ok(True)

    async def _check_no_cycles(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
    ) -> Result[bool]:
        """
        Check that creating this relationship won't create a circular dependency.

        For BLOCKS/PREREQUISITE_FOR: source -> target is invalid if target -> ... -> source exists.
        """
        result = await self.backend.check_no_cycles(source_uid, target_uid, relationship_type)

        if result.is_error:
            return Result.fail(result)

        records = result.value
        if records and records[0]["cycle_count"] > 0:
            return Result.fail(
                Errors.validation(
                    f"Creating this {relationship_type.value} relationship would create a circular dependency"
                )
            )

        return Result.ok(True)

    async def _create_inverse_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        metadata: dict[str, Any],
    ) -> None:
        """Create inverse relationship for asymmetric types."""
        result = await self.backend.create_inverse(
            source_uid=source_uid,
            target_uid=target_uid,
            relationship_type=relationship_type,
            metadata=metadata,
        )
        if result.is_error:
            logger.error(f"Failed to create inverse relationship: {result.error}")
        else:
            logger.info(f"Created inverse relationship: {relationship_type.value}")

    async def _delete_inverse_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
    ) -> None:
        """Delete inverse relationship for asymmetric types."""
        result = await self.backend.delete_inverse(
            source_uid=source_uid,
            target_uid=target_uid,
            relationship_type=relationship_type,
        )
        if result.is_error:
            logger.error(f"Failed to delete inverse relationship: {result.error}")
        else:
            logger.info(f"Deleted inverse relationship: {relationship_type.value}")

    # ========================================================================
    # Enhanced UX Methods
    # ========================================================================

    async def get_blocking_chain(
        self,
        entity_uid: EntityUID,
        max_depth: int = 10,
    ) -> Result[BlockingChainResult]:
        """
        Get transitive blocking chain with depth levels.

        Returns all entities that block the given entity, organized by depth
        from the root blockers to the immediate blockers.

        Args:
            entity_uid: Entity UID to get blockers for
            max_depth: Maximum depth to traverse (default 10)

        Returns:
            Result with blocking chain data including levels and critical_path.
        """
        result = await self.backend.get_blocking_chain(entity_uid)

        if result.is_error:
            return Result.fail(result)

        if not result.value:
            empty_chain: BlockingChainResult = {
                "root_uid": entity_uid,
                "total_blockers": 0,
                "chain_depth": 0,
                "levels": [],
                "critical_path": [entity_uid],
            }
            return Result.ok(empty_chain)

        # Group by depth
        levels_dict: dict[int, list[dict[str, Any]]] = {}
        all_blockers = []

        for record in result.value:
            depth_val = record["depth"]
            blocker_data = {
                "uid": record["uid"],
                "title": record["title"],
                "entity_type": record["entity_type"],
                "status": record["status"],
                "blocks_count": record["blocks_count"],
            }

            if depth_val not in levels_dict:
                levels_dict[depth_val] = []
            levels_dict[depth_val].append(blocker_data)
            all_blockers.append(record["uid"])

        # Convert to sorted list
        levels = [
            {"depth": depth, "entities": entities}
            for depth, entities in sorted(levels_dict.items(), reverse=True)
        ]

        # Build critical path (longest chain)
        max_depth_val = max(levels_dict.keys()) if levels_dict else 0
        critical_path = []
        if levels:
            # Take first entity from each depth level + the target
            for depth in sorted(levels_dict.keys(), reverse=True):
                critical_path.append(levels_dict[depth][0]["uid"])
            critical_path.append(entity_uid)

        chain_data: BlockingChainResult = {
            "root_uid": entity_uid,
            "total_blockers": len(all_blockers),
            "chain_depth": max_depth_val,
            "levels": levels,
            "critical_path": critical_path,
        }

        logger.info(
            f"Retrieved blocking chain for {entity_uid}: "
            f"{len(all_blockers)} blockers across {max_depth_val} levels"
        )
        return Result.ok(chain_data)

    async def get_alternatives_with_comparison(
        self,
        entity_uid: EntityUID,
        comparison_fields: list[str] | None = None,
    ) -> Result[list[AlternativeComparisonItem]]:
        """
        Get alternative entities with side-by-side comparison data.

        Args:
            entity_uid: Entity UID to get alternatives for
            comparison_fields: Specific fields to include in comparison
                              (None = all available fields)

        Returns:
            Result with list of alternatives with comparison data
        """
        result = await self.backend.get_alternatives_comparison(entity_uid)

        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.ok([])

        # get_alternatives_comparison is a `# boundary` method (dict[str, Any] rows).
        alternatives: list[AlternativeComparisonItem] = []
        for record in result.value:
            # Build comparison data from relationship properties
            comparison_data: dict[str, Any] = {}
            if record["timeframe"]:
                comparison_data["timeframe"] = record["timeframe"]
            if record["difficulty"]:
                comparison_data["difficulty"] = record["difficulty"]
            if record["resources"]:
                comparison_data["resources"] = record["resources"]

            # Add any custom comparison fields from relationship
            rel_props = record["rel_properties"] or {}
            for key, value in rel_props.items():
                if key not in [
                    "comparison_criteria",
                    "tradeoffs",
                    "created_at",
                    "relationship_category",
                    "is_symmetric",
                ]:
                    if comparison_fields is None or key in comparison_fields:
                        comparison_data[key] = value

            alternative_data: AlternativeComparisonItem = {
                "uid": record["uid"],
                "title": record["title"],
                "entity_type": record["entity_type"],
                "status": record["status"],
                "priority": record["priority"],
                "description": record["description"],
                "comparison_data": comparison_data,
                "metadata": {
                    "tradeoffs": record["tradeoffs"] or "",
                    "comparison_criteria": record["comparison_criteria"] or "",
                },
            }

            alternatives.append(alternative_data)

        logger.info(f"Retrieved {len(alternatives)} alternatives for {entity_uid}")
        return Result.ok(alternatives)

    async def get_relationship_graph(
        self,
        entity_uid: EntityUID,
        depth: int = 2,
        relationship_types: list[RelationshipName] | None = None,
    ) -> Result[RelationshipGraphData]:
        """
        Get relationship graph in Vis.js Network format.

        Returns nodes and edges for interactive force-directed graph visualization.

        Args:
            entity_uid: Center entity UID
            depth: Graph traversal depth (1-3 recommended)
            relationship_types: Filter by specific relationship types
                               (None = all lateral relationships)

        Returns:
            Result with Vis.js Network format (nodes + edges)
        """
        # Build type filter
        if relationship_types:
            type_filter = "|".join([rt.value for rt in relationship_types])
        else:
            all_types = [rt.value for rt in RelationshipName if rt.is_lateral_relationship()]
            type_filter = "|".join(all_types)

        from core.utils.palette import RelationshipColor

        # Query graph with depth limit
        result = await self.backend.get_relationship_graph(
            entity_uid=entity_uid,
            type_filter=type_filter,
            depth=depth,
        )

        if result.is_error:
            return Result.fail(result)

        if not result.value:
            # Return just the center node
            center_only: RelationshipGraphData = {
                "nodes": [
                    {
                        "id": entity_uid,
                        "label": entity_uid,
                        "type": "unknown",
                        "entity_type": None,
                        "status": "unknown",
                        "group": "center",
                        "level": 0,
                    }
                ],
                "edges": [],
            }
            return Result.ok(center_only)

        # Build nodes and edges
        nodes_dict: dict[str, dict[str, Any]] = {}
        edges_list: list[dict[str, Any]] = []

        # Add center node
        center_record = result.value[0]
        nodes_dict[entity_uid] = {
            "id": entity_uid,
            "label": center_record["center_title"] or entity_uid,
            "type": center_record["center_type"] or "unknown",
            "entity_type": center_record["center_entity_type"],
            "status": center_record["center_status"] or "unknown",
            "group": "center",
            "level": 0,
        }

        # Process all records
        for record in result.value:
            related_uid = record["related_uid"]
            depth_level = record["depth_level"]

            # Add related node
            if related_uid not in nodes_dict:
                group = "related"
                nodes_dict[related_uid] = {
                    "id": related_uid,
                    "label": record["related_title"] or related_uid,
                    "type": record["related_type"] or "unknown",
                    "entity_type": record["related_entity_type"],
                    "status": record["related_status"] or "unknown",
                    "group": group,
                    "level": depth_level,
                }

            # Add edges from relationships
            relationships = record["relationships"] or []
            for rel in relationships:
                rel_type = rel["type"]
                edge = {
                    "from": rel["from"],
                    "to": rel["to"],
                    "label": rel_type.lower().replace("_", " "),
                    "arrows": "to",
                    "color": {"color": RelationshipColor.for_type(rel_type)},
                    "relationship_type": rel_type,
                }
                # Avoid duplicates
                edge_key = f"{edge['from']}-{edge['to']}-{rel_type}"
                if edge_key not in {
                    f"{e['from']}-{e['to']}-{e['relationship_type']}" for e in edges_list
                }:
                    edges_list.append(edge)

        graph_data: RelationshipGraphData = {
            "nodes": list(nodes_dict.values()),
            "edges": edges_list,
        }

        logger.info(
            f"Generated relationship graph for {entity_uid}: "
            f"{len(nodes_dict)} nodes, {len(edges_list)} edges"
        )
        return Result.ok(graph_data)


__all__ = ["LateralRelationshipService"]
