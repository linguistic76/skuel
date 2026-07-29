"""
CRUD Mixin
==========

CrudOperations[T] protocol implementation.

Provides:
    create: Create entity with auto-user OWNS relationship
    get: Get entity by UID
    get_or_fail: Get entity by UID, not-found as error Result
    get_many: Batch entity retrieval (N+1 prevention)
    update: Partial update with updated_at timestamp
    delete: Delete with optional cascade (DETACH DELETE)
    list: List entities with filters, pagination, sorting

Requires on concrete class:
    driver, logger, entity_class, label, default_filters, _create_labels,
    query_builder, prometheus_metrics, _track_db_metrics, _default_filter_clause,
    _default_filter_params, _inject_default_filters, _is_driver_closed,
    create_user_relationship
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, FilterParams, UserUID
from core.utils.error_boundary import safe_backend_operation
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver, Record

    from adapters.persistence.neo4j.query import UnifiedQueryBuilder
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics
    from core.models.enums.neo_labels import NeoLabel


class _CrudMixin[T: DomainModelProtocol]:
    """
    CrudOperations[T] — create, get, get_many, update, delete, list.

    Requires on concrete class:
        driver: AsyncDriver
        logger: logging.Logger
        entity_class: type[T]
        label: NeoLabel
        default_filters: FilterParams
        _create_labels: str
        query_builder: UnifiedQueryBuilder
        prometheus_metrics: PrometheusMetrics | None
        _track_db_metrics: method
        _default_filter_clause: method
        _default_filter_params: method
        _inject_default_filters: method
        _is_driver_closed: method
        create_user_relationship: async method (from _UserEntityMixin)
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
        entity_class: type[T]
        label: NeoLabel
        default_filters: FilterParams
        _create_labels: str
        query_builder: UnifiedQueryBuilder
        prometheus_metrics: PrometheusMetrics | None

        def _track_db_metrics(
            self, operation: str, duration: float, is_error: bool = False
        ) -> None: ...

        def _default_filter_clause(self, node_var: str = "n") -> str: ...

        def _default_filter_params(self) -> FilterParams: ...

        def _inject_default_filters(
            self,
            where_clauses: builtins.list[str],
            params: dict[str, Any],
            node_var: str = "n",
        ) -> None: ...

        def _is_driver_closed(self) -> bool: ...

        async def count(self, **filters: Any) -> Result[int]: ...

        async def create_user_relationship(
            self,
            user_uid: UserUID,
            entity_uid: EntityUID,
            relationship_type: RelationshipName | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> Result[bool]: ...

    # ============================================================================
    # UNIVERSAL CRUD - WORKS FOR ANY ENTITY TYPE
    # ============================================================================

    async def _create_node(
        self,
        entity: T,
        operation: str,
        match_clause: str = "",
        extra_cypher: str = "",
        params: dict[str, Any] | None = None,
        failure_message: str | None = None,
    ) -> Result[T]:
        """
        Shared body of create() and create_with_spawned_from().

        Serializes the entity, CREATEs the multi-label node, optionally wraps
        it with a caller-supplied MATCH prefix / extra Cypher (e.g. the
        SPAWNED_FROM edge), auto-creates the OWNS relationship when the entity
        carries a user_uid (warning-only on failure), and tracks metrics under
        ``operation``. Exceptions propagate to the callers'
        @safe_backend_operation decorators.
        """
        start_time = time.time()
        node_data = to_neo4j_node(entity)

        # Ensure default_filter properties are set on new nodes (e.g., entity_type)
        node_data.update(self.default_filters)

        # Extract user_uid if present (for auto-relationship creation)
        user_uid = node_data.get("user_uid")

        query = f"""
        {match_clause}
        CREATE (n:{self._create_labels})
        SET n = $props
        {extra_cypher}
        RETURN n
        """

        record = await self._run_single(query, {"props": node_data, **(params or {})})

        if not record:
            # Track error metrics
            self._track_db_metrics(operation, time.time() - start_time, is_error=True)
            return Result.fail(
                Errors.database(operation, failure_message or f"Failed to create {self.label}")
            )

        created = from_neo4j_node(dict(record["n"]), self.entity_class)

        # Auto-create user relationship if user_uid exists
        if user_uid:
            rel_result = await self.create_user_relationship(
                user_uid=user_uid,
                entity_uid=EntityUID(created.uid),
                relationship_type=RelationshipName.OWNS,
            )

            if rel_result.is_error:
                self.logger.warning(
                    f"Created {self.label} {created.uid} but failed to create user relationship: {rel_result.error}"
                )
                # Don't fail the entire create operation - entity was created successfully
            else:
                self.logger.debug(f"Auto-created OWNS relationship for {self.label} {created.uid}")

        # Track metrics
        self._track_db_metrics(operation, time.time() - start_time, is_error=False)

        return Result.ok(created)

    @safe_backend_operation("create")
    async def create(self, entity: T) -> Result[T]:
        """
        Create any entity type.

        AUTO-CREATES USER RELATIONSHIP: If entity has user_uid field,
        automatically creates (User)-[:OWNS]->(Entity) relationship.

        Multi-label CREATE: When base_label is set, creates nodes with
        dual labels: ``(n:Entity:Task)``.
        """
        return await self._create_node(entity, "create")

    @safe_backend_operation("create_with_spawned_from")
    async def create_with_spawned_from(self, entity: T, template_uid: str) -> Result[T]:
        """Create entity node + atomic ``(entity)-[:SPAWNED_FROM]->(template)`` edge.

        Used by the PsEngagement spawn orchestrator to write the graph-native
        back-reference from a spawned activity to the template that produced it
        — node and edge succeed or fail together in one Cypher transaction.
        There is no parallel ``template_uid`` property on the node; the edge
        is THE relationship.

        Like ``create()``, auto-creates ``(User)-[:OWNS]->(entity)`` if the
        entity carries a ``user_uid`` (warning-only on failure).
        """
        return await self._create_node(
            entity,
            "create_with_spawned_from",
            match_clause="MATCH (t {uid: $template_uid})",
            extra_cypher="CREATE (n)-[r:SPAWNED_FROM]->(t)\n        SET r.spawned_at = datetime()",
            params={"template_uid": template_uid},
            failure_message=f"Failed to create {self.label} or locate template {template_uid}",
        )

    @safe_backend_operation("get")
    async def get(self, uid: str) -> Result[T | None]:
        """
        Get any entity by UID.

        Retrieves a single entity from the Neo4j database by its unique identifier.
        Returns None if the entity does not exist.

        Args:
            uid: Unique identifier of the entity (e.g., "task:123", "event:456")

        Returns:
            Result[T | None]: Success with entity if found, Success with None if not found,
                             or Failure if database error occurs

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
            result = await backend.get("task:123")

            if result.is_ok:
                task = result.value
                if task:
                    print(f"Found task: {task.title}")
                else:
                    print("Task not found")
            else:
                print(f"Error: {result.error}")
            ```

        Note:
            - This method does NOT raise exceptions - all errors are wrapped in Result
            - Not found is NOT an error - returns Result.ok(None)
            - For batch retrieval, use get_many() to avoid N+1 queries
        """
        df_clause = self._default_filter_clause()
        where_line = f"WHERE {df_clause}" if df_clause else ""

        query = f"""
        MATCH (n:{self.label} {{uid: $uid}})
        {where_line}
        RETURN n
        """

        params: dict[str, Any] = {"uid": uid}
        params.update(self._default_filter_params())

        record = await self._run_single(query, params)

        if not record:
            return Result.ok(None)

        entity = from_neo4j_node(dict(record["n"]), self.entity_class)
        return Result.ok(entity)

    async def get_or_fail(self, uid: str) -> Result[T]:
        """
        Get an entity by UID, converting "not found" into an error Result.

        THE generic body behind the domain backends' get_task/get_goal/...
        wrappers (contrast with get(), where not-found is Result.ok(None)).
        The not-found resource name is the domain model class name.
        """
        get_result = await self.get(uid)
        if get_result.is_error:
            return Result.fail(get_result)
        if not get_result.value:
            return Result.fail(
                Errors.not_found(resource=self.entity_class.__name__, identifier=uid)
            )
        return Result.ok(get_result.value)

    @safe_backend_operation("get_many")
    async def get_many(self, uids: builtins.list[str]) -> Result[builtins.list[T | None]]:
        """
        Get multiple entities by UIDs in a single batched query.

        This method prevents N+1 query problems by fetching all requested
        entities in ONE database roundtrip using Neo4j's WHERE IN clause.

        Args:
            uids: List of entity UIDs to fetch

        Returns:
            Result[List[T]] with entities in the SAME ORDER as input UIDs.
            Missing entities are represented as None in the list to maintain
            position correspondence with the input UIDs (DataLoader requirement).

        Example:
            # Fetch 10 knowledge units in one query instead of 10 separate queries
            result = await backend.get_many([
                "ku.python.basics",
                "ku.python.functions",
                "ku.python.classes"
            ])
            # Returns list with 3 KnowledgeUnit objects in same order

        Performance:
            - 10 entities: 10 queries → 1 query (~10x faster)
            - 100 entities: 100 queries → 1 query (~100x faster)
        """
        if not uids:
            return Result.ok([])

        # Guard: Skip operation if driver is closed (test teardown)
        if self._is_driver_closed():
            return Result.ok([])

        df_clause = self._default_filter_clause()
        extra_where = f" AND {df_clause}" if df_clause else ""

        query = f"""
        MATCH (n:{self.label})
        WHERE n.uid IN $uids{extra_where}
        RETURN n
        """

        params: dict[str, Any] = {"uids": uids}
        params.update(self._default_filter_params())

        records = await self._run_records(query, params)

        # Create uid-to-entity map for fast lookup
        entity_map = {}
        for record in records:
            entity = from_neo4j_node(record["n"], self.entity_class)
            entity_map[entity.uid] = entity

        # Return entities in same order as input UIDs (DataLoader requirement)
        # Missing entities are None to maintain correspondence
        entities = [entity_map.get(uid) for uid in uids]

        self.logger.debug(
            f"Batched get_many: fetched {len(records)} of {len(uids)} {self.label} entities"
        )
        return Result.ok(entities)

    @safe_backend_operation("get_content")
    async def get_content(self, uid: str) -> Result[str | None]:
        """
        Get an entity's body content from its :Content node.

        Body content for chunked entity types (PathStep, Ku) lives on a
        separate ``(:Entity)-[:HAS_CONTENT]->(:Content)`` node, never as an
        entity property — ingestion pops the body pre-upsert (ADR-074). This
        is the read counterpart consumed by the
        ``ContextOperationsMixin.get_with_content`` inline-first fallback.

        Args:
            uid: Unique identifier of the entity

        Returns:
            Result[str | None]: the :Content node's body, or None when the
            entity has no content subtree (not an error).
        """
        query = f"""
        MATCH (n:{self.label} {{uid: $uid}})-[:HAS_CONTENT]->(c:Content)
        RETURN c.body AS body
        """

        record = await self._run_single(query, {"uid": uid})

        if not record:
            return Result.ok(None)
        return Result.ok(record["body"])

    @safe_backend_operation("update")
    async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]:
        """
        Update any entity by UID.

        Performs a partial update of an entity, modifying only the fields specified
        in the updates dictionary. Automatically sets updated_at timestamp.

        Args:
            uid: Unique identifier of the entity to update
            updates: Dictionary of field names to new values (partial update)

        Returns:
            Result[T]: Success with updated entity, or Failure if entity not found
                      or database error occurs

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Update specific fields
            result = await backend.update(
                "task:123",
                {
                    "status": "completed",
                    "priority": "high",
                    "completion_notes": "Finished ahead of schedule",
                },
            )

            if result.is_ok:
                task = result.value
                print(f"Updated task: {task.title}")
            ```

        Note:
            - Uses Neo4j's += operator for partial updates (preserves other fields)
            - Automatically adds updated_at timestamp
            - Returns error if entity doesn't exist (use get() first to check)
            - Empty updates dictionary returns validation error
        """
        start_time = time.time()

        if not updates:
            self._track_db_metrics("update", time.time() - start_time, is_error=True)
            return Result.fail(Errors.validation("No updates provided", field="updates"))

        # Add updated_at timestamp
        updates["updated_at"] = datetime.now().isoformat()

        # Prevent overwriting default_filter properties (e.g., entity_type)
        for k in self.default_filters:
            updates.pop(k, None)

        # Serialize complex types for Neo4j (dicts → JSON strings, enums → values, etc.)
        # This matches what to_neo4j_node() does for create(), closing the SoC gap
        # where services previously had to manually json.dumps() before calling update().
        updates = to_neo4j_node(updates)

        df_clause = self._default_filter_clause()
        where_line = f"WHERE {df_clause}" if df_clause else ""

        query = f"""
        MATCH (n:{self.label} {{uid: $uid}})
        {where_line}
        SET n += $updates
        RETURN n
        """

        params: dict[str, Any] = {"uid": uid, "updates": updates}
        params.update(self._default_filter_params())

        record = await self._run_single(query, params)

        if not record:
            self._track_db_metrics("update", time.time() - start_time, is_error=True)
            return Result.fail(Errors.not_found("resource", f"{self.label} {uid} not found"))

        updated = from_neo4j_node(dict(record["n"]), self.entity_class)

        # Track metrics
        self._track_db_metrics("update", time.time() - start_time, is_error=False)

        return Result.ok(updated)

    @safe_backend_operation("atomic_append_dual_track_checkin")
    async def atomic_append_dual_track_checkin(
        self, uid: str, snapshot: dict[str, Any], history_limit: int
    ) -> Result[bool]:
        """Atomically append a per-entity dual-track check-in snapshot (ADR-030).

        Node-lock-serialized so two near-simultaneous check-ins on the SAME entity
        can't lose a snapshot (the read-modify-write of the JSON ``dual_track_checkins``
        log runs under a Neo4j node write-lock). Replaces the former get()+update()
        read-modify-write in ``BaseAnalyticsService._store_dual_track_checkin``.

        Backend: ``_dual_track_checkin_store.atomic_append_checkin`` (flat list — the
        per-entity log has no dimension key).

        Args:
            uid: Entity UID.
            snapshot: ``DualTrackResult.to_checkin_snapshot`` dict.
            history_limit: Max snapshots retained (oldest dropped).

        Returns:
            Result[bool]: True if appended, NotFound if the entity does not exist.
        """
        from adapters.persistence.neo4j._dual_track_checkin_store import atomic_append_checkin

        appended = await atomic_append_checkin(
            self.driver,
            label=str(self.label),
            uid=uid,
            snapshot=snapshot,
            history_limit=history_limit,
        )
        if not appended:
            return Result.fail(Errors.not_found("resource", f"{self.label} {uid} not found"))
        return Result.ok(True)

    @safe_backend_operation("delete")
    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        Delete any entity by UID.

        Removes an entity from the Neo4j database. Optionally deletes all relationships
        (cascade=True) or requires manual relationship cleanup (cascade=False).

        Args:
            uid: Unique identifier of the entity to delete
            cascade: If True, deletes entity and all its relationships (DETACH DELETE).
                    If False, fails if entity has relationships (requires manual cleanup).

        Returns:
            Result[bool]: Success with True if deleted, False if not found,
                         or Failure if database error occurs (e.g., relationships exist)

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Delete with relationships (cascade)
            result = await backend.delete("task:123", cascade=True)

            if result.is_ok and result.value:
                print("Task and all relationships deleted")

            # Delete without relationships (fails if relationships exist)
            result = await backend.delete("task:456", cascade=False)
            ```

        Warning:
            - cascade=True deletes ALL relationships (incoming and outgoing)
            - cascade=False will fail if entity has any relationships
            - Deletion is permanent - no soft delete or recovery
            - Consider backing up data before cascade delete operations

        Note:
            - Returns True even if entity didn't exist (idempotent)
            - Use cascade=True for most deletions to avoid orphaned relationships
        """
        start_time = time.time()

        df_clause = self._default_filter_clause()
        where_line = f"WHERE {df_clause}" if df_clause else ""

        if cascade:
            # DETACH DELETE removes entity AND all relationships
            query = f"""
            MATCH (n:{self.label} {{uid: $uid}})
            {where_line}
            DETACH DELETE n
            RETURN count(n) as deleted
            """
        else:
            # DELETE only - intentionally fails if relationships exist (safety check).
            # Use cascade=True to remove relationships too.
            query = f"""
            MATCH (n:{self.label} {{uid: $uid}})
            {where_line}
            DELETE n // noqa: CYP002 - intentional: non-DETACH DELETE is the safety check
            RETURN count(n) as deleted
            """

        params: dict[str, Any] = {"uid": uid}
        params.update(self._default_filter_params())

        async with self.driver.session() as session:
            try:
                result = await session.run(query, params)
                summary = await result.consume()

                deleted = summary.counters.nodes_deleted > 0

                # Track metrics
                self._track_db_metrics("delete", time.time() - start_time, is_error=False)

                return Result.ok(deleted)
            except NEO4J_EXCEPTIONS as e:
                error_msg = str(e)
                # Neo4j constraint error when trying to delete node with relationships
                if "Cannot delete" in error_msg and "relationship" in error_msg.lower():
                    self._track_db_metrics("delete", time.time() - start_time, is_error=True)
                    return Result.fail(
                        Errors.business(
                            rule="delete_with_relationships",
                            message=f"Cannot delete {self.label} '{uid}' - has existing relationships. "
                            "Use cascade=True to delete with relationships.",
                        )
                    )
                # Track error for other exceptions
                self._track_db_metrics("delete", time.time() - start_time, is_error=True)
                raise

    @safe_backend_operation("list")
    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> Result[tuple[builtins.list[T], int]]:
        """
        List any entity type with dynamic filters.

        Now uses UnifiedQueryBuilder with fluent API.
        Add a field to your model → it's automatically filterable!

        Returns:
            Result[tuple[list[T], int]]: (page of entities, total matching count).
            The total ignores limit/offset so callers can paginate — it mirrors
            ``get_user_entities`` and is what every consumer + the protocol expect.
        """
        # Build query using UnifiedQueryBuilder fluent API
        # Pass label explicitly to ensure correct Neo4j label is used
        builder = (
            self.query_builder.for_model(self.entity_class, label=self.label)
            .limit(limit)
            .offset(offset)
        )

        # Inject default_filters for Ku-type discrimination
        if self.default_filters:
            builder = builder.filter(**self.default_filters)

        if filters:
            builder = builder.filter(**filters)

        if sort_by:
            builder = builder.order_by(sort_by, desc=(sort_order == "desc"))

        query, params = builder.build()

        records = await self._run_records(query, params)

        entities = [from_neo4j_node(r["n"], self.entity_class) for r in records]

        # Total count ignores pagination; count() re-applies default_filters itself.
        count_result = await self.count(**(filters or {}))
        if count_result.is_error:
            return Result.fail(count_result)

        return Result.ok((entities, count_result.value))
