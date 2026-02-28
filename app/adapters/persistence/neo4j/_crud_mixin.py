"""
CRUD Mixin
==========

CrudOperations[T] protocol implementation.

Provides:
    create: Create entity with auto-user OWNS relationship
    get: Get entity by UID
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

from core.models.protocols import DomainModelProtocol
from core.utils.error_boundary import safe_backend_operation
from core.utils.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver

    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics
    from core.models.query import UnifiedQueryBuilder


class _CrudMixin[T: DomainModelProtocol]:
    """
    CrudOperations[T] — create, get, get_many, update, delete, list.

    Requires on concrete class:
        driver: AsyncDriver
        logger: logging.Logger
        entity_class: type[T]
        label: str
        default_filters: dict[str, Any]
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
        logger: logging.Logger
        entity_class: type[T]
        label: str
        default_filters: dict[str, Any]
        _create_labels: str
        query_builder: UnifiedQueryBuilder
        prometheus_metrics: PrometheusMetrics | None

        def _track_db_metrics(
            self, operation: str, duration: float, is_error: bool = False
        ) -> None: ...

        def _default_filter_clause(self, node_var: str = "n") -> str: ...

        def _default_filter_params(self) -> dict[str, Any]: ...

        def _inject_default_filters(
            self,
            where_clauses: builtins.list[str],
            params: dict[str, Any],
            node_var: str = "n",
        ) -> None: ...

        def _is_driver_closed(self) -> bool: ...

        async def create_user_relationship(
            self,
            user_uid: str,
            entity_uid: str,
            relationship_type: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> Result[bool]: ...

    # ============================================================================
    # UNIVERSAL CRUD - WORKS FOR ANY ENTITY TYPE
    # ============================================================================

    @safe_backend_operation("create")
    async def create(self, entity: T) -> Result[T]:
        """
        Create any entity type.

        AUTO-CREATES USER RELATIONSHIP: If entity has user_uid field,
        automatically creates (User)-[:OWNS]->(Entity) relationship.

        Multi-label CREATE: When base_label is set, creates nodes with
        dual labels: ``(n:Entity:Task)``.
        """
        start_time = time.time()
        node_data = to_neo4j_node(entity)

        # Ensure default_filter properties are set on new nodes (e.g., ku_type)
        node_data.update(self.default_filters)

        # Extract user_uid if present (for auto-relationship creation)
        user_uid = node_data.get("user_uid")

        query = f"""
        CREATE (n:{self._create_labels})
        SET n = $props
        RETURN n
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"props": node_data})
            record = await result.single()

            if not record:
                # Track error metrics
                self._track_db_metrics("create", time.time() - start_time, is_error=True)
                return Result.fail(Errors.database("create", f"Failed to create {self.label}"))

            created = from_neo4j_node(dict(record["n"]), self.entity_class)

            # Auto-create user relationship if user_uid exists
            if user_uid:
                rel_result = await self.create_user_relationship(
                    user_uid=user_uid, entity_uid=created.uid, relationship_type="OWNS"
                )

                if rel_result.is_error:
                    self.logger.warning(
                        f"Created {self.label} {created.uid} but failed to create user relationship: {rel_result.error}"
                    )
                    # Don't fail the entire create operation - entity was created successfully
                else:
                    self.logger.debug(
                        f"Auto-created OWNS relationship for {self.label} {created.uid}"
                    )

            # Track metrics
            self._track_db_metrics("create", time.time() - start_time, is_error=False)

            return Result.ok(created)

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

        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()

            if not record:
                return Result.ok(None)

            entity = from_neo4j_node(dict(record["n"]), self.entity_class)
            return Result.ok(entity)

    @safe_backend_operation("get_many")
    async def get_many(self, uids: builtins.list[str]) -> Result[builtins.list[T]]:
        """
        Get multiple entities by UIDs in a single batched query.

        This method prevents N+1 query problems by fetching all requested
        entities in ONE database roundtrip using Neo4j's WHERE IN clause.

        **Critical for GraphQL DataLoader batching!**

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

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

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

        # Prevent overwriting default_filter properties (e.g., ku_type)
        for k in self.default_filters:
            updates.pop(k, None)

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

        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()

            if not record:
                self._track_db_metrics("update", time.time() - start_time, is_error=True)
                return Result.fail(Errors.not_found("resource", f"{self.label} {uid} not found"))

            updated = from_neo4j_node(dict(record["n"]), self.entity_class)

            # Track metrics
            self._track_db_metrics("update", time.time() - start_time, is_error=False)

            return Result.ok(updated)

    @safe_backend_operation("delete")
    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        DETACH DELETE any entity by UID.

        Removes an entity from the Neo4j database. Optionally deletes all relationships
        (cascade=True) or requires manual relationship cleanup (cascade=False).

        Args:
            uid: Unique identifier of the entity to DETACH DELETE
            cascade: If True, deletes entity and all its relationships (DETACH DELETE).
                    If False, fails if entity has relationships (requires manual cleanup).

        Returns:
            Result[bool]: Success with True if deleted, False if not found,
                         or Failure if database error occurs (e.g., relationships exist)

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # DETACH DELETE with relationships (cascade)
            result = await backend.DETACH DELETE("task:123", cascade=True)

            if result.is_ok and result.value:
                print("Task and all relationships deleted")

            # DETACH DELETE without relationships (fails if relationships exist)
            result = await backend.DETACH DELETE("task:456", cascade=False)
            ```

        Warning:
            - cascade=True deletes ALL relationships (incoming and outgoing)
            - cascade=False will fail if entity has any relationships
            - Deletion is permanent - no soft DETACH DELETE or recovery
            - Consider backing up data before cascade DETACH DELETE operations

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
            except Exception as e:
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
    ) -> Result[builtins.list[T]]:
        """
        List any entity type with dynamic filters.

        Now uses UnifiedQueryBuilder with fluent API.
        Add a field to your model → it's automatically filterable!
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

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

            entities = [from_neo4j_node(r["n"], self.entity_class) for r in records]
            return Result.ok(entities)
