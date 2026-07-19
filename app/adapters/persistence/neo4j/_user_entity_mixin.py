"""
User Entity Mixin
=================

Generic user-entity relationship tracking for all UniversalNeo4jBackend instances.

Provides:
    create_user_relationship: Create (User)-[rel]->(Entity) edge
    get_user_entities: Get user's entities via relationship traversal
    list_by_user: Flat (unpaginated) user-entity list
    count_user_entities: Count user's entities
    update_relationship_access: Increment access_count + last_accessed
    delete_user_relationship: Remove user-entity relationship

Requires on concrete class:
    driver, logger, label, entity_class, _inject_default_filters
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID
from core.utils.error_boundary import safe_backend_operation
from core.utils.result_simplified import Errors, Result
from core.utils.validation_helpers import validate_field_name

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver, Record

    from core.models.enums.neo_labels import NeoLabel


class _UserEntityMixin[T: DomainModelProtocol]:
    """
    Generic user-entity relationship tracking for all entity backends.

    Provides the 5 core user-entity relationship methods that belong on
    every UniversalNeo4jBackend[T] instance, regardless of domain.

    Requires on concrete class:
        driver: AsyncDriver
        logger: logging.Logger
        label: NeoLabel
        entity_class: type[T]
        _inject_default_filters: method (from shell)
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

        def _inject_default_filters(
            self,
            where_clauses: builtins.list[str],
            params: dict[str, Any],
            node_var: str = "n",
        ) -> None: ...

        async def get(self, uid: str) -> Result[T | None]: ...

        async def create(self, entity: T) -> Result[T]: ...

        async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]: ...

        async def delete(self, uid: str, cascade: bool = False) -> Result[bool]: ...

    # ============================================================================
    # USER-ENTITY RELATIONSHIP TRACKING (October 16, 2025)
    # ============================================================================
    # Complete User Tracking Across All Domains
    #
    # These methods enable tracking of user-entity relationships for ALL domains:
    # tasks, events, habits, goals, choices, principles, journals, finance, etc.
    #
    # Auto-creates (User)-[:HAS_X]->(Entity) when entities are created with user_uid.
    # Provides query methods for user-specific entity filtering and statistics.

    def _build_user_entity_filters(
        self,
        user_uid: UserUID,
        filters: dict[str, Any] | None,
        base_params: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build the WHERE clause + params shared by get_user_entities and
        count_user_entities: default filters (Ku-type discrimination) plus
        identifier-validated caller filters on the ``e`` node variable.
        """
        filter_clauses: builtins.list[str] = []
        params: dict[str, Any] = {"user_uid": user_uid, **(base_params or {})}

        # Inject default_filters for Ku-type discrimination
        self._inject_default_filters(filter_clauses, params, node_var="e")

        if filters:
            for key, value in filters.items():
                if not validate_field_name(key):
                    self.logger.warning(f"Skipping invalid filter key: {key!r}")
                    continue
                filter_clauses.append(f"e.{key} = ${key}")
                params[key] = value

        where_clause = f"WHERE {' AND '.join(filter_clauses)}" if filter_clauses else ""
        return where_clause, params

    @safe_backend_operation("create_user_relationship")
    async def create_user_relationship(
        self,
        user_uid: UserUID,
        entity_uid: EntityUID,
        relationship_type: RelationshipName | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Create user-entity relationship.

        This method is called automatically when entities are created with user_uid.
        Can also be called manually to create additional relationship types.

        Args:
            user_uid: User UID,
            entity_uid: Entity UID,
            relationship_type: Neo4j relationship type. Defaults to OWNS.
            metadata: Optional edge properties (created_at, last_accessed, priority, etc.)

        Returns:
            Result[bool] indicating success

        Example:
            # Automatically called by create() when entity has user_uid
            await backend.create_user_relationship(
                user_uid="user_123",
                entity_uid="task_456",
                relationship_type=RelationshipName.OWNS,
                metadata={"priority": "high", "created_at": datetime.now().isoformat()}
            )
        """
        # Default relationship type: OWNS (domain-first architecture). The
        # RelationshipName type is the injection-safety guarantee — no runtime
        # validation needed before the interpolation below.
        if relationship_type is None:
            relationship_type = RelationshipName.OWNS

        # Default metadata
        default_metadata = {
            "created_at": datetime.now().isoformat(),
            "last_accessed": datetime.now().isoformat(),
            "access_count": 0,
            "is_active": True,
        }

        # Merge with provided metadata
        props = {**default_metadata, **(metadata or {})}

        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (e:{self.label} {{uid: $entity_uid}})
        MERGE (u)-[r:{relationship_type}]->(e)
        SET r = $props
        RETURN r
        """

        record = await self._run_single(
            query, {"user_uid": user_uid, "entity_uid": entity_uid, "props": props}
        )

        if not record:
            return Result.fail(
                Errors.database(
                    "create_user_relationship",
                    f"Failed to create relationship: User {user_uid} or {self.label} {entity_uid} not found",
                )
            )

        self.logger.info(
            f"Created user relationship: {user_uid} --[{relationship_type}]-> {entity_uid}"
        )
        return Result.ok(True)

    @safe_backend_operation("get_user_entities")
    async def get_user_entities(
        self,
        user_uid: UserUID,
        relationship_type: RelationshipName | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        sort_order: str = "desc",
    ) -> Result[tuple[builtins.list[T], int]]:
        """
        Get all entities for a user via relationship traversal.

        This is the PRIMARY method for user-specific entity queries.
        Replaces property-based filtering with graph relationship traversal.

        Args:
            user_uid: User UID,
            relationship_type: Optional relationship type filter (e.g., "HAS_TASK")
                              If None, uses default "HAS_{LABEL}" pattern
            filters: Optional filters on entity properties (status, priority, etc.),
            limit: Max results,
            offset: Pagination offset,
            sort_by: Field to sort by (default: created_at),
            sort_order: "asc" or "desc" (default: desc)

        Returns:
            Result[tuple[list[T], int]]: Tuple of (entities, total_count) for pagination

        Example:
            # Get all user's tasks
            result = await tasks_backend.get_user_entities("user_123")

            # Get only active tasks, sorted by due date
            result = await tasks_backend.get_user_entities(
                "user_123",
                filters={"status": "active"},
                sort_by="due_date",
                sort_order="asc"
            )

            # Get user's high-priority goals
            result = await goals_backend.get_user_entities(
                "user_123",
                filters={"priority": "high"}, limit=QueryLimit.PREVIEW
            )
        """
        # Default relationship type: OWNS (domain-first architecture). The
        # RelationshipName type is the injection-safety guarantee — no runtime
        # validation needed before interpolation.
        if relationship_type is None:
            relationship_type = RelationshipName.OWNS

        where_clause, params = self._build_user_entity_filters(
            user_uid, filters, base_params={"limit": limit, "offset": offset}
        )

        # Default sort field — validate to prevent injection
        if not sort_by or not validate_field_name(sort_by):
            if sort_by:
                self.logger.warning(
                    f"Invalid sort_by rejected, falling back to created_at: {sort_by!r}"
                )
            sort_by = "created_at"

        # Sort direction
        order_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{relationship_type}]->(e:{self.label})
        {where_clause}
        RETURN e
        ORDER BY e.{sort_by} {order_direction}
        SKIP $offset
        LIMIT $limit
        """

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = [record async for record in result]

        entities = [from_neo4j_node(record["e"], self.entity_class) for record in records]

        # Get total count for pagination
        count_result = await self.count_user_entities(user_uid, relationship_type, filters)
        if count_result.is_error:
            return Result.fail(count_result)

        total_count = count_result.value

        self.logger.debug(
            f"Found {len(entities)} entities for user {user_uid} (total: {total_count})"
        )
        return Result.ok((entities, total_count))

    async def list_by_user(self, user_uid: UserUID, limit: int = 100) -> Result[builtins.list[T]]:
        """
        List a user's entities as a flat list (not a paginated tuple).

        THE generic body behind the domain backends' list_by_user /
        get_user_{tasks,goals,...} wrappers.
        """
        page_result = await self.get_user_entities(user_uid, limit=limit)
        if page_result.is_error:
            return Result.fail(page_result)
        entities, _ = page_result.value
        return Result.ok(entities)

    @safe_backend_operation("count_user_entities")
    async def count_user_entities(
        self,
        user_uid: UserUID,
        relationship_type: RelationshipName | None = None,
        filters: dict[str, Any] | None = None,
    ) -> Result[int]:
        """
        Count entities for a user.

        Args:
            user_uid: User UID,
            relationship_type: Optional relationship type filter,
            filters: Optional filters on entity properties

        Returns:
            Result[int] count of entities

        Example:
            # Count all user's tasks
            count_result = await tasks_backend.count_user_entities("user_123")

            # Count completed tasks
            count_result = await tasks_backend.count_user_entities(
                "user_123",
                filters={"status": "completed"}
            )
        """
        # Default relationship type: OWNS (domain-first architecture). The
        # RelationshipName type is the injection-safety guarantee — no runtime
        # validation needed before interpolation.
        if relationship_type is None:
            relationship_type = RelationshipName.OWNS

        where_clause, params = self._build_user_entity_filters(user_uid, filters)

        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{relationship_type}]->(e:{self.label})
        {where_clause}
        RETURN count(e) as count
        """

        record = await self._run_single(query, params)

        count = record["count"] if record else 0
        return Result.ok(count)

    @safe_backend_operation("update_relationship_access")
    async def update_relationship_access(
        self,
        user_uid: UserUID,
        entity_uid: EntityUID,
        relationship_type: RelationshipName | None = None,
    ) -> Result[bool]:
        """
        Update relationship metadata when user accesses an entity.

        Increments access_count and updates last_accessed timestamp.
        Use this to track user engagement with entities.

        Args:
            user_uid: User UID,
            entity_uid: Entity UID,
            relationship_type: Optional relationship type

        Returns:
            Result[bool] indicating success

        Example:
            # Track when user views a task
            await backend.update_relationship_access(
                user_uid="user_123",
                entity_uid="task_456"
            )
        """
        # Default relationship type: OWNS; the RelationshipName type is the
        # injection-safety guarantee (no runtime validation needed).
        if relationship_type is None:
            relationship_type = RelationshipName.OWNS

        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[r:{relationship_type}]->(e:{self.label} {{uid: $entity_uid}})
        SET r.access_count = coalesce(r.access_count, 0) + 1,
            r.last_accessed = $now
        RETURN r.access_count as count
        """

        record = await self._run_single(
            query,
            {
                "user_uid": user_uid,
                "entity_uid": entity_uid,
                "now": datetime.now().isoformat(),
            },
        )

        if not record:
            return Result.fail(
                Errors.not_found(
                    "relationship",
                    f"User {user_uid} --[{relationship_type}]-> {self.label} {entity_uid}",
                )
            )

        self.logger.debug(
            f"Updated access for {user_uid} -> {entity_uid} (count: {record['count']})"
        )
        return Result.ok(True)

    @safe_backend_operation("delete_user_relationship")
    async def delete_user_relationship(
        self,
        user_uid: UserUID,
        entity_uid: EntityUID,
        relationship_type: RelationshipName | None = None,
    ) -> Result[bool]:
        """
        Delete user-entity relationship.

        Use this when transferring entity ownership or removing user access.

        Args:
            user_uid: User UID,
            entity_uid: Entity UID,
            relationship_type: Optional relationship type

        Returns:
            Result[bool] indicating success

        Example:
            # Remove user's access to a shared goal
            await backend.delete_user_relationship(
                user_uid="user_123",
                entity_uid="goal_456"
            )
        """
        # Default relationship type: OWNS; the RelationshipName type is the
        # injection-safety guarantee (no runtime validation needed).
        if relationship_type is None:
            relationship_type = RelationshipName.OWNS

        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[r:{relationship_type}]->(e:{self.label} {{uid: $entity_uid}})
        DELETE r
        RETURN count(r) as deleted
        """

        record = await self._run_single(query, {"user_uid": user_uid, "entity_uid": entity_uid})

        deleted = (record and record["deleted"] > 0) if record else False

        if deleted:
            self.logger.info(
                f"Deleted user relationship: {user_uid} --[{relationship_type}]-> {entity_uid}"
            )
        else:
            self.logger.warning(f"No relationship found to delete: {user_uid} -> {entity_uid}")

        return Result.ok(deleted)
