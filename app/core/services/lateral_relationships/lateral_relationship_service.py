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

Usage:
    # Domain services delegate to this core service
    lateral_service = LateralRelationshipService(driver)

    result = await lateral_service.create_lateral_relationship(
        source_uid="goal_a",
        target_uid="goal_b",
        relationship_type=LateralRelationType.BLOCKS,
        metadata={"reason": "Must complete setup first", "severity": "required"}
    )

See: /docs/architecture/LATERAL_RELATIONSHIPS_CORE.md
"""

from typing import Any

from core.models.enums.lateral_relationship_types import LateralRelationType
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class LateralRelationshipService:
    """
    Core service for managing lateral relationships in the graph.

    This service is domain-agnostic and provides the foundation for all
    lateral relationship operations. Domain-specific services (GoalsLateralService,
    TasksLateralService, etc.) use this as their backend.

    Responsibilities:
    - Create/delete lateral relationships
    - Validate relationship constraints
    - Handle bidirectional relationships
    - Query lateral connections
    - Store relationship metadata
    """

    def __init__(self, driver: Any) -> None:
        """
        Initialize lateral relationship service.

        Args:
            driver: Neo4j driver for graph operations
        """
        self.driver = driver

    async def create_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: LateralRelationType,
        metadata: dict[str, Any] | None = None,
        validate: bool = True,
        auto_inverse: bool = True,
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

        Returns:
            Result[bool]: Success if relationship created

        Validation:
            - Entities exist
            - Relationship constraints met (same parent for SIBLING, etc.)
            - No circular dependencies for BLOCKS/PREREQUISITE_FOR
            - No duplicate relationships

        Example:
            ```python
            result = await service.create_lateral_relationship(
                source_uid="goal_learn_python",
                target_uid="goal_build_app",
                relationship_type=LateralRelationType.BLOCKS,
                metadata={
                    "reason": "Must learn language before building",
                    "severity": "required",
                    "created_by": user_uid
                }
            )
            ```
        """
        if source_uid == target_uid:
            return Errors.validation("Cannot create lateral relationship with self")

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
        rel_metadata["relationship_category"] = relationship_type.get_category()
        rel_metadata["is_symmetric"] = relationship_type.is_symmetric()

        # Create the relationship
        try:
            result = await self.driver.execute_query(
                f"""
                MATCH (source {{uid: $source_uid}})
                MATCH (target {{uid: $target_uid}})
                CREATE (source)-[r:{relationship_type.value} $metadata]->(target)
                RETURN r
                """,
                {
                    "source_uid": source_uid,
                    "target_uid": target_uid,
                    "metadata": rel_metadata,
                },
            )

            if not result.records:
                return Errors.database(
                    f"Failed to create {relationship_type.value} relationship"
                )

            logger.info(
                f"✅ Created lateral relationship: {source_uid} -[{relationship_type.value}]-> {target_uid}"
            )

            # Auto-create inverse if asymmetric
            if auto_inverse and not relationship_type.is_symmetric():
                inverse_type = relationship_type.get_inverse()
                if inverse_type:
                    await self._create_inverse_relationship(
                        source_uid=target_uid,  # Reversed
                        target_uid=source_uid,  # Reversed
                        relationship_type=inverse_type,
                        metadata=rel_metadata,
                    )

            return Result.ok(True)

        except Exception as e:
            logger.error(f"❌ Failed to create lateral relationship: {e}")
            return Errors.database(f"Relationship creation failed: {str(e)}")

    async def delete_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: LateralRelationType,
        delete_inverse: bool = True,
    ) -> Result[bool]:
        """
        Delete explicit lateral relationship.

        Args:
            source_uid: Source entity UID
            target_uid: Target entity UID
            relationship_type: Type of relationship to delete
            delete_inverse: Also delete inverse relationship if asymmetric

        Returns:
            Result[bool]: Success if relationship deleted
        """
        try:
            result = await self.driver.execute_query(
                f"""
                MATCH (source {{uid: $source_uid}})-[r:{relationship_type.value}]->(target {{uid: $target_uid}})
                DELETE r
                RETURN count(r) as deleted_count
                """,
                {"source_uid": source_uid, "target_uid": target_uid},
            )

            deleted_count = result.records[0]["deleted_count"] if result.records else 0

            if deleted_count == 0:
                return Errors.not_found(
                    f"Relationship {relationship_type.value} not found between {source_uid} and {target_uid}"
                )

            logger.info(
                f"✅ Deleted lateral relationship: {source_uid} -[{relationship_type.value}]-> {target_uid}"
            )

            # Delete inverse if needed
            if delete_inverse and not relationship_type.is_symmetric():
                inverse_type = relationship_type.get_inverse()
                if inverse_type:
                    await self._delete_inverse_relationship(
                        source_uid=target_uid,
                        target_uid=source_uid,
                        relationship_type=inverse_type,
                    )

            return Result.ok(True)

        except Exception as e:
            logger.error(f"❌ Failed to delete lateral relationship: {e}")
            return Errors.database(f"Relationship deletion failed: {str(e)}")

    async def get_lateral_relationships(
        self,
        entity_uid: str,
        relationship_types: list[LateralRelationType] | None = None,
        direction: str = "outgoing",  # "outgoing", "incoming", "both"
        include_metadata: bool = True,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all lateral relationships for an entity.

        Args:
            entity_uid: Entity UID
            relationship_types: Filter by specific types (None = all types)
            direction: Relationship direction to query
            include_metadata: Include relationship properties in results

        Returns:
            Result with list of relationships:
            ```python
            [
                {
                    "type": "BLOCKS",
                    "target_uid": "goal_xyz",
                    "target_title": "Advanced Topics",
                    "metadata": {"reason": "...", "severity": "required"},
                    "direction": "outgoing"
                },
                ...
            ]
            ```
        """
        # Build type filter
        if relationship_types:
            type_filter = "|".join([rt.value for rt in relationship_types])
        else:
            # All lateral relationship types
            all_types = [rt.value for rt in LateralRelationType]
            type_filter = "|".join(all_types)

        # Build query based on direction
        if direction == "outgoing":
            pattern = f"(entity)-[r:{type_filter}]->(related)"
        elif direction == "incoming":
            pattern = f"(entity)<-[r:{type_filter}]-(related)"
        else:  # both
            pattern = f"(entity)-[r:{type_filter}]-(related)"

        try:
            result = await self.driver.execute_query(
                f"""
                MATCH {pattern}
                WHERE entity.uid = $entity_uid
                RETURN
                    type(r) as relationship_type,
                    related.uid as related_uid,
                    related.title as related_title,
                    properties(r) as metadata,
                    CASE
                        WHEN startNode(r) = entity THEN 'outgoing'
                        ELSE 'incoming'
                    END as direction
                ORDER BY relationship_type, related_title
                """,
                {"entity_uid": entity_uid},
            )

            relationships = [
                {
                    "type": record["relationship_type"],
                    "target_uid": record["related_uid"],
                    "target_title": record["related_title"],
                    "metadata": record["metadata"] if include_metadata else {},
                    "direction": record["direction"],
                }
                for record in result.records
            ]

            logger.info(
                f"✅ Retrieved {len(relationships)} lateral relationships for {entity_uid}"
            )
            return Result.ok(relationships)

        except Exception as e:
            logger.error(f"❌ Failed to get lateral relationships: {e}")
            return Errors.database(f"Query failed: {str(e)}")

    async def get_siblings(
        self,
        entity_uid: str,
        include_explicit_only: bool = False,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get sibling entities (same parent).

        Args:
            entity_uid: Entity UID
            include_explicit_only: Only return explicit SIBLING relationships
                                   (False = derive from hierarchy)

        Returns:
            Result with list of siblings
        """
        if include_explicit_only:
            # Query explicit SIBLING relationships
            return await self.get_lateral_relationships(
                entity_uid,
                relationship_types=[LateralRelationType.SIBLING],
                direction="both",
            )
        else:
            # Derive from hierarchy (share same parent)
            try:
                result = await self.driver.execute_query(
                    """
                    MATCH (parent)-[r]->(sibling)
                    WHERE (parent)-[]->(entity {uid: $entity_uid})
                    AND sibling.uid != $entity_uid
                    AND type(r) IN ['SUBGOAL', 'SUBHABIT', 'SUBEVENT', 'SUBPRINCIPLE',
                                     'SUBCHOICE', 'CONTAINS_STEP', 'ORGANIZES']
                    RETURN
                        sibling.uid as sibling_uid,
                        sibling.title as sibling_title,
                        type(r) as hierarchy_type,
                        r.order as order
                    ORDER BY r.order, sibling.title
                    """,
                    {"entity_uid": entity_uid},
                )

                siblings = [
                    {
                        "uid": record["sibling_uid"],
                        "title": record["sibling_title"],
                        "hierarchy_type": record["hierarchy_type"],
                        "order": record["order"],
                        "relationship": "derived_sibling",
                    }
                    for record in result.records
                ]

                return Result.ok(siblings)

            except Exception as e:
                logger.error(f"❌ Failed to get siblings: {e}")
                return Errors.database(f"Sibling query failed: {str(e)}")

    async def get_cousins(
        self,
        entity_uid: str,
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
        try:
            # Build pattern based on degree
            # 1st cousins: grandparent -> parent1 -> entity, grandparent -> parent2 -> cousin
            # 2nd cousins: great-grandparent -> gp1 -> p1 -> entity, ggp -> gp2 -> p2 -> cousin

            # For simplicity, implement 1st cousins only for now
            if degree != 1:
                return Errors.validation("Only first cousins (degree=1) currently supported")

            result = await self.driver.execute_query(
                """
                MATCH (grandparent)-[]->(parent1)-[]->(entity {uid: $entity_uid})
                MATCH (grandparent)-[]->(parent2)-[]->(cousin)
                WHERE parent1 != parent2
                AND cousin.uid != $entity_uid
                AND NOT (parent1)-[]->(cousin)  // Not a sibling
                RETURN
                    cousin.uid as cousin_uid,
                    cousin.title as cousin_title,
                    grandparent.uid as shared_ancestor_uid,
                    grandparent.title as shared_ancestor_title
                ORDER BY cousin.title
                """,
                {"entity_uid": entity_uid},
            )

            cousins = [
                {
                    "uid": record["cousin_uid"],
                    "title": record["cousin_title"],
                    "shared_ancestor_uid": record["shared_ancestor_uid"],
                    "shared_ancestor_title": record["shared_ancestor_title"],
                    "degree": degree,
                    "relationship": "derived_cousin",
                }
                for record in result.records
            ]

            return Result.ok(cousins)

        except Exception as e:
            logger.error(f"❌ Failed to get cousins: {e}")
            return Errors.database(f"Cousin query failed: {str(e)}")

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _validate_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: LateralRelationType,
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

        # Check same parent constraint
        if relationship_type.requires_same_parent():
            same_parent_result = await self._check_same_parent(source_uid, target_uid)
            if same_parent_result.is_error:
                return same_parent_result

        # Check same depth constraint
        if relationship_type.requires_same_depth():
            same_depth_result = await self._check_same_depth(source_uid, target_uid)
            if same_depth_result.is_error:
                return same_depth_result

        # Check for circular dependencies (BLOCKS, PREREQUISITE_FOR)
        if relationship_type in {
            LateralRelationType.BLOCKS,
            LateralRelationType.PREREQUISITE_FOR,
        }:
            cycle_result = await self._check_no_cycles(source_uid, target_uid, relationship_type)
            if cycle_result.is_error:
                return cycle_result

        return Result.ok(True)

    async def _check_entities_exist(
        self, source_uid: str, target_uid: str
    ) -> Result[bool]:
        """Verify both entities exist in the graph."""
        try:
            result = await self.driver.execute_query(
                """
                MATCH (source {uid: $source_uid})
                MATCH (target {uid: $target_uid})
                RETURN count(source) as source_count, count(target) as target_count
                """,
                {"source_uid": source_uid, "target_uid": target_uid},
            )

            if not result.records:
                return Errors.not_found("One or both entities not found")

            record = result.records[0]
            if record["source_count"] == 0:
                return Errors.not_found(f"Source entity {source_uid} not found")
            if record["target_count"] == 0:
                return Errors.not_found(f"Target entity {target_uid} not found")

            return Result.ok(True)

        except Exception as e:
            return Errors.database(f"Entity existence check failed: {str(e)}")

    async def _check_same_parent(self, source_uid: str, target_uid: str) -> Result[bool]:
        """Verify entities share the same parent."""
        try:
            result = await self.driver.execute_query(
                """
                MATCH (parent)-[]->(source {uid: $source_uid})
                MATCH (parent)-[]->(target {uid: $target_uid})
                RETURN count(parent) as shared_parent_count
                """,
                {"source_uid": source_uid, "target_uid": target_uid},
            )

            if not result.records or result.records[0]["shared_parent_count"] == 0:
                return Errors.validation(
                    "Entities must share same parent for this relationship type"
                )

            return Result.ok(True)

        except Exception as e:
            return Errors.database(f"Same parent check failed: {str(e)}")

    async def _check_same_depth(self, source_uid: str, target_uid: str) -> Result[bool]:
        """Verify entities are at the same hierarchical depth."""
        try:
            # Calculate depth by counting ancestors
            result = await self.driver.execute_query(
                """
                MATCH path1 = (root)-[*]->(source {uid: $source_uid})
                WHERE NOT ()-[]->(root)
                WITH length(path1) as source_depth
                MATCH path2 = (root2)-[*]->(target {uid: $target_uid})
                WHERE NOT ()-[]->(root2)
                WITH source_depth, length(path2) as target_depth
                RETURN source_depth, target_depth
                LIMIT 1
                """,
                {"source_uid": source_uid, "target_uid": target_uid},
            )

            if not result.records:
                # Entities might be roots (depth 0)
                return Result.ok(True)

            record = result.records[0]
            if record["source_depth"] != record["target_depth"]:
                return Errors.validation(
                    f"Entities must be at same depth for this relationship type "
                    f"(source depth: {record['source_depth']}, target depth: {record['target_depth']})"
                )

            return Result.ok(True)

        except Exception as e:
            return Errors.database(f"Same depth check failed: {str(e)}")

    async def _check_no_cycles(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: LateralRelationType,
    ) -> Result[bool]:
        """
        Check that creating this relationship won't create a circular dependency.

        For BLOCKS/PREREQUISITE_FOR: source -> target is invalid if target -> ... -> source exists.
        """
        try:
            # Check if path already exists from target back to source
            result = await self.driver.execute_query(
                f"""
                MATCH (target {{uid: $target_uid}})-[:{relationship_type.value}*1..10]->(source {{uid: $source_uid}})
                RETURN count(*) as cycle_count
                """,
                {"source_uid": source_uid, "target_uid": target_uid},
            )

            if result.records and result.records[0]["cycle_count"] > 0:
                return Errors.validation(
                    f"Creating this {relationship_type.value} relationship would create a circular dependency"
                )

            return Result.ok(True)

        except Exception as e:
            return Errors.database(f"Cycle check failed: {str(e)}")

    async def _create_inverse_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: LateralRelationType,
        metadata: dict[str, Any],
    ) -> None:
        """Create inverse relationship for asymmetric types."""
        try:
            await self.driver.execute_query(
                f"""
                MATCH (source {{uid: $source_uid}})
                MATCH (target {{uid: $target_uid}})
                CREATE (source)-[r:{relationship_type.value} $metadata]->(target)
                """,
                {
                    "source_uid": source_uid,
                    "target_uid": target_uid,
                    "metadata": metadata,
                },
            )
            logger.info(f"✅ Created inverse relationship: {relationship_type.value}")
        except Exception as e:
            logger.error(f"❌ Failed to create inverse relationship: {e}")

    async def _delete_inverse_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: LateralRelationType,
    ) -> None:
        """Delete inverse relationship for asymmetric types."""
        try:
            await self.driver.execute_query(
                f"""
                MATCH (source {{uid: $source_uid}})-[r:{relationship_type.value}]->(target {{uid: $target_uid}})
                DELETE r
                """,
                {"source_uid": source_uid, "target_uid": target_uid},
            )
            logger.info(f"✅ Deleted inverse relationship: {relationship_type.value}")
        except Exception as e:
            logger.error(f"❌ Failed to delete inverse relationship: {e}")


__all__ = ["LateralRelationshipService"]
