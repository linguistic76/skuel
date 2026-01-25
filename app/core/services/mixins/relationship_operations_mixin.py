"""
Relationship Operations Mixin
=============================

Provides graph relationship management and prerequisite/hierarchy traversal.

Methods:
    Core Relationships:
        - add_relationship: Create relationship between entities
        - get_relationships: Get all relationships for an entity
        - traverse: Graph traversal following patterns

    Prerequisite Operations:
        - get_prerequisites: Get prerequisite entities
        - get_enables: Get entities enabled by this entity
        - add_prerequisite: Add prerequisite relationship
        - get_hierarchy: Get hierarchical structure
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.services.protocols import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    from logging import Logger

    from core.models.graph_models import GraphPath, Relationship


class RelationshipOperationsMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing graph relationship operations and prerequisite traversal.

    The heart of SKUEL - everything connects through relationships.

    Required attributes from composing class:
        backend: B - Backend implementation
        logger: Logger - For debug logging
        entity_label: str - Neo4j node label
        _prerequisite_relationships: list[str] - Relationship types for prerequisites
        _records_to_domain_models: Method for DTO conversion
        _validate_prerequisites: Validation hook
    """

    # Type hints for attributes that must be provided by composing class
    backend: B
    logger: Logger
    _prerequisite_relationships: ClassVar[list[str]]

    @property
    def entity_label(self) -> str:
        """Entity label - must be provided by composing class."""
        raise NotImplementedError

    def _records_to_domain_models(
        self, records: builtins.list[dict[str, Any]], node_key: str = "n"
    ) -> builtins.list[T]:
        """DTO conversion - provided by ConversionHelpersMixin."""
        raise NotImplementedError

    def _validate_prerequisites(
        self, entity_uid: str, prerequisite_uids: builtins.list[str]
    ) -> Result[None] | None:
        """Validation hook - override in subclass."""
        return None

    # ========================================================================
    # RELATIONSHIP OPERATIONS - The Heart of SKUEL
    # ========================================================================

    async def add_relationship(
        self,
        from_uid: str,
        rel_type: str | RelationshipName,
        to_uid: str,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Add a relationship between two entities.

        This is fundamental to SKUEL - everything connects through relationships.
        Examples:
        - Task DEVELOPS_MASTERY_OF KnowledgeUnit
        - KnowledgeUnit REQUIRES KnowledgeUnit
        - Habit CONTRIBUTES_TO Goal

        Args:
            from_uid: Source entity UID
            rel_type: Relationship type (string or RelationshipName enum)
            to_uid: Target entity UID
            properties: Optional relationship properties

        Returns:
            Result[bool]: True if relationship was created successfully
        """
        if not all([from_uid, rel_type, to_uid]):
            return Result.fail(
                Errors.validation(
                    message="from_uid, rel_type, and to_uid are required", field="relationship"
                )
            )

        # Convert string to RelationshipName if needed
        if isinstance(rel_type, str):
            try:
                relationship_type = RelationshipName[rel_type]
            except KeyError:
                # Try with the value directly (supports both "APPLIES_KNOWLEDGE" lookup)
                try:
                    relationship_type = RelationshipName(rel_type)
                except ValueError:
                    return Result.fail(
                        Errors.validation(
                            message=f"Unknown relationship type: {rel_type}",
                            field="rel_type",
                        )
                    )
        else:
            relationship_type = rel_type

        return await self.backend.add_relationship(
            from_uid=from_uid,
            to_uid=to_uid,
            relationship_type=relationship_type,
            properties=properties,
        )

    async def get_relationships(
        self,
        uid: str,
        rel_type: str | None = None,
        direction: str = "both",  # 'in', 'out', 'both'
    ) -> Result[builtins.list[Relationship]]:
        """
        Get all relationships for an entity.

        Args:
            uid: Entity UID
            rel_type: Optional filter by relationship type
            direction: Direction of relationships to retrieve
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        if direction not in ["in", "out", "both"]:
            return Result.fail(
                Errors.validation(
                    message="Direction must be 'in', 'out', or 'both'", field="direction"
                )
            )

        # Backend must support relationships - enforced at initialization
        return await self.backend.get_relationships(uid, rel_type, direction)

    async def traverse(
        self, start_uid: str, rel_pattern: str, max_depth: int = 3, include_properties: bool = False
    ) -> Result[builtins.list[GraphPath]]:
        """
        Traverse the graph following a relationship pattern.

        Simple but powerful graph traversal - avoiding over-engineering.

        Args:
            start_uid: Starting entity UID
            rel_pattern: Pattern like "REQUIRES*" or "ENABLES+"
            max_depth: Maximum traversal depth
            include_properties: Include relationship properties
        """
        if not start_uid:
            return Result.fail(
                Errors.validation(message="Start UID is required", field="start_uid")
            )

        if max_depth < 1 or max_depth > 10:
            return Result.fail(
                Errors.validation(
                    message="Max depth must be between 1 and 10",
                    field="max_depth",
                    user_message="Traversal depth must be reasonable to avoid performance issues",
                )
            )

        # Backend must support traversal - enforced at initialization
        return await self.backend.traverse(start_uid, rel_pattern, max_depth, include_properties)

    # ========================================================================
    # PREREQUISITE & RELATIONSHIP CHAIN OPERATIONS (January 2026 - Unified)
    # ========================================================================
    # These methods provide prerequisite/enables/hierarchy traversal for ANY domain.
    # Previously only curriculum domains had these; now all 14 domains can use them.
    # Configure via: _prerequisite_relationships, _enables_relationships

    @with_error_handling("get_prerequisites", error_type="database", uid_param="uid")
    async def get_prerequisites(self, uid: str, depth: int = 3) -> Result[builtins.list[T]]:
        """
        Get prerequisite entities for this entity.

        Traverses prerequisite relationships to find all entities
        that must be completed/mastered before this one.

        Requires: _prerequisite_relationships to be configured (non-empty list)

        Uses: build_prerequisite_traversal_query from cypher module (Phase 2 consolidation)

        Args:
            uid: Entity UID
            depth: Maximum prerequisite chain depth (default: 3)

        Returns:
            Result[list[T]]: Ordered list of prerequisites (foundational first)
        """
        if not self._prerequisite_relationships:
            return Result.ok([])  # No prerequisites configured for this domain

        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        if depth < 1 or depth > 10:
            return Result.fail(
                Errors.validation(
                    message="Depth must be between 1 and 10",
                    field="depth",
                )
            )

        from core.models.query.cypher import build_prerequisite_traversal_query

        query, params = build_prerequisite_traversal_query(
            label=self.entity_label,
            uid=uid,
            relationship_types=self._prerequisite_relationships,
            depth=depth,
            direction="outgoing",
        )

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        entities = self._records_to_domain_models(result.value)
        self.logger.debug(f"Found {len(entities)} prerequisites for {uid}")
        return Result.ok(entities)

    @with_error_handling("get_enables", error_type="database", uid_param="uid")
    async def get_enables(self, uid: str, depth: int = 3) -> Result[builtins.list[T]]:
        """
        Get entities enabled by this entity.

        Finds all entities that become accessible after completing/mastering this one.

        Requires: _prerequisite_relationships to be configured (non-empty list)

        Uses: build_prerequisite_traversal_query from cypher module (Phase 2 consolidation)

        Args:
            uid: Entity UID
            depth: Maximum depth to traverse (default: 3)

        Returns:
            Result[list[T]]: Entities that this entity enables
        """
        if not self._prerequisite_relationships:
            return Result.ok([])  # No enables configured for this domain

        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        from core.models.query.cypher import build_prerequisite_traversal_query

        # Use direction="incoming" for enables (inverse of prerequisites)
        query, params = build_prerequisite_traversal_query(
            label=self.entity_label,
            uid=uid,
            relationship_types=self._prerequisite_relationships,
            depth=depth,
            direction="incoming",
        )

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        entities = self._records_to_domain_models(result.value)
        self.logger.debug(f"Found {len(entities)} entities enabled by {uid}")
        return Result.ok(entities)

    async def add_prerequisite(
        self,
        entity_uid: str,
        prerequisite_uid: str,
        confidence: float = 1.0,
    ) -> Result[bool]:
        """
        Add a prerequisite relationship.

        Requires: _prerequisite_relationships to be configured (non-empty list)

        Args:
            entity_uid: The entity that requires the prerequisite
            prerequisite_uid: The prerequisite entity UID
            confidence: Relationship confidence (0.0-1.0)

        Returns:
            Result[bool]: True if relationship was created
        """
        if not self._prerequisite_relationships:
            return Result.fail(
                Errors.business(
                    rule="prerequisites_not_supported",
                    message=f"{self.entity_label} domain does not support prerequisites",
                )
            )

        # Validate
        validation = self._validate_prerequisites(entity_uid, [prerequisite_uid])
        if validation:
            return Result.fail(validation.expect_error())

        # Use first prerequisite relationship type
        rel_type = self._prerequisite_relationships[0]

        return await self.add_relationship(
            from_uid=entity_uid,
            rel_type=rel_type,
            to_uid=prerequisite_uid,
            properties={"confidence": confidence, "created_at": datetime.now(UTC).isoformat()},
        )

    # ========================================================================
    # HIERARCHY OPERATIONS (January 2026 - Unified)
    # ========================================================================

    @with_error_handling("get_hierarchy", error_type="database", uid_param="uid")
    async def get_hierarchy(self, uid: str) -> Result[dict[str, Any]]:
        """
        Get hierarchical structure for this entity.

        Returns the entity's position in any containment hierarchy:
        - Parents: Entities that contain/aggregate this one
        - Children: Entities this one contains/aggregates

        Uses: build_hierarchy_query from cypher module (Phase 2 consolidation)

        Args:
            uid: Entity UID

        Returns:
            Result[dict]: Hierarchical context with parents and children
        """
        if not uid:
            return Result.fail(Errors.validation(message="UID is required", field="uid"))

        from core.models.query.cypher import build_hierarchy_query

        query, params = build_hierarchy_query(
            label=self.entity_label,
            uid=uid,
        )

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value
        if not records:
            return Result.ok({"uid": uid, "parents": [], "children": []})

        record = records[0]
        hierarchy = {
            "uid": uid,
            "entity_type": self.entity_label,
            "parents": [p for p in record.get("parents", []) if p.get("uid")],
            "children": [c for c in record.get("children", []) if c.get("uid")],
        }

        return Result.ok(hierarchy)
