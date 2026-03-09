"""
Search Mixin
============

EntitySearchOperations[T] protocol implementation.

Provides:
    find_by_date_range: Date-range entity filtering
    search: Text substring search across title/name/description/content
    find_by: Dynamic field filtering with operator support (eq, gt, lt, contains, in)
    count: Count entities with filters
    health_check: Database connectivity check
    get_domain_context_raw: Raw graph traversal context (domain-agnostic)
    execute_query: Low-level Cypher execution for batch operations

Requires on concrete class:
    driver, logger, entity_class, label, default_filters, query_builder,
    _default_filter_clause, _default_filter_params, _inject_default_filters,
    _is_driver_closed, _track_db_metrics, list
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol
from core.utils.error_boundary import safe_backend_operation
from core.utils.neo4j_mapper import from_neo4j_node
from core.utils.result_simplified import Errors, Result
from core.utils.validation_helpers import validate_field_name

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver

    from adapters.persistence.neo4j.query import UnifiedQueryBuilder
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics
    from core.ports.base_protocols import GraphContextNode


class _SearchMixin[T: DomainModelProtocol]:
    """
    EntitySearchOperations[T] — find_by_date_range, search, find_by, count,
    health_check, get_domain_context_raw, execute_query.

    Requires on concrete class:
        driver: AsyncDriver
        logger: logging.Logger
        entity_class: type[T]
        label: str
        default_filters: dict[str, Any]
        query_builder: UnifiedQueryBuilder
        prometheus_metrics: PrometheusMetrics | None
        _default_filter_clause: method
        _default_filter_params: method
        _inject_default_filters: method
        _is_driver_closed: method
        _track_db_metrics: method
        list: async method (from _CrudMixin)
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        logger: logging.Logger
        entity_class: type[T]
        label: str
        default_filters: dict[str, Any]
        query_builder: UnifiedQueryBuilder
        prometheus_metrics: PrometheusMetrics | None

        def _default_filter_clause(self, node_var: str = "n") -> str: ...

        def _default_filter_params(self) -> dict[str, Any]: ...

        def _inject_default_filters(
            self,
            where_clauses: builtins.list[str],
            params: dict[str, Any],
            node_var: str = "n",
        ) -> None: ...

        def _is_driver_closed(self) -> bool: ...

        def _track_db_metrics(
            self, operation: str, duration: float, is_error: bool = False
        ) -> None: ...

        async def list(
            self,
            limit: int = 100,
            offset: int = 0,
            filters: dict[str, Any] | None = None,
            sort_by: str | None = None,
            sort_order: str = "asc",
        ) -> Result[builtins.list[T]]: ...

    # ============================================================================
    # UNIVERSAL DOMAIN-SPECIFIC OPERATIONS
    # ============================================================================

    @safe_backend_operation("find_by_date_range")
    async def find_by_date_range(
        self,
        start_date: date | str | None,
        end_date: date | str | None,
        date_field: str = "occurred_at",
        additional_filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> Result[builtins.list[T]]:
        """Find any entity within a date range."""
        # Validate date_field to prevent Cypher injection
        if not validate_field_name(date_field):
            self.logger.warning(
                f"Invalid date_field rejected, falling back to occurred_at: {date_field!r}"
            )
            date_field = "occurred_at"

        params: dict[str, Any] = {"limit": limit}
        where_clauses: builtins.list[str] = []

        # Inject default_filters for Ku-type discrimination
        self._inject_default_filters(where_clauses, params)

        # Build date range conditions
        if start_date:
            where_clauses.append(f"date(n.{date_field}) >= date($start_date)")
            if isinstance(start_date, date | datetime):
                params["start_date"] = start_date.isoformat()
            else:
                params["start_date"] = start_date

        if end_date:
            where_clauses.append(f"date(n.{date_field}) <= date($end_date)")
            if isinstance(end_date, date | datetime):
                params["end_date"] = end_date.isoformat()
            else:
                params["end_date"] = end_date

        # Add additional filters
        if additional_filters:
            for key, value in additional_filters.items():
                if not validate_field_name(key):
                    self.logger.warning(f"Skipping invalid filter key: {key!r}")
                    continue
                if value is not None:
                    where_clauses.append(f"n.{key} = ${key}")
                    params[key] = value

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
        MATCH (n:{self.label})
        {where_clause}
        RETURN n
        ORDER BY n.{date_field} DESC
        LIMIT $limit
        """

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

            entities = [from_neo4j_node(record["n"], self.entity_class) for record in records]
            return Result.ok(entities)

    @safe_backend_operation("search")
    async def search(self, query: str, limit: int = 10) -> Result[builtins.list[T]]:
        """
        Search any entity type by text.

        Performs case-sensitive substring search across common text fields:
        title, name, description, and content. Returns entities where query
        appears anywhere in these fields.

        Args:
            query: Search string (case-sensitive substring match)
            limit: Maximum number of results to return (default 10)

        Returns:
            Result[List[T]]: Success with matching entities (may be empty),
                            or Failure if database error

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Search for tasks containing "urgent"
            result = await backend.search("urgent", QueryLimit.MEDIUM)

            if result.is_ok:
                tasks = result.value
                print(f"Found {len(tasks)} urgent tasks")
                for task in tasks:
                    print(f"- {task.title}")
            ```

        Search Fields:
            - title: Primary entity title
            - name: Alternative name field
            - description: Entity description
            - content: Full entity content

        Limitations:
            - Case-sensitive matching (use LOWER() for case-insensitive)
            - Substring match only (not full-text search)
            - No relevance ranking
            - Searches across multiple fields (can't limit to specific field)

        Performance:
            - Sequential scan (no full-text index)
            - Use for simple queries only
            - For advanced search, use dedicated search service

        Note:
            - Returns empty list if no matches (not an error)
            - Field must exist and be non-null to match
            - For semantic search, use SearchIntelligenceService
            - For faceted search, use find_by() with filters

        See Also:
            - find_by(): Exact field matching with operators
            - SearchIntelligenceService: Semantic/embedding-based search
            - list(): Get all entities with filters
        """
        df_clause = self._default_filter_clause()
        extra_and = f"\n               AND {df_clause}" if df_clause else ""

        cypher = f"""
            MATCH (n:{self.label})
            WHERE (n.title CONTAINS $query
               OR n.name CONTAINS $query
               OR n.description CONTAINS $query
               OR n.content CONTAINS $query){extra_and}
            RETURN n
            LIMIT $limit
        """

        params: dict[str, Any] = {"query": query, "limit": limit}
        params.update(self._default_filter_params())

        async with self.driver.session() as session:
            result = await session.run(cypher, params)
            records = await result.data()

            entities = [from_neo4j_node(record["n"], self.entity_class) for record in records]
            return Result.ok(entities)

    @safe_backend_operation("find_by")
    async def find_by(self, limit: int = 100, **filters: Any) -> Result[builtins.list[T]]:
        """
        Dynamic find by any model field with operator support.

        This is the new 100% dynamic way to query - automatically supports
        ANY field you add to your model!

        Usage:
            # Simple equality
            tasks = await backend.find_by(priority='high', status='in_progress')

            # Comparison operators
            tasks = await backend.find_by(due_date__gte=date.today())
            tasks = await backend.find_by(estimated_hours__lt=5.0)

            # String matching
            tasks = await backend.find_by(title__contains='urgent')

            # List membership
            tasks = await backend.find_by(priority__in=['high', 'urgent'])

            # Pagination and sorting
            tasks = await backend.find_by(status='active', limit=QueryLimit.SMALL, offset=20)
            tasks = await backend.find_by(priority='high', sort_by='due_date', sort_order='asc')

        Supported operators:
            - eq (default): Exact match
            - gt, lt, gte, lte: Comparisons
            - contains: String matching
            - in: List membership

        Special parameters:
            - limit: Max results (default 100)
            - offset: Pagination offset
            - sort_by: Field name to sort by
            - sort_order: 'asc' or 'desc' (default 'asc')
        """
        start_time = time.time()

        # Extract pagination and sorting parameters
        offset_val = filters.pop("offset", 0)
        sort_by = filters.pop("sort_by", None)
        sort_order = filters.pop("sort_order", "asc")

        if not filters and not self.default_filters:
            return await self.list(limit=limit)  # type: ignore[no-any-return]

        # Merge default_filters (non-overridable) with caller filters
        all_filters = {**filters, **self.default_filters}

        # Use UnifiedQueryBuilder fluent API with explicit label
        query_builder = (
            self.query_builder.for_model(self.entity_class, label=self.label)
            .filter(**all_filters)
            .limit(limit)
        )

        # Apply pagination
        if offset_val > 0:
            query_builder = query_builder.offset(offset_val)

        # Apply sorting
        if sort_by:
            query_builder = query_builder.order_by(sort_by, desc=(sort_order == "desc"))

        query, params = query_builder.build()

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

            entities = [from_neo4j_node(r["n"], self.entity_class) for r in records]

            # Track metrics
            self._track_db_metrics("read", time.time() - start_time, is_error=False)

            return Result.ok(entities)

    @safe_backend_operation("count")
    async def count(self, **filters: Any) -> Result[int]:
        """
        Count any entity type with dynamic filters.

        Now uses UnifiedQueryBuilder - supports the same filter syntax as find_by().
        """
        # Merge default_filters with caller filters
        all_filters = {**filters, **self.default_filters}

        # Use UnifiedQueryBuilder fluent API for counting
        count = await (
            self.query_builder.for_model(self.entity_class, label=self.label).filter(**all_filters)
            if all_filters
            else self.query_builder.for_model(self.entity_class, label=self.label)
        ).count()

        return Result.ok(count)

    @safe_backend_operation("health_check")
    async def health_check(self) -> Result[bool]:
        """Check database health for any entity type."""
        cypher = "RETURN 1 as alive"

        async with self.driver.session() as session:
            result = await session.run(cypher, {})
            record = await result.single()

            return Result.ok(record and record["alive"] == 1)

    # ============================================================================
    # B: RAW GRAPH CONTEXT (DOMAIN-AGNOSTIC)
    # ============================================================================

    async def get_domain_context_raw(
        self,
        entity_uid: str,
        entity_label: str,
        relationship_types: builtins.list[str],
        depth: int = 2,
        min_confidence: float = 0.7,
        bidirectional: bool = False,
    ) -> Result[builtins.list[GraphContextNode]]:
        """
        Get raw graph context without domain-specific categorization.

        This is a PURE PRIMITIVE that returns typed graph traversal results.
        Domain-specific categorization happens in relationship/intelligence services.

        Args:
            entity_uid: Entity UID to query from
            entity_label: Neo4j label (e.g., "Task", "Goal", "Event")
            relationship_types: List of relationship types to traverse
            depth: Graph traversal depth (default 2)
            min_confidence: Minimum path confidence (default 0.7)
            bidirectional: Include incoming and outgoing (default False)

        Returns:
            Result[list[GraphContextNode]] with typed graph traversal results:
                - uid: Entity UID (str)
                - title: Entity title (str)
                - labels: Neo4j labels (list[str])
                - distance: Hops from source (int)
                - path_strength: Confidence cascade (float)
                - via_relationships: Relationship sequence with direction markers (list[str])

        Example:
            ```python
            # Get raw context for a task
            result = await backend.get_domain_context_raw(
                entity_uid="task:123",
                entity_label="Task",
                relationship_types=["DEPENDS_ON", "REQUIRES_KNOWLEDGE"],
                GraphDepth.NEIGHBORHOOD,
                bidirectional=True,
            )

            # Returns typed list - categorization done by caller
            for node in result.value:
                uid = node["uid"] # Type-safe: str
                labels = node["labels"] # Type-safe: list[str]
            ```

        Note:
            - This is domain-agnostic - works for ANY entity type
            - Categorization logic belongs in relationship/intelligence services

        See Also:
            - GraphContextNode for field type documentation
            - TasksRelationshipService.get_task_cross_domain_context() for usage
            - CypherGenerator.build_domain_context_with_paths()
        """
        from adapters.persistence.neo4j.query import build_domain_context_with_paths

        try:
            # Build pure Cypher query
            query, params = build_domain_context_with_paths(
                node_uid=entity_uid,
                node_label=entity_label,
                relationship_types=relationship_types,
                depth=depth,
                min_confidence=min_confidence,
                bidirectional=bidirectional,
            )

            # Execute query
            async with self.driver.session() as session:
                result = await session.run(query, params)
                record = await result.single()

                if not record:
                    return Result.ok([])  # No context found (not an error)

                # Return raw domain_context list
                domain_context = record.get("domain_context", [])
                return Result.ok(domain_context)

        except Exception as e:
            self.logger.error(f"Failed to get raw domain context: {e}")
            return Result.fail(Errors.database(operation="get_domain_context_raw", message=str(e)))

    @safe_backend_operation("execute_query")
    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Execute a low-level Cypher query and return raw results.

        This method is used by batch query methods in relationship services
        to execute CypherGenerator queries efficiently.

        Args:
            query: Cypher query string
            params: Optional query parameters

        Returns:
            Result[list[dict]] with raw Neo4j records as dictionaries

        Example:
            ```python
            from adapters.persistence.neo4j.query import build_batch_relationship_exists

            query, params = build_batch_relationship_exists(
                node_label="Task",
                relationship_types=["REQUIRES_KNOWLEDGE"],
                direction="outgoing",
            )
            params["uids"] = ["task:1", "task:2"]

            result = await backend.execute_query(query, params)
            # Returns: [{"uid": "task:1", "has_relationships": True}, ...]
            ```

        Note:
            - Returns raw dictionaries (not domain models)
            - Used primarily by batch query optimization methods
            - For domain model queries, use find_by() or search()
        """
        # Guard: Skip operation if driver is closed (test teardown)
        if self._is_driver_closed():
            return Result.ok([])

        if params is None:
            params = {}

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()  # Get all records as dictionaries
            return Result.ok(records)
