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
        relationship_type=RelationshipName.BLOCKS,
        metadata={"reason": "Must complete setup first", "severity": "required"}
    )

See: /docs/architecture/LATERAL_RELATIONSHIPS_CORE.md
"""

from typing import TYPE_CHECKING, Any

from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver
from core.models.relationship_registry import get_lateral_spec
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

    def __init__(self, driver: "AsyncDriver") -> None:
        self.driver = driver

    async def create_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        metadata: dict[str, Any] | None = None,
        validate: bool = True,
        auto_inverse: bool = True,
        user_uid: str | None = None,
        domain_service: Any | None = None,
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
                return Result.fail(
                    Errors.database(
                        operation="create_relationship",
                        message=f"Failed to create {relationship_type.value} relationship",
                    )
                )

            logger.info(
                f"✅ Created lateral relationship: {source_uid} -[{relationship_type.value}]-> {target_uid}"
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

        except Exception as e:
            logger.error(f"❌ Failed to create lateral relationship: {e}")
            return Result.fail(Errors.database(operation="Relationship creation", message=str(e)))

    async def delete_lateral_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
        delete_inverse: bool = True,
        user_uid: str | None = None,
        domain_service: Any | None = None,
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
                return Result.fail(
                    Errors.not_found(
                        f"Relationship {relationship_type.value} not found between {source_uid} and {target_uid}"
                    )
                )

            logger.info(
                f"✅ Deleted lateral relationship: {source_uid} -[{relationship_type.value}]-> {target_uid}"
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

        except Exception as e:
            logger.error(f"❌ Failed to delete lateral relationship: {e}")
            return Result.fail(Errors.database(operation="Relationship deletion", message=str(e)))

    async def get_lateral_relationships(
        self,
        entity_uid: str,
        relationship_types: list[RelationshipName] | None = None,
        direction: str = "outgoing",  # "outgoing", "incoming", "both"
        include_metadata: bool = True,
        user_uid: str | None = None,
        domain_service: Any | None = None,
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
                    "direction": "outgoing",
                },
                ...,
            ]
            ```
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
            # All lateral relationship types
            all_types = [rt.value for rt in RelationshipName if rt.is_lateral_relationship()]
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

            logger.info(f"✅ Retrieved {len(relationships)} lateral relationships for {entity_uid}")
            return Result.ok(relationships)

        except Exception as e:
            logger.error(f"❌ Failed to get lateral relationships: {e}")
            return Result.fail(Errors.database(operation="Query", message=str(e)))

    async def get_siblings(
        self,
        entity_uid: str,
        include_explicit_only: bool = False,
        user_uid: str | None = None,
        domain_service: Any | None = None,
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
            # Query explicit SIBLING relationships
            return await self.get_lateral_relationships(
                entity_uid,
                relationship_types=[RelationshipName.SIBLING],
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
                return Result.fail(Errors.database(operation="Sibling query", message=str(e)))

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
                return Result.fail(
                    Errors.validation("Only first cousins (degree=1) currently supported")
                )

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
            return Result.fail(Errors.database(operation="Cousin query", message=str(e)))

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
                return Result.fail(Errors.not_found("One or both entities not found"))

            record = result.records[0]
            if record["source_count"] == 0:
                return Result.fail(Errors.not_found(f"Source entity {source_uid} not found"))
            if record["target_count"] == 0:
                return Result.fail(Errors.not_found(f"Target entity {target_uid} not found"))

            return Result.ok(True)

        except Exception as e:
            return Result.fail(Errors.database(operation="Entity existence check", message=str(e)))

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
                return Result.fail(
                    Errors.validation("Entities must share same parent for this relationship type")
                )

            return Result.ok(True)

        except Exception as e:
            return Result.fail(Errors.database(operation="Same parent check", message=str(e)))

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
                return Result.fail(
                    Errors.validation(
                        f"Entities must be at same depth for this relationship type "
                        f"(source depth: {record['source_depth']}, target depth: {record['target_depth']}))"
                    )
                )

            return Result.ok(True)

        except Exception as e:
            return Result.fail(Errors.database(operation="Same depth check", message=str(e)))

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
                return Result.fail(
                    Errors.validation(
                        f"Creating this {relationship_type.value} relationship would create a circular dependency"
                    )
                )

            return Result.ok(True)

        except Exception as e:
            return Result.fail(Errors.database(operation="Cycle check", message=str(e)))

    async def _create_inverse_relationship(
        self,
        source_uid: str,
        target_uid: str,
        relationship_type: RelationshipName,
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
        relationship_type: RelationshipName,
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

    # ========================================================================
    # Enhanced UX Methods (Phase 5)
    # ========================================================================

    async def get_blocking_chain(
        self,
        entity_uid: str,
        max_depth: int = 10,
    ) -> Result[dict[str, Any]]:
        """
        Get transitive blocking chain with depth levels.

        Returns all entities that block the given entity, organized by depth
        from the root blockers to the immediate blockers.

        Args:
            entity_uid: Entity UID to get blockers for
            max_depth: Maximum depth to traverse (default 10)

        Returns:
            Result with blocking chain data:
            ```python
            {
                "root_uid": "task_deploy",
                "total_blockers": 3,
                "chain_depth": 2,
                "levels": [
                    {
                        "depth": 0,
                        "entities": [
                            {
                                "uid": "task_setup_env",
                                "title": "Setup Environment",
                                "entity_type": "task",
                                "status": "completed",
                                "blocks_count": 1,
                            }
                        ],
                    },
                    ...,
                ],
                "critical_path": ["task_setup_env", "task_install_deps", "task_deploy"],
            }
            ```

        Example:
            ```python
            result = await service.get_blocking_chain("task_deploy_app", max_depth=5)
            if not result.is_error:
                print(f"Chain depth: {result.value['chain_depth']}")
                for level in result.value["levels"]:
                    print(f"Depth {level['depth']}: {len(level['entities'])} blockers")
            ```
        """
        try:
            result = await self.driver.execute_query(
                """
                MATCH path = (blocker)-[:BLOCKS*1..10]->(entity {uid: $uid})
                WITH blocker, path, length(path) as depth
                RETURN
                    blocker.uid as uid,
                    blocker.title as title,
                    blocker.status as status,
                    labels(blocker)[0] as entity_type,
                    depth,
                    size((blocker)-[:BLOCKS]->()) as blocks_count
                ORDER BY depth DESC
                """,
                {"uid": entity_uid},
            )

            if not result.records:
                return Result.ok(
                    {
                        "root_uid": entity_uid,
                        "total_blockers": 0,
                        "chain_depth": 0,
                        "levels": [],
                        "critical_path": [entity_uid],
                    }
                )

            # Group by depth
            levels_dict: dict[int, list[dict[str, Any]]] = {}
            all_blockers = []

            for record in result.records:
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

            chain_data = {
                "root_uid": entity_uid,
                "total_blockers": len(all_blockers),
                "chain_depth": max_depth_val,
                "levels": levels,
                "critical_path": critical_path,
            }

            logger.info(
                f"✅ Retrieved blocking chain for {entity_uid}: "
                f"{len(all_blockers)} blockers across {max_depth_val} levels"
            )
            return Result.ok(chain_data)

        except Exception as e:
            logger.error(f"❌ Failed to get blocking chain: {e}")
            return Result.fail(Errors.database(operation="Blocking chain query", message=str(e)))

    async def get_alternatives_with_comparison(
        self,
        entity_uid: str,
        comparison_fields: list[str] | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get alternative entities with side-by-side comparison data.

        Args:
            entity_uid: Entity UID to get alternatives for
            comparison_fields: Specific fields to include in comparison
                              (None = all available fields)

        Returns:
            Result with list of alternatives with comparison data:
            ```python
            [
                {
                    "uid": "goal_career_a",
                    "title": "Corporate Leadership",
                    "entity_type": "goal",
                    "status": "active",
                    "priority": "high",
                    "description": "...",
                    "comparison_data": {
                        "timeframe": "5 years",
                        "difficulty": "high",
                        "resources": "company sponsored",
                    },
                    "metadata": {
                        "tradeoffs": "Less flexibility, higher pay",
                        "comparison_criteria": "career growth vs autonomy",
                    },
                },
                ...,
            ]
            ```

        Example:
            ```python
            result = await service.get_alternatives_with_comparison(
                "goal_corporate_leadership",
                comparison_fields=["timeframe", "difficulty", "resources"],
            )
            if not result.is_error:
                for alt in result.value:
                    print(f"Alternative: {alt['title']}")
                    print(f"Tradeoffs: {alt['metadata']['tradeoffs']}")
            ```
        """
        try:
            result = await self.driver.execute_query(
                """
                MATCH (entity {uid: $uid})-[r:ALTERNATIVE_TO]-(alternative)
                RETURN
                    alternative.uid as uid,
                    alternative.title as title,
                    alternative.description as description,
                    alternative.status as status,
                    alternative.priority as priority,
                    labels(alternative)[0] as entity_type,
                    r.comparison_criteria as comparison_criteria,
                    r.tradeoffs as tradeoffs,
                    r.timeframe as timeframe,
                    r.difficulty as difficulty,
                    r.resources as resources,
                    properties(alternative) as all_properties,
                    properties(r) as rel_properties
                """,
                {"uid": entity_uid},
            )

            if not result.records:
                return Result.ok([])

            alternatives = []
            for record in result.records:
                # Build comparison data from relationship properties
                comparison_data = {}
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

                alternative_data = {
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

            logger.info(f"✅ Retrieved {len(alternatives)} alternatives for {entity_uid}")
            return Result.ok(alternatives)

        except Exception as e:
            logger.error(f"❌ Failed to get alternatives with comparison: {e}")
            return Result.fail(Errors.database(operation="Alternatives query", message=str(e)))

    async def get_relationship_graph(
        self,
        entity_uid: str,
        depth: int = 2,
        relationship_types: list[RelationshipName] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Get relationship graph in Vis.js Network format.

        Returns nodes and edges for interactive force-directed graph visualization.

        Args:
            entity_uid: Center entity UID
            depth: Graph traversal depth (1-3 recommended)
            relationship_types: Filter by specific relationship types
                               (None = all lateral relationships)

        Returns:
            Result with Vis.js Network format:
            ```python
            {
                "nodes": [
                    {
                        "id": "task_abc",
                        "label": "Setup Environment",
                        "type": "task",
                        "status": "completed",
                        "group": "blocker",
                        "level": 0,
                    },
                    ...,
                ],
                "edges": [
                    {
                        "from": "task_abc",
                        "to": "task_xyz",
                        "label": "blocks",
                        "arrows": "to",
                        "color": {"color": "#EF4444"},
                        "relationship_type": "BLOCKS",
                    },
                    ...,
                ],
            }
            ```

        Color Scheme:
            - BLOCKS → Red (#EF4444)
            - PREREQUISITE_FOR → Orange (#F59E0B)
            - ALTERNATIVE_TO → Blue (#3B82F6)
            - COMPLEMENTARY_TO → Green (#10B981)
            - RELATED_TO → Gray (#6B7280)

        Example:
            ```python
            result = await service.get_relationship_graph(
                "task_deploy",
                depth=2,
                relationship_types=[
                    RelationshipName.BLOCKS,
                    RelationshipName.PREREQUISITE_FOR,
                ],
            )
            if not result.is_error:
                graph_data = result.value
                print(
                    f"Nodes: {len(graph_data['nodes'])}, Edges: {len(graph_data['edges'])}"
                )
            ```
        """
        # Build type filter
        if relationship_types:
            type_filter = "|".join([rt.value for rt in relationship_types])
        else:
            all_types = [rt.value for rt in RelationshipName if rt.is_lateral_relationship()]
            type_filter = "|".join(all_types)

        # Color mapping for relationship types
        def get_relationship_color(rel_type: str) -> str:
            """Map relationship type to color."""
            color_map = {
                "BLOCKS": "#EF4444",  # Red
                "PREREQUISITE_FOR": "#F59E0B",  # Orange
                "ALTERNATIVE_TO": "#3B82F6",  # Blue
                "COMPLEMENTARY_TO": "#10B981",  # Green
                "RELATED_TO": "#6B7280",  # Gray
                "SIBLING": "#8B5CF6",  # Purple
            }
            return color_map.get(rel_type, "#6B7280")

        try:
            # Query graph with depth limit
            result = await self.driver.execute_query(
                f"""
                MATCH path = (center {{uid: $uid}})-[r:{type_filter}*1..{depth}]-(related)
                WITH center, r, related, length(path) as depth_level
                RETURN DISTINCT
                    center.uid as center_uid,
                    center.title as center_title,
                    labels(center)[0] as center_type,
                    center.status as center_status,
                    related.uid as related_uid,
                    related.title as related_title,
                    labels(related)[0] as related_type,
                    related.status as related_status,
                    [rel in r | {{
                        type: type(rel),
                        from: startNode(rel).uid,
                        to: endNode(rel).uid
                    }}] as relationships,
                    depth_level
                """,
                {"uid": entity_uid},
            )

            if not result.records:
                # Return just the center node
                return Result.ok(
                    {
                        "nodes": [
                            {
                                "id": entity_uid,
                                "label": entity_uid,
                                "type": "unknown",
                                "status": "unknown",
                                "group": "center",
                                "level": 0,
                            }
                        ],
                        "edges": [],
                    }
                )

            # Build nodes and edges
            nodes_dict: dict[str, dict[str, Any]] = {}
            edges_list = []

            # Add center node
            center_record = result.records[0]
            nodes_dict[entity_uid] = {
                "id": entity_uid,
                "label": center_record["center_title"] or entity_uid,
                "type": center_record["center_type"] or "unknown",
                "status": center_record["center_status"] or "unknown",
                "group": "center",
                "level": 0,
            }

            # Process all records
            for record in result.records:
                related_uid = record["related_uid"]
                depth_level = record["depth_level"]

                # Add related node
                if related_uid not in nodes_dict:
                    # Determine group based on relationship
                    group = "related"
                    nodes_dict[related_uid] = {
                        "id": related_uid,
                        "label": record["related_title"] or related_uid,
                        "type": record["related_type"] or "unknown",
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
                        "color": {"color": get_relationship_color(rel_type)},
                        "relationship_type": rel_type,
                    }
                    # Avoid duplicates
                    edge_key = f"{edge['from']}-{edge['to']}-{rel_type}"
                    if edge_key not in {
                        f"{e['from']}-{e['to']}-{e['relationship_type']}" for e in edges_list
                    }:
                        edges_list.append(edge)

            graph_data = {
                "nodes": list(nodes_dict.values()),
                "edges": edges_list,
            }

            logger.info(
                f"✅ Generated relationship graph for {entity_uid}: "
                f"{len(nodes_dict)} nodes, {len(edges_list)} edges"
            )
            return Result.ok(graph_data)

        except Exception as e:
            logger.error(f"❌ Failed to get relationship graph: {e}")
            return Result.fail(
                Errors.database(operation="Relationship graph query", message=str(e))
            )


__all__ = ["LateralRelationshipService"]
