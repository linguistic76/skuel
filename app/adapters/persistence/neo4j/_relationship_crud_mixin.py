"""
Relationship CRUD Mixin
=======================

Graph-native relationship creation, deletion, validation, and private helpers.

Provides:
    _extract_label_from_uid: Fast UID-to-label mapping
    _validate_relationship_pair: Shared registry-validation pipeline (single + batch)
    _build_direction_pattern: Build directional Cypher patterns
    _get_node_labels: Query node labels from database
    _batch_related: Shared UNWIND core of the batch_* relationship queries
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

from typing import TYPE_CHECKING, Any, Literal, Required, TypedDict

from adapters.persistence.neo4j._backend_helpers import direction_clause
from core.models.enums.neo_labels import NeoLabel
from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.models.type_hints import FilterParams
from core.utils.error_boundary import safe_backend_operation
from core.utils.result_simplified import ErrorCategory, ErrorContext, Errors, ErrorSeverity, Result

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver, Record

    from core.ports.base_protocols import Direction


class _PairDiagnosis(TypedDict, total=False):
    """Failure diagnosis from _validate_relationship_pair — kind + per-kind context."""

    kind: Required[Literal["no_source_label", "invalid_type", "invalid_target"]]
    source_label: str
    valid_types: list[str]
    actual_target: str
    expected_targets: list[str]


class _RelationshipCrudMixin[T: DomainModelProtocol]:
    """
    Relationship CRUD methods — create, delete, validate, count, check, batch.

    Requires on concrete class:
        driver: AsyncDriver
        logger: logging.Logger
        label: NeoLabel
        entity_class: type[T]
        default_filters: FilterParams
    """

    if TYPE_CHECKING:
        driver: AsyncDriver

        # Session-run chokepoint (Neo4jSessionRunner)
        async def _run_single(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Record | None: ...

        async def _run_records(
            self, query: str, params: dict[str, Any] | None = None
        ) -> list[dict[str, Any]]: ...

        logger: logging.Logger
        label: NeoLabel
        entity_class: type[T]
        default_filters: FilterParams

    # ============================================================================
    # GRAPH-NATIVE RELATIONSHIP API (October 26, 2025)
    # ============================================================================
    # Generic relationship methods for pure graph operations.
    # These eliminate the need for denormalized UID lists in domain models.

    def _extract_label_from_uid(self, uid: str) -> str | None:
        """
        Extract label from UID pattern (e.g., 'task:123' → 'Task').

        SKUEL uses consistent UID patterns: {domain}:{id} or {domain}.{id}.
        Fast pattern matching, no DB query needed.

        Args:
            uid: Entity UID (e.g., "task:123", "ku:python-basics")

        Returns:
            Label string if pattern matches, None otherwise (requires DB fallback)

        Examples:
            >>> backend._extract_label_from_uid("task:123")
            "Task"
            >>> backend._extract_label_from_uid("ku:python-basics")
            "Ku"
            >>> backend._extract_label_from_uid("unknown:xyz")
            None
        """
        # Common UID patterns in SKUEL
        # Ingestion accepts both ':' and '.' separators (validator.py normalizes).
        patterns = {
            "task:": "Task",
            "event:": "Event",
            "habit:": "Habit",
            "goal:": "Goal",
            "principle:": "Principle",
            "choice:": "Choice",
            "ku:": "Ku",
            "ku.": "Ku",
            "ps:": "PathStep",
            "ps.": "PathStep",
            "lp:": "LearningPath",
            "lp.": "LearningPath",
            "ex:": "Exercise",
            "ex.": "Exercise",
            "user.": "User",
            "ue_": "UserEntry",  # ADR-054 unified user-authored content
        }

        for prefix, label in patterns.items():
            if uid.startswith(prefix):
                return label

        return None  # Fallback to DB query

    @staticmethod
    def _pick_domain_label(labels: builtins.list[str]) -> str | None:
        """
        Pick the domain-specific label from a multi-label node.

        SKUEL domain entities use multi-label CREATE — e.g. ``(n:Entity:Ku)`` —
        and ``labels(n)`` returns them in unspecified order. The relationship
        registry (``LABEL_CONFIGS``) is keyed by domain-specific labels only;
        the universal ``:Entity`` base label has no entry. So when the
        validator falls back to DB labels, it must skip ``"Entity"`` to find
        the label that actually keys the registry.
        """
        for label in labels:
            if label != NeoLabel.ENTITY.value:
                return label
        return labels[0] if labels else None

    def _validate_relationship_pair(
        self,
        from_uid: str,
        rel_type: RelationshipName | str,
        source_labels: builtins.list[str],
        target_labels: builtins.list[str],
    ) -> _PairDiagnosis | None:
        """
        Registry-validate one (source, target, relationship-type) triple.

        THE shared pipeline behind create_relationship and
        create_relationships_batch — source-label extraction (UID parse with
        DB-label fallback), relationship-type registry check, and target-label
        check. The label *fetch* stays with the callers (single vs batched
        query); this helper only consumes the fetched labels.

        Returns:
            None when the pair is valid, else a diagnosis dict with a
            ``"kind"`` key (``no_source_label`` | ``invalid_type`` |
            ``invalid_target``) plus the context each caller needs to build
            its own error surface.
        """
        from core.models.relationship_registry import (
            get_relationship_metadata,
            get_valid_relationships,
            validate_relationship,
        )

        # Step 1: Extract source label (fast UID parsing, DB-label fallback —
        # skipping the universal :Entity base label)
        source_label = self._extract_label_from_uid(from_uid) or self._pick_domain_label(
            source_labels
        )
        if not source_label:
            return {"kind": "no_source_label"}

        # Step 3: Validate relationship type for source domain
        if not validate_relationship(source_label, rel_type):
            return {
                "kind": "invalid_type",
                "source_label": source_label,
                "valid_types": list(get_valid_relationships(source_label).keys()),
            }

        # Step 4: Validate target node label against the registry spec
        spec = get_relationship_metadata(source_label, rel_type)
        if (
            spec
            and spec.target_labels
            and not any(label in spec.target_labels for label in target_labels)
        ):
            return {
                "kind": "invalid_target",
                "source_label": source_label,
                "actual_target": self._pick_domain_label(target_labels) or "Unknown",
                "expected_targets": spec.target_labels,
            }

        return None

    @staticmethod
    def _pair_diagnosis_to_error(
        diagnosis: _PairDiagnosis,
        from_uid: str,
        relationship_type: RelationshipName,
        target_labels: builtins.list[str],
    ) -> ErrorContext:
        """Map a _validate_relationship_pair diagnosis to create_relationship's error surface."""
        if diagnosis["kind"] == "no_source_label":
            return Errors.validation(
                message=f"Unable to determine source label for UID: {from_uid}",
                field="from_uid",
                value=from_uid,
            )

        if diagnosis["kind"] == "invalid_type":
            source_label = diagnosis["source_label"]
            valid_types = diagnosis["valid_types"]
            return ErrorContext(
                category=ErrorCategory.VALIDATION,
                code="VALIDATION_FIELD_RELATIONSHIP_TYPE",
                message=(
                    f"Invalid relationship type '{relationship_type}' for {source_label}. "
                    f"Valid types: {valid_types}"
                ),
                severity=ErrorSeverity.LOW,
                details={
                    "field": "relationship_type",
                    "value": relationship_type,
                    "source_label": source_label,
                    "source_uid": from_uid,
                    "valid_relationship_types": valid_types,
                },
                user_message=f"Invalid relationship type '{relationship_type}'",
                source_location=ErrorContext.capture_current_location(),
            )

        # invalid_target
        return ErrorContext(
            category=ErrorCategory.VALIDATION,
            code="VALIDATION_FIELD_TARGET_LABEL",
            message=(
                f"Invalid target label for relationship: "
                f"{diagnosis['source_label']} --[{relationship_type}]-> "
                f"{diagnosis['actual_target']}. "
                f"Expected target labels: {diagnosis['expected_targets']}"
            ),
            severity=ErrorSeverity.LOW,
            details={
                "field": "target_label",
                "value": diagnosis["actual_target"],
                "source_label": diagnosis["source_label"],
                "target_labels": target_labels,
                "expected_target_labels": diagnosis["expected_targets"],
                "relationship_type": relationship_type,
            },
            user_message=f"Invalid target type for {relationship_type} relationship",
            source_location=ErrorContext.capture_current_location(),
        )

    def _build_direction_pattern(
        self,
        relationship_type: RelationshipName,
        direction: Direction,
        source_var: str = "n",
        target_var: str = "related",
        rel_var: str | None = None,
        target_label: NeoLabel | None = None,
    ) -> Result[str]:
        """
        Build Cypher pattern for directional relationship traversal.

        Consolidates repeated pattern building across:
        - get_related_entities() (with target label)
        - get_related_uids() (with relationship variable)
        - count_related() (with relationship variable)

        Args:
            relationship_type: The relationship type (RelationshipName enum)
            direction: Traversal direction ("outgoing", "incoming", or "both")
            source_var: Variable name for source node (default: "n")
            target_var: Variable name for target node (default: "related")
            rel_var: Optional relationship variable name (e.g., "r" for property access)
            target_label: Optional label constraint on target node

        Returns:
            Result[str] containing the Cypher pattern or validation error

        Examples:
            >>> backend._build_direction_pattern(RelationshipName.OWNS, "outgoing")
            Result.ok("(n)-[:OWNS]->(related)")

            >>> backend._build_direction_pattern(
            ...     RelationshipName.REQUIRES_PREREQUISITE, "incoming", rel_var="r"
            ... )
            Result.ok("(n)<-[r:REQUIRES_PREREQUISITE]-(related)")

            >>> backend._build_direction_pattern(
            ...     RelationshipName.OWNS, "outgoing", target_label="Task"
            ... )
            Result.ok("(n)-[:OWNS]->(related:Task)")
        """
        from core.utils.validation_helpers import validate_relationship_type

        # Defense-in-depth: the RelationshipName type already guarantees a valid,
        # injection-safe value; this runtime check is a belt-and-suspenders safety net.
        if not validate_relationship_type(relationship_type):
            return Result.fail(
                Errors.validation(
                    message=f"Invalid relationship type: {relationship_type}",
                    field="relationship_type",
                )
            )

        # Build target part: (related) or (related:Label)
        target_part = f"({target_var}:{target_label})" if target_label else f"({target_var})"

        try:
            arrow = direction_clause(direction, rel_var, str(relationship_type))
        except ValueError as e:
            return Result.fail(
                Errors.validation(message=str(e), field="direction", value=direction)
            )
        return Result.ok(f"({source_var}){arrow}{target_part}")

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
        # NOT :Content — the chunk store's shadow node shares its entity's uid;
        # an unguarded uid MATCH would read the shadow's labels here and wrong
        # validation would follow (G13). Endpoints may be User/Group (non-
        # :Entity), so exclusion — not :Entity binding — is the guard.
        query = """
        MATCH (a {uid: $from_uid}) WHERE NOT a:Content
        MATCH (b {uid: $to_uid}) WHERE NOT b:Content
        RETURN labels(a) as source_labels, labels(b) as target_labels
        """

        record = await self._run_single(query, {"from_uid": from_uid, "to_uid": to_uid})

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

    @safe_backend_operation("get_node_labels_batch")
    async def _get_node_labels_batch(
        self, uids: builtins.list[str]
    ) -> Result[dict[str, builtins.list[str]]]:
        """
        Query labels for many nodes in ONE query (batch sibling of _get_node_labels).

        Returns a uid -> labels map; UIDs with no matching node are simply
        absent from the map — callers decide whether that is an error.
        """
        # NOT :Content — same G13 shadow-uid guard as _get_node_labels.
        query = """
        UNWIND $uids AS uid
        MATCH (n {uid: uid}) WHERE NOT n:Content
        RETURN uid, labels(n) AS labels
        """

        records = await self._run_records(query, {"uids": uids})

        return Result.ok({record["uid"]: record["labels"] for record in records})

    @safe_backend_operation("get_owner_uids_batch")
    async def get_owner_uids_batch(
        self, uids: builtins.list[str]
    ) -> Result[dict[str, builtins.list[str]]]:
        """Owners of each node, for many nodes in ONE query (uid -> owning user UIDs).

        For callers that turn user-supplied UIDs into edges: the other end of an edge is
        request input, so a create path that trusts it will happily link one user's
        entity to another's.

        Ownership is spelled THREE ways in this graph, and reading only one of them is
        how a check like that leaks:

        - ``n.user_uid`` — ``UserOwnedEntity`` (the 6 activity domains, UserEntry, ...)
        - ``n.owner_uid`` — ``Exercise`` and ``Group``, which are NOT UserOwnedEntity;
          a PERSONAL exercise read through ``user_uid`` alone looks unowned
        - ``(:User)-[:OWNS]->(n)`` — the canonical edge, written for exercises, revised
          exercises, form submissions, feedback and groups

        Only nodes with at least one of the three appear in the map. Genuinely shared
        content — Ku, PathStep, LearningPath — has no ownership property and is reached
        by no OWNS edge, so it is simply absent, the same convention
        ``_get_node_labels_batch`` uses for missing nodes. That absence is meaningful,
        not a gap: it lets a caller express "must match if owned, allowed if shared"
        without hand-listing which entity types are user-owned — a list that would
        silently rot as types are added, which is exactly how the ``owner_uid`` family
        was missed the first time.

        A list rather than one value because ownership is asked as a MEMBERSHIP question:
        the caller must be among the owners, not equal to whichever spelling was read
        first.
        """
        # NOT :Content — same G13 shadow-uid guard as _get_node_labels_batch.
        query = """
        UNWIND $uids AS uid
        MATCH (n {uid: uid}) WHERE NOT n:Content
        OPTIONAL MATCH (owner:User)-[:OWNS]->(n)
        WITH uid, n, collect(DISTINCT owner.uid) AS owns_uids
        WITH uid, [o IN owns_uids + [n.user_uid, n.owner_uid] WHERE o IS NOT NULL] AS owners
        WHERE size(owners) > 0
        RETURN uid, owners
        """

        records = await self._run_records(query, {"uids": uids})

        return Result.ok({record["uid"]: list(record["owners"]) for record in records})

    @safe_backend_operation("create_relationship")
    async def create_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
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
            relationship_type: Neo4j relationship type (RelationshipName enum)
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
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            )
            # ✅ Task -> Knowledge is valid per registry

            # Invalid relationship - fails validation
            result = await backend.create_relationship(
                from_uid="task:123",
                to_uid="habit:exercise",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
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
        # ========================================================================
        # C: VALIDATION (Hard Failures)
        # ========================================================================

        # Step 2: Get node labels from database (existence check + validation input)
        labels_result = await self._get_node_labels(from_uid, to_uid)
        if labels_result.is_error:
            return Result.fail(labels_result)  # Nodes don't exist

        source_labels: builtins.list[str]
        target_labels: builtins.list[str]
        source_labels, target_labels = labels_result.value

        # Steps 1/3/4: shared registry-validation pipeline
        diagnosis = self._validate_relationship_pair(
            from_uid, relationship_type, source_labels, target_labels
        )
        if diagnosis is not None:
            return Result.fail(
                self._pair_diagnosis_to_error(diagnosis, from_uid, relationship_type, target_labels)
            )

        # Note: Property validation and cardinality constraints were removed in January 2026
        # during the RelationshipRegistry migration. The new registry focuses on
        # essential validation (relationship type + target labels). Add cardinality
        # constraints to UnifiedRelationshipDefinition if needed in the future.

        # ========================================================================
        # RELATIONSHIP CREATION (All Validation Passed)
        # ========================================================================

        props = properties or {}

        # NOT :Content — same G13 shadow-uid guard as _get_node_labels: an
        # unguarded MERGE would create the edge to BOTH the entity and its
        # chunk-store shadow (the doubled-INTERACTION_DURING bug class).
        query = f"""
        MATCH (a {{uid: $from_uid}}) WHERE NOT a:Content
        MATCH (b {{uid: $to_uid}}) WHERE NOT b:Content
        MERGE (a)-[r:{relationship_type}]->(b)
        SET r += $properties
        RETURN r
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, {"from_uid": from_uid, "to_uid": to_uid, "properties": props}
            )
            await result.single()

        self.logger.debug(f"Created relationship: {from_uid} --[{relationship_type}]-> {to_uid}")
        return Result.ok(True)

    @safe_backend_operation("create_extracted_from_links")
    async def create_extracted_from_links(
        self, entry_uid: str, links: builtins.list[tuple[str, str, str | None]]
    ) -> Result[int]:
        """
        Batch-write DSL extraction provenance edges (ADR-069, ADR-070).

        Writes ``(created)-[:EXTRACTED_FROM {extracted_at, source_line_hash,
        vault_id}]->(entry)`` for each ``(created_uid, line_hash, vault_id)``
        triple. ``vault_id`` is the obsidian-tasks 🆔 join key (ADR-070); None
        for @context() DSL lines. Dedicated writer rather than
        ``create_relationship``: the source label is whichever entity the DSL
        line produced (Task, Habit, Ku, ...), so routing through registry
        validation would force registering provenance into every domain config.
        MERGE keeps re-runs idempotent; ``extracted_at`` is set server-side as a
        native Cypher datetime.

        Args:
            entry_uid: Source UserEntry UID the entities were extracted from
            links: ``(created_uid, source_line_hash, vault_id)`` triples

        Returns:
            Result[int]: number of provenance edges now present for the pairs
        """
        if not links:
            return Result.ok(0)

        query = """
        MATCH (entry:UserEntry {uid: $entry_uid})
        UNWIND $links AS link
        MATCH (e:Entity {uid: link.uid})
        MERGE (e)-[r:EXTRACTED_FROM]->(entry)
        ON CREATE SET r.extracted_at = datetime()
        SET r.source_line_hash = link.line_hash,
            r.vault_id = link.vault_id
        RETURN count(r) AS link_count
        """
        params = {
            "entry_uid": entry_uid,
            "links": [
                {"uid": uid, "line_hash": line_hash, "vault_id": vault_id}
                for uid, line_hash, vault_id in links
            ],
        }

        record = await self._run_single(query, params)
        link_count = int(record["link_count"]) if record else 0

        if link_count < len(links):
            self.logger.warning(
                f"EXTRACTED_FROM provenance: wrote {link_count}/{len(links)} edges "
                f"for entry {entry_uid} (missing created nodes?)"
            )
        return Result.ok(link_count)

    @safe_backend_operation("update_extracted_from_vault_id")
    async def update_extracted_from_vault_id(
        self, entry_uid: str, entity_uid: str, vault_id: str
    ) -> Result[None]:
        """Set vault_id on an existing EXTRACTED_FROM edge (ADR-070 ID injection).

        Called by VaultReconciler after injecting a 🆔 token into a vault file
        for a task that was initially created without one.

        Args:
            entry_uid: UserEntry UID (target of EXTRACTED_FROM)
            entity_uid: Extracted entity UID (source of EXTRACTED_FROM)
            vault_id: The injected 🆔 ID (e.g. ``sk_abc123``)
        """
        query = """
        MATCH (e:Entity {uid: $entity_uid})-[r:EXTRACTED_FROM]->(entry:UserEntry {uid: $entry_uid})
        SET r.vault_id = $vault_id
        RETURN count(r) AS updated
        """
        record = await self._run_single(
            query,
            {"entity_uid": entity_uid, "entry_uid": entry_uid, "vault_id": vault_id},
        )
        if not record or int(record["updated"]) == 0:
            self.logger.warning(
                f"update_extracted_from_vault_id: no EXTRACTED_FROM edge {entity_uid} → {entry_uid}"
            )
        return Result.ok(None)

    @safe_backend_operation("delete_relationship")
    async def delete_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[bool]:
        """
        Delete a graph relationship between two entities.

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
        # NOT :Content — G13 shadow-uid guard (see create_relationship).
        query = f"""
        MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
        WHERE NOT a:Content AND NOT b:Content
        DELETE r
        RETURN count(r) as deleted_count
        """

        record = await self._run_single(query, {"from_uid": from_uid, "to_uid": to_uid})
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
        from adapters.persistence.neo4j.batch_cypher_builder import BatchCypherBuilder

        if not relationships:
            return Result.ok(0)

        # Use BatchCypherBuilder for query generation
        query_result = BatchCypherBuilder.build_relationship_delete_query(relationships)

        record = await self._run_single(query_result.query, query_result.params)
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
        # NOT :Content — G13 shadow-uid guard (see create_relationship).
        query = f"""
        MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
        WHERE NOT a:Content AND NOT b:Content
        RETURN count(r) > 0 as exists
        """

        record = await self._run_single(query, {"from_uid": from_uid, "to_uid": to_uid})
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

            # Count a goal's essential habits (incoming SUPPORTS_GOAL, filtered by tier)
            essential_count = await backend.count_related(
                uid="goal:fitness",
                relationship_type=RelationshipName.SUPPORTS_GOAL,
                direction="incoming",
                properties={"essentiality": "essential"}
            )
            print(f"Goal has {essential_count.value} essential habits")
        """
        # Build Cypher pattern using helper (with named relationship variable for property access)
        pattern_result = self._build_direction_pattern(
            relationship_type=relationship_type,
            direction=direction,
            rel_var="r",
        )
        if pattern_result.is_error:
            return Result.fail(pattern_result)
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

        # NOT :Content — G13 shadow-uid guard (see create_relationship).
        query = f"""
        MATCH (n {{uid: $uid}})
        WHERE NOT n:Content
        MATCH {pattern}
        {where_clause}
        RETURN count(related) as count
        """

        record = await self._run_single(query, params)
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
        if not relationships:
            return Result.ok(0)

        # ========================================================================
        # C: BATCH VALIDATION (Validate ALL before creating ANY)
        # ========================================================================

        validation_errors = []

        # Step 2 (batched): labels for every endpoint in ONE query
        all_uids = sorted(
            {uid for from_uid, to_uid, _rel, _props in relationships for uid in (from_uid, to_uid)}
        )
        labels_map_result = await self._get_node_labels_batch(all_uids)
        if labels_map_result.is_error:
            return Result.fail(labels_map_result)
        labels_map = labels_map_result.value

        for idx, (from_uid, to_uid, rel_type, _props) in enumerate(relationships):
            # Note: _props intentionally unused - property validation not yet implemented
            # Step 2: Look up node labels from the batched map
            source_labels = labels_map.get(from_uid)
            target_labels = labels_map.get(to_uid)
            if source_labels is None or target_labels is None:
                missing = [uid for uid in (from_uid, to_uid) if uid not in labels_map]
                validation_errors.append(
                    {
                        "index": idx,
                        "from_uid": from_uid,
                        "to_uid": to_uid,
                        "relationship_type": rel_type,
                        "error": "Nodes not found",
                        "details": f"Node(s) not found: {', '.join(missing)}",
                    }
                )
                continue

            # Steps 1/3/4: shared registry-validation pipeline
            diagnosis = self._validate_relationship_pair(
                from_uid, rel_type, source_labels, target_labels
            )
            if diagnosis is None:
                continue

            entry: dict[str, Any] = {"index": idx, "from_uid": from_uid}
            if diagnosis["kind"] == "no_source_label":
                entry["error"] = "Unable to determine source label"
            elif diagnosis["kind"] == "invalid_type":
                entry.update(
                    {
                        "to_uid": to_uid,
                        "relationship_type": rel_type,
                        "error": (
                            f"Invalid relationship type '{rel_type}' "
                            f"for {diagnosis['source_label']}"
                        ),
                        "valid_types": diagnosis["valid_types"],
                    }
                )
            else:  # invalid_target
                entry.update(
                    {
                        "to_uid": to_uid,
                        "relationship_type": rel_type,
                        "error": (
                            f"Invalid target: {diagnosis['source_label']} "
                            f"--[{rel_type}]-> {diagnosis['actual_target']}"
                        ),
                        "expected_targets": diagnosis["expected_targets"],
                        "actual_target": diagnosis["actual_target"],
                    }
                )
            validation_errors.append(entry)

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
        # Uses BatchCypherBuilder for pure Cypher query generation
        from adapters.persistence.neo4j.batch_cypher_builder import BatchCypherBuilder

        # Generate queries grouped by relationship type
        queries = BatchCypherBuilder.build_relationship_create_queries(relationships)

        total_created = 0
        async with self.driver.session() as session:
            for query, rels_data in queries:
                result = await session.run(query, {"rels": rels_data})
                record = await result.single()
                total_created += record["created_count"] if record else 0

        self.logger.info(f"Created {total_created} relationships in batch")
        return Result.ok(total_created)

    # ============================================================================
    # CONFIG-DRIVEN BATCH RELATIONSHIP QUERIES
    # ============================================================================
    # Used by UnifiedRelationshipService's BatchOperationsMixin.
    # Entity label and relationship type come from DomainRelationshipConfig.

    async def _batch_related(
        self,
        entity_label: NeoLabel,
        entity_uids: builtins.list[str],
        relationship_type: str,
        direction: str,
        return_clause: str,
    ) -> builtins.list[dict[str, Any]]:
        """
        Shared UNWIND core behind the three batch_* relationship queries.

        The public wrappers (batch_has_relationship / batch_count_related /
        batch_get_related_uids) differ only in their RETURN line — pass it as
        ``return_clause``. Exceptions propagate to the wrappers'
        @safe_backend_operation decorators.
        """
        query = f"""
        UNWIND $entity_uids AS entity_uid
        MATCH (e:{entity_label} {{uid: entity_uid}})
        OPTIONAL MATCH (e){direction_clause(direction)}(related)
        WHERE type(r) = $relationship_type
        RETURN entity_uid, {return_clause}
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {"entity_uids": entity_uids, "relationship_type": relationship_type},
            )
            return [dict(record) async for record in result]

    @safe_backend_operation("batch_has_relationship")
    async def batch_has_relationship(
        self,
        entity_label: NeoLabel,
        entity_uids: builtins.list[str],
        relationship_type: str,
        direction: str,
    ) -> Result[dict[str, bool]]:
        """
        Check relationship existence for multiple entities in a single query.

        Args:
            entity_label: Label of the source entity nodes
            entity_uids: List of entity UIDs to check
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"

        Returns:
            Result[dict[str, bool]] mapping uid -> has_relationship
        """
        if not entity_uids:
            return Result.ok({})

        records = await self._batch_related(
            entity_label,
            entity_uids,
            relationship_type,
            direction,
            "count(related) > 0 AS has_relationship",
        )
        return Result.ok({str(r["entity_uid"]): r.get("has_relationship", False) for r in records})

    @safe_backend_operation("batch_count_related")
    async def batch_count_related(
        self,
        entity_label: NeoLabel,
        entity_uids: builtins.list[str],
        relationship_type: str,
        direction: str,
    ) -> Result[dict[str, int]]:
        """
        Count related entities for multiple entities in a single query.

        Args:
            entity_label: Label of the source entity nodes
            entity_uids: List of entity UIDs to check
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"

        Returns:
            Result[dict[str, int]] mapping uid -> count
        """
        if not entity_uids:
            return Result.ok({})

        records = await self._batch_related(
            entity_label, entity_uids, relationship_type, direction, "count(related) AS count"
        )
        return Result.ok({str(r["entity_uid"]): r.get("count", 0) for r in records})

    @safe_backend_operation("batch_get_related_uids")
    async def batch_get_related_uids(
        self,
        entity_label: NeoLabel,
        entity_uids: builtins.list[str],
        relationship_type: str,
        direction: str,
    ) -> Result[dict[str, builtins.list[str]]]:
        """
        Get related entity UIDs for multiple entities in a single query.

        Args:
            entity_label: Label of the source entity nodes
            entity_uids: List of entity UIDs to query
            relationship_type: Neo4j relationship type string
            direction: "outgoing", "incoming", or "both"

        Returns:
            Result[dict[str, list[str]]] mapping entity_uid -> list of related UIDs
        """
        if not entity_uids:
            return Result.ok({})

        records = await self._batch_related(
            entity_label,
            entity_uids,
            relationship_type,
            direction,
            "collect(related.uid) AS related_uids",
        )
        return Result.ok(
            {
                str(r["entity_uid"]): [
                    uid for uid in (r.get("related_uids") or []) if uid is not None
                ]
                for r in records
            }
        )
