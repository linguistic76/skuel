"""
Relationship CRUD Mixin
=======================

Graph-native relationship creation, deletion, validation, and private helpers.

Provides:
    _extract_label_from_uid: Fast UID-to-label mapping
    _build_direction_pattern: Build directional Cypher patterns
    _get_node_labels: Query node labels from database
    create_relationship: Create/update a graph relationship (with validation)
    delete_relationship: Delete a relationship
    delete_relationships_batch: Batch relationship deletion
    has_relationship: Check relationship existence
    count_related: Count related entities without loading them
    create_relationships_batch: Batch relationship creation (with validation)

Requires on concrete class:
    driver, logger, label, entity_class, default_filters
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.utils.error_boundary import safe_backend_operation
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver

    from core.ports.base_protocols import Direction


class _RelationshipCrudMixin[T: DomainModelProtocol]:
    """
    Relationship CRUD methods — create, delete, validate, count, check, batch.

    Requires on concrete class:
        driver: AsyncDriver
        logger: logging.Logger
        label: str
        entity_class: type[T]
        default_filters: dict[str, Any]
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        logger: logging.Logger
        label: str
        entity_class: type[T]
        default_filters: dict[str, Any]

    # ============================================================================
    # GRAPH-NATIVE RELATIONSHIP API (October 26, 2025)
    # ============================================================================
    # Generic relationship methods for pure graph operations.
    # These eliminate the need for denormalized UID lists in domain models.

    def _extract_label_from_uid(self, uid: str) -> str | None:
        """
        Extract label from UID pattern (e.g., 'task:123' → 'Task').

        SKUEL uses consistent UID patterns: {domain}:{id}
        Fast pattern matching, no DB query needed.

        Args:
            uid: Entity UID (e.g., "task:123", "ku.python-basics")

        Returns:
            Label string if pattern matches, None otherwise (requires DB fallback)

        Examples:
            >>> backend._extract_label_from_uid("task:123")
            "Task"
            >>> backend._extract_label_from_uid("ku.python-basics")
            "Entity"
            >>> backend._extract_label_from_uid("unknown:xyz")
            None
        """
        # Common UID patterns in SKUEL
        patterns = {
            "task:": "Task",
            "event:": "Event",
            "habit:": "Habit",
            "goal:": "Goal",
            "principle:": "Principle",
            "choice:": "Choice",
            "ku.": "Entity",  # Knowledge uses dots
            "user.": "User",
            "expense:": "Expense",
        }

        for prefix, label in patterns.items():
            if uid.startswith(prefix):
                return label

        return None  # Fallback to DB query

    def _build_direction_pattern(
        self,
        relationship_type: str,
        direction: Direction,
        source_var: str = "n",
        target_var: str = "related",
        rel_var: str | None = None,
        target_label: str | None = None,
    ) -> Result[str]:
        """
        Build Cypher pattern for directional relationship traversal.

        Consolidates repeated pattern building across:
        - get_related_entities() (with target label)
        - get_related_uids() (with relationship variable)
        - count_related() (with relationship variable)

        Args:
            relationship_type: The relationship type (e.g., "PREREQUISITE", "OWNS")
            direction: Traversal direction ("outgoing", "incoming", or "both")
            source_var: Variable name for source node (default: "n")
            target_var: Variable name for target node (default: "related")
            rel_var: Optional relationship variable name (e.g., "r" for property access)
            target_label: Optional label constraint on target node

        Returns:
            Result[str] containing the Cypher pattern or validation error

        Examples:
            >>> backend._build_direction_pattern("OWNS", "outgoing")
            Result.ok("(n)-[:OWNS]->(related)")

            >>> backend._build_direction_pattern("PREREQUISITE", "incoming", rel_var="r")
            Result.ok("(n)<-[r:PREREQUISITE]-(related)")

            >>> backend._build_direction_pattern("OWNS", "outgoing", target_label="Task")
            Result.ok("(n)-[:OWNS]->(related:Task)")
        """
        # Build relationship part: [r:TYPE] or [:TYPE]
        rel_part = f"[{rel_var}:{relationship_type}]" if rel_var else f"[:{relationship_type}]"

        # Build target part: (related) or (related:Label)
        target_part = f"({target_var}:{target_label})" if target_label else f"({target_var})"

        # Build pattern based on direction
        match direction:
            case "outgoing":
                return Result.ok(f"({source_var})-{rel_part}->{target_part}")
            case "incoming":
                return Result.ok(f"({source_var})<-{rel_part}-{target_part}")
            case "both":
                return Result.ok(f"({source_var})-{rel_part}-{target_part}")
            case _:
                return Result.fail(
                    Errors.validation(
                        message=f"Invalid direction: {direction}. Valid options: outgoing, incoming, both",
                        field="direction",
                        value=direction,
                    )
                )

    @safe_backend_operation("get_node_labels")
    async def _get_node_labels(
        self, from_uid: str, to_uid: str
    ) -> Result[tuple[builtins.list[str], builtins.list[str]]]:
        """
        Query database for node labels (single efficient query).

        Gets labels for both source and target nodes in ONE transaction.
        Used for validation when UID pattern matching fails.

        Args:
            from_uid: Source node UID
            to_uid: Target node UID

        Returns:
            Result containing tuple of (source_labels, target_labels)
            Returns error if either node doesn't exist

        Example:
            >>> result = await backend._get_node_labels("task:123", "ku.python")
            >>> source_labels, target_labels = result.value
            >>> print(source_labels)  # ["Task"]
            >>> print(target_labels)  # ["Entity", "Entity"]
        """
        query = """
        MATCH (a {uid: $from_uid})
        MATCH (b {uid: $to_uid})
        RETURN labels(a) as source_labels, labels(b) as target_labels
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
            record = await result.single()

            if not record:
                return Result.fail(
                    Errors.not_found(
                        resource="Node",
                        identifier=f"{from_uid} or {to_uid}",
                    )
                )

            source_labels = record.get("source_labels", [])
            target_labels = record.get("target_labels", [])

            return Result.ok((source_labels, target_labels))

    @safe_backend_operation("create_relationship")
    async def create_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Create or update a graph relationship between two entities.


        - Validates relationship type for source domain (hard failure)
        - Validates target node label matches registry spec (hard failure)
        - Uses UID parsing + DB fallback for label extraction
        - Ensures semantic correctness of graph relationships

        GRAPH-NATIVE: Creates pure Neo4j relationship edges, not node properties.
        This is the foundation for eliminating UID list fields from domain models.

        Uses MERGE to be idempotent - if relationship exists, updates properties.
        This prevents duplicate relationships and allows safe retry logic.

        Args:
            from_uid: Source entity UID (must exist in database)
            to_uid: Target entity UID (must exist in database)
            relationship_type: Neo4j relationship type (e.g., "APPLIES_KNOWLEDGE", "DEPENDS_ON")
                              MUST match RelationshipRegistry for source domain
            properties: Optional relationship properties (metadata). Common properties:
                       - confidence: float (0.0-1.0) - relationship confidence score
                       - strength: float - relationship strength
                       - created_at: datetime - when relationship was created
                       - Any domain-specific metadata

        Returns:
            Result[bool]: Success with True if created/updated
            Result[Error]: Validation failure or database error

        Validation Errors:
            - Invalid relationship type for source domain
            - Invalid target node label (doesn't match registry spec)
            - Source or target node doesn't exist

        Examples:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Valid relationship - passes validation
            result = await backend.create_relationship(
                from_uid="task:123",
                to_uid="ku.python-basics",
                relationship_type="APPLIES_KNOWLEDGE",
            )
            # ✅ Task -> Knowledge is valid per registry

            # Invalid relationship - fails validation
            result = await backend.create_relationship(
                from_uid="task:123",
                to_uid="habit:exercise",
                relationship_type="APPLIES_KNOWLEDGE",
            )
            # ❌ Error: APPLIES_KNOWLEDGE expects Knowledge target, not Habit
            ```

        Note:
            - Both entities must exist before creating relationship
            - MERGE makes this idempotent (safe to call multiple times)
            - RelationshipRegistry validation is AUTOMATIC (no manual checks needed)
            - For batch operations, use create_relationships_batch() for better performance
            - Relationship properties are optional but recommended for graph analytics

        See Also:
            - delete_relationship(): Remove relationships
            - has_relationship(): Check if relationship exists
            - get_relationship_metadata(): Retrieve relationship properties
            - RelationshipRegistry: Valid relationship types per domain
        """
        from core.models.relationship_registry import (
            get_relationship_metadata,
            get_valid_relationships,
            validate_relationship,
        )

        # ========================================================================
        # C: VALIDATION (Hard Failures)
        # ========================================================================

        # Step 1: Extract source label (fast UID parsing first)
        source_label = self._extract_label_from_uid(from_uid)

        # Step 2: Get node labels from database (needed for target validation)
        labels_result = await self._get_node_labels(from_uid, to_uid)
        if labels_result.is_error:
            return Result.fail(labels_result.expect_error())  # Nodes don't exist

        source_labels: builtins.list[str]
        target_labels: builtins.list[str]
        source_labels, target_labels = labels_result.value

        # Use DB label if UID parsing failed
        if not source_label and source_labels:
            source_label = source_labels[0]

        if not source_label:
            return Result.fail(
                Errors.validation(
                    message=f"Unable to determine source label for UID: {from_uid}",
                    field="from_uid",
                    value=from_uid,
                )
            )

        # Step 3: Validate relationship type for source domain
        if not validate_relationship(source_label, relationship_type):
            valid_rels = get_valid_relationships(source_label)
            from core.utils.result_simplified import ErrorCategory, ErrorContext, ErrorSeverity

            return Result.fail(
                ErrorContext(
                    category=ErrorCategory.VALIDATION,
                    code="VALIDATION_FIELD_RELATIONSHIP_TYPE",
                    message=(
                        f"Invalid relationship type '{relationship_type}' for {source_label}. "
                        f"Valid types: {list(valid_rels.keys())}"
                    ),
                    severity=ErrorSeverity.LOW,
                    details={
                        "field": "relationship_type",
                        "value": relationship_type,
                        "source_label": source_label,
                        "source_uid": from_uid,
                        "valid_relationship_types": list(valid_rels.keys()),
                    },
                    user_message=f"Invalid relationship type '{relationship_type}'",
                    source_location=ErrorContext.capture_current_location(),
                )
            )

        # Step 4: Validate target node label
        spec = get_relationship_metadata(source_label, relationship_type)
        if spec and spec.target_labels:
            primary_target_label = target_labels[0] if target_labels else "Unknown"

            # Check if any of the node's labels match the spec
            valid_target = any(label in spec.target_labels for label in target_labels)

            if not valid_target:
                from core.utils.result_simplified import ErrorCategory, ErrorContext, ErrorSeverity

                return Result.fail(
                    ErrorContext(
                        category=ErrorCategory.VALIDATION,
                        code="VALIDATION_FIELD_TARGET_LABEL",
                        message=(
                            f"Invalid target label for relationship: "
                            f"{source_label} --[{relationship_type}]-> {primary_target_label}. "
                            f"Expected target labels: {spec.target_labels}"
                        ),
                        severity=ErrorSeverity.LOW,
                        details={
                            "field": "target_label",
                            "value": primary_target_label,
                            "source_label": source_label,
                            "target_labels": target_labels,
                            "expected_target_labels": spec.target_labels,
                            "relationship_type": relationship_type,
                        },
                        user_message=f"Invalid target type for {relationship_type} relationship",
                        source_location=ErrorContext.capture_current_location(),
                    )
                )

        # Note: Property validation and cardinality constraints were removed in January 2026
        # during the RelationshipRegistry migration. The new registry focuses on
        # essential validation (relationship type + target labels). Add cardinality
        # constraints to UnifiedRelationshipDefinition if needed in the future.

        # ========================================================================
        # RELATIONSHIP CREATION (All Validation Passed)
        # ========================================================================

        props = properties or {}

        query = f"""
        MATCH (a {{uid: $from_uid}})
        MATCH (b {{uid: $to_uid}})
        MERGE (a)-[r:{relationship_type}]->(b)
        SET r += $properties
        RETURN r
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, {"from_uid": from_uid, "to_uid": to_uid, "properties": props}
            )
            await result.single()

        self.logger.debug(
            f"Created relationship: {from_uid} --[{relationship_type}]-> {to_uid}"
        )
        return Result.ok(True)

    @safe_backend_operation("delete_relationship")
    async def delete_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[bool]:
        """
        DETACH DELETE a graph relationship between two entities.

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            relationship_type: Neo4j relationship type

        Returns:
            Result[bool] indicating success (True even if relationship didn't exist)

        Example:
            await backend.delete_relationship(
                from_uid="task:123",
                to_uid="ku:python-basics",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE
            )
        """
        rel_type = relationship_type.value
        query = f"""
        MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
        DETACH DELETE r
        RETURN count(r) as deleted_count
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
            record = await result.single()
            deleted_count = record["deleted_count"] if record else 0

        self.logger.debug(
            f"Deleted {deleted_count} relationship(s): {from_uid} --[{rel_type}]-> {to_uid}"
        )
        return Result.ok(True)

    @safe_backend_operation("delete_relationships_batch")
    async def delete_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str]]
    ) -> Result[int]:
        """
        Delete multiple relationships in a single transaction.

        Symmetric with create_relationships_batch() for efficient bulk deletion.
        Idempotent - no error if relationships don't exist.

        Args:
            relationships: List of (from_uid, to_uid, rel_type) tuples

        Returns:
            Result[int] with count of relationships deleted

        Example:
            relationships = [
                ("task:123", "ku:python", "APPLIES_KNOWLEDGE"),
                ("task:123", "ku:algorithms", "REQUIRES_KNOWLEDGE"),
            ]
            result = await backend.delete_relationships_batch(relationships)
            print(f"Deleted {result.value} relationships")
        """
        from core.infrastructure.batch import BatchOperationHelper

        if not relationships:
            return Result.ok(0)

        # Use BatchOperationHelper for query generation
        query_result = BatchOperationHelper.build_relationship_delete_query(relationships)

        async with self.driver.session() as session:
            result = await session.run(query_result.query, query_result.params)
            record = await result.single()
            deleted_count = record["deleted_count"] if record else 0

        self.logger.debug(
            f"Batch deleted {deleted_count} relationships ({len(relationships)} requested)"
        )
        return Result.ok(deleted_count)

    @safe_backend_operation("has_relationship")
    async def has_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[bool]:
        """
        Check if a graph relationship exists between two entities.

        Efficient existence check - returns True/False without loading properties or entities.
        Much faster than get_relationship_metadata() when you only need to check existence.

        Args:
            from_uid: Source entity UID (must exist)
            to_uid: Target entity UID (must exist)
            relationship_type: Neo4j relationship type (exact match, case-sensitive)

        Returns:
            Result[bool]: Success with True if relationship exists, False if not,
                         or Failure if database error

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Check before creating to avoid duplicates
            exists = await backend.has_relationship(
                from_uid="task:123",
                to_uid="ku:python-basics",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            )

            if not exists.value:
                await backend.create_relationship(
                    from_uid="task:123",
                    to_uid="ku:python-basics",
                    relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
                )
            ```

        Performance:
            - O(1) lookup using relationship index
            - No property loading (very fast)
            - Use for existence checks before mutations

        Note:
            - Checks exact relationship type (case-sensitive)
            - Direction matters: (from)-[:TYPE]->(to) is different from (to)-[:TYPE]->(from)
            - For bidirectional check, call twice with swapped UIDs
            - Returns False if either entity doesn't exist

        See Also:
            - create_relationship(): Create new relationships
            - get_relationship_metadata(): Get relationship properties
            - count_related(): Count all relationships of a type
        """
        rel_type = relationship_type.value
        query = f"""
        MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
        RETURN count(r) > 0 as exists
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
            record = await result.single()
            exists = record["exists"] if record else False

        return Result.ok(exists)

    @safe_backend_operation("count_related")
    async def count_related(
        self,
        uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        properties: dict[str, Any] | None = None,
    ) -> Result[int]:
        """
        Count related entities without loading them.

        Efficient for checking relationship counts (e.g., "How many prerequisites?").
        Use this instead of `len(await get_related_uids())` for better performance.

        Args:
            uid: Entity UID
            relationship_type: Neo4j relationship type
            direction: "outgoing", "incoming", or "both"
            properties: Optional dict of relationship properties to filter by

        Returns:
            Result[int] with relationship count

        Examples:
            # Count how many knowledge units this task applies
            count_result = await backend.count_related(
                uid="task:123",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
                direction="outgoing"
            )
            print(f"Task applies {count_result.value} knowledge units")

            # Count prerequisites
            prereq_count = await backend.count_related(
                uid="ku:advanced-python",
                relationship_type=RelationshipName.REQUIRES_KNOWLEDGE,
                direction="outgoing"
            )

            # Count essential habits (with property filtering)
            essential_count = await backend.count_related(
                uid="goal:fitness",
                relationship_type=RelationshipName.REQUIRES_HABIT,
                direction="outgoing",
                properties={"essentiality": "essential"}
            )
            print(f"Goal has {essential_count.value} essential habits")
        """
        # Extract string value for Cypher query
        rel_type = relationship_type.value

        # Build Cypher pattern using helper (with named relationship variable for property access)
        pattern_result = self._build_direction_pattern(
            relationship_type=rel_type,
            direction=direction,
            rel_var="r",
        )
        if pattern_result.is_error:
            return Result.fail(pattern_result.expect_error())
        pattern = pattern_result.value

        # Build WHERE clause for property filtering
        where_clauses = []
        params = {"uid": uid}

        if properties:
            for key, value in properties.items():
                param_name = f"prop_{key}"
                where_clauses.append(f"r.{key} = ${param_name}")
                params[param_name] = value

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
        MATCH (n {{uid: $uid}})
        MATCH {pattern}
        {where_clause}
        RETURN count(related) as count
        """

        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            count = record["count"] if record else 0

        return Result.ok(count)

    @safe_backend_operation("create_relationships_batch")
    async def create_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str, dict[str, Any] | None]]
    ) -> Result[int]:
        """
        Create multiple relationships in a single transaction.


        - Validates ALL relationships BEFORE creating ANY (transaction integrity)
        - Returns detailed errors for invalid relationships
        - Uses efficient batch validation with single DB query

        Efficient batch operation for creating many relationships at once.
        Uses UNWIND for optimal performance.

        Args:
            relationships: List of (from_uid, to_uid, rel_type, properties) tuples

        Returns:
            Result[int] with count of relationships created
            Result[Error] if ANY relationship fails validation (creates NONE)

        Validation:
            - All relationship types must be valid for their source domains
            - All target labels must match registry specs
            - Validates ALL before creating ANY (transaction integrity)

        Example:
            # Create multiple task -> knowledge relationships
            rels = [
                ("task:123", "ku.python-basics", "APPLIES_KNOWLEDGE", {"confidence": 0.9}),
                ("task:123", "ku.functions", "APPLIES_KNOWLEDGE", {"confidence": 0.8}),
                ("task:123", "ku.loops", "APPLIES_KNOWLEDGE", {"confidence": 0.7})
            ]
            result = await backend.create_relationships_batch(rels)
            print(f"Created {result.value} relationships") # All or nothing
        """
        from core.models.relationship_registry import (
            get_relationship_metadata,
            get_valid_relationships,
            validate_relationship,
        )

        if not relationships:
            return Result.ok(0)

        # ========================================================================
        # C: BATCH VALIDATION (Validate ALL before creating ANY)
        # ========================================================================

        validation_errors = []

        for idx, (from_uid, to_uid, rel_type, _props) in enumerate(relationships):
            # Step 1: Extract source label (fast UID parsing)
            # Note: _props intentionally unused - property validation not yet implemented
            source_label = self._extract_label_from_uid(from_uid)

            # Step 2: Get node labels from database
            labels_result = await self._get_node_labels(from_uid, to_uid)
            if labels_result.is_error:
                validation_errors.append(
                    {
                        "index": idx,
                        "from_uid": from_uid,
                        "to_uid": to_uid,
                        "relationship_type": rel_type,
                        "error": "Nodes not found",
                        "details": labels_result.expect_error().message,
                    }
                )
                continue

            source_labels: builtins.list[str]
            target_labels: builtins.list[str]
            source_labels, target_labels = labels_result.value

            # Use DB label if UID parsing failed
            if not source_label and source_labels:
                source_label = source_labels[0]

            if not source_label:
                validation_errors.append(
                    {
                        "index": idx,
                        "from_uid": from_uid,
                        "error": "Unable to determine source label",
                    }
                )
                continue

            # Step 3: Validate relationship type for source domain
            if not validate_relationship(source_label, rel_type):
                valid_rels = get_valid_relationships(source_label)
                validation_errors.append(
                    {
                        "index": idx,
                        "from_uid": from_uid,
                        "to_uid": to_uid,
                        "relationship_type": rel_type,
                        "error": f"Invalid relationship type '{rel_type}' for {source_label}",
                        "valid_types": list(valid_rels.keys()),
                    }
                )
                continue

            # Step 4: Validate target node label
            spec = get_relationship_metadata(source_label, rel_type)
            if spec and spec.target_labels:
                # Check if any of the node's labels match the spec
                valid_target = any(label in spec.target_labels for label in target_labels)

                if not valid_target:
                    primary_target_label = target_labels[0] if target_labels else "Unknown"
                    validation_errors.append(
                        {
                            "index": idx,
                            "from_uid": from_uid,
                            "to_uid": to_uid,
                            "relationship_type": rel_type,
                            "error": (
                                f"Invalid target: {source_label} --[{rel_type}]-> {primary_target_label}"
                            ),
                            "expected_targets": spec.target_labels,
                            "actual_target": primary_target_label,
                        }
                    )
                    continue

        # If ANY validation failed, return errors without creating relationships
        if validation_errors:
            from core.utils.result_simplified import ErrorCategory, ErrorContext, ErrorSeverity

            return Result.fail(
                ErrorContext(
                    category=ErrorCategory.VALIDATION,
                    code="VALIDATION_FIELD_RELATIONSHIPS",
                    message=f"Batch validation failed: {len(validation_errors)} invalid relationships",
                    severity=ErrorSeverity.LOW,
                    details={
                        "field": "relationships",
                        "total_relationships": len(relationships),
                        "validation_errors": validation_errors,
                        "error_count": len(validation_errors),
                    },
                    user_message="Invalid relationships in batch",
                    source_location=ErrorContext.capture_current_location(),
                )
            )

        # ========================================================================
        # BATCH CREATION (All validations passed)
        # ========================================================================
        # Uses BatchOperationHelper for pure Cypher query generation
        from core.infrastructure.batch import BatchOperationHelper

        # Generate queries grouped by relationship type
        queries = BatchOperationHelper.build_relationship_create_queries(relationships)

        total_created = 0
        async with self.driver.session() as session:
            for query, rels_data in queries:
                result = await session.run(query, {"rels": rels_data})
                record = await result.single()
                total_created += record["created_count"] if record else 0

        self.logger.info(f"Created {total_created} relationships in batch")
        return Result.ok(total_created)
