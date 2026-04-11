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
from core.models.type_hints import EntityUID, FilterParams, UserUID
from core.utils.error_boundary import safe_backend_operation
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.neo4j_mapper import from_neo4j_node
from core.utils.result_simplified import Errors, Result
from core.utils.validation_helpers import validate_field_name

if TYPE_CHECKING:
    import builtins
    import logging

    from neo4j import AsyncDriver

    from adapters.persistence.neo4j.query import UnifiedQueryBuilder
    from core.infrastructure.monitoring.prometheus_metrics import PrometheusMetrics
    from core.ports.base_protocols import Direction, GraphContextNode


class _SearchMixin[T: DomainModelProtocol]:
    """
    EntitySearchOperations[T] — find_by_date_range, search, find_by, count,
    health_check, get_domain_context_raw, execute_query.

    Requires on concrete class:
        driver: AsyncDriver
        logger: logging.Logger
        entity_class: type[T]
        label: str
        default_filters: FilterParams
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
        default_filters: FilterParams
        query_builder: UnifiedQueryBuilder
        prometheus_metrics: PrometheusMetrics | None

        def _default_filter_clause(self, node_var: str = "n") -> str: ...

        def _default_filter_params(self) -> FilterParams: ...

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
        additional_filters: FilterParams | None = None,
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
        entity_uid: EntityUID,
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
            - UnifiedRelationshipService for cross-domain context usage
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

        except NEO4J_EXCEPTIONS as e:
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

    # ============================================================================
    # C: TYPED SEARCH OPERATIONS (April 2026)
    # Encapsulate query builder + execute_query into typed backend methods.
    # Service mixins call these instead of importing query builders directly.
    # ============================================================================

    @safe_backend_operation("text_search_raw")
    async def text_search_raw(
        self,
        query_text: str,
        search_fields: tuple[str, ...],
        *,
        limit: int = 50,
        order_by: str = "created_at",
        order_desc: bool = True,
        user_uid: UserUID | None = None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Text search across specified fields, returning raw dicts.

        Builds and executes a text search Cypher query with OR semantics
        across multiple fields (case-insensitive CONTAINS).

        Args:
            query_text: Search string
            search_fields: Fields to search (e.g., ("title", "description"))
            limit: Maximum results
            order_by: Sort field
            order_desc: Sort descending
            user_uid: Optional user scope

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query import build_text_search_query

        cypher_query, params = build_text_search_query(
            self.entity_class,
            query_text,
            search_fields=search_fields,
            label=self.label,
            limit=limit,
            order_by=order_by,
            order_desc=order_desc,
        )

        if user_uid:
            cypher_query = cypher_query.replace("WHERE ", "WHERE n.user_uid = $user_uid AND ", 1)
            params["user_uid"] = user_uid

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("relationship_traversal_raw")
    async def relationship_traversal_raw(
        self,
        source_uid: str,
        relationship_type: str,
        target_label: str,
        direction: Direction = "outgoing",
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Traverse a graph relationship and return raw target node dicts.

        Args:
            source_uid: UID of the source entity
            relationship_type: Relationship type string
            target_label: Neo4j label of target nodes
            direction: Traversal direction

        Returns:
            Result[list[dict]]: Raw Neo4j records for related entities
        """
        from adapters.persistence.neo4j.query import build_relationship_traversal_query

        cypher_query, params = build_relationship_traversal_query(
            source_uid=source_uid,
            relationship_type=relationship_type,
            target_label=target_label,
            direction=direction,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("graph_aware_search_raw")
    async def graph_aware_search_raw(
        self,
        query_text: str,
        source_uid: str,
        relationship_type: str,
        search_fields: tuple[str, ...],
        *,
        direction: Direction = "outgoing",
        limit: int = 50,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Combined text search + relationship traversal in one query.

        Args:
            query_text: Search string
            source_uid: UID to traverse from
            relationship_type: Relationship type string
            search_fields: Fields to search
            direction: Traversal direction
            limit: Maximum results
            order_by: Sort field
            order_desc: Sort descending

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query.cypher import build_graph_aware_search_query

        cypher_query, params = build_graph_aware_search_query(
            self.entity_class,
            query=query_text,
            source_uid=source_uid,
            relationship_type=relationship_type,
            search_fields=search_fields,
            label=self.label,
            direction=direction,
            limit=limit,
            order_by=order_by,
            order_desc=order_desc,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("array_any_match_raw")
    async def array_any_match_raw(
        self,
        field: str,
        values: builtins.list[str],
        *,
        match_all: bool = False,
        limit: int = 50,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Search array field for ANY/ALL of the given values.

        Args:
            field: Array field name (e.g., "tags")
            values: Values to match
            match_all: Require ALL values (True) or ANY value (False)
            limit: Maximum results
            order_by: Sort field
            order_desc: Sort descending

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query.cypher import build_array_any_match_query

        cypher_query, params = build_array_any_match_query(
            label=self.label,
            field=field,
            values=values,
            match_all=match_all,
            limit=limit,
            order_by=order_by,
            order_desc=order_desc,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("array_contains_raw")
    async def array_contains_raw(
        self,
        field: str,
        value: str,
        *,
        limit: int = 50,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Search array field for a single value (case-insensitive contains).

        Args:
            field: Array field name
            value: Value to search for
            limit: Maximum results
            order_by: Sort field
            order_desc: Sort descending

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query.cypher import build_array_contains_query

        cypher_query, params = build_array_contains_query(
            label=self.label,
            field=field,
            value=value,
            limit=limit,
            order_by=order_by,
            order_desc=order_desc,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("distinct_values_raw")
    async def distinct_values_raw(
        self,
        field: str,
        user_uid: UserUID | None = None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get distinct values for a field, optionally scoped to a user.

        Args:
            field: Field to get distinct values for
            user_uid: Optional user scope (None = all users)

        Returns:
            Result[list[dict]]: Records with "value" key
        """
        from adapters.persistence.neo4j.query.cypher import build_distinct_values_query

        cypher_query, params = build_distinct_values_query(
            label=self.label,
            field=field,
            user_uid=user_uid,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("faceted_search_raw")
    async def faceted_search_raw(
        self,
        user_uid: UserUID,
        *,
        user_ownership_relationship: str | None,
        search_fields: tuple[str, ...],
        search_order_by: str,
        graph_enrichment_patterns: tuple[tuple[str, ...], ...],
        property_filters: dict[str, Any],
        query_text: str | None = None,
        graph_patterns: dict[str, str] | None = None,
        limit: int = 50,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Graph-aware faceted search combining ownership, filters, text,
        and graph enrichment in a single Cypher query.

        Args:
            user_uid: User identifier for ownership patterns
            user_ownership_relationship: Relationship type for ownership (None for shared content)
            search_fields: Fields for text search
            search_order_by: Sort field
            graph_enrichment_patterns: Tuples of (rel_type, target_label, context_name[, direction])
            property_filters: Exact-match property filters
            query_text: Optional text search
            graph_patterns: Optional graph pattern filters
            limit: Maximum results

        Returns:
            Result[list[dict]]: Records with entity data and enrichment collections
        """
        cypher_parts: builtins.list[str] = []
        params: dict[str, Any] = {"user_uid": user_uid}

        # 1. Base MATCH with optional user ownership
        if user_ownership_relationship:
            cypher_parts.append(
                f"MATCH (user:User {{uid: $user_uid}})-[:{user_ownership_relationship}]->"
                f"(entity:{self.label})"
            )
        else:
            cypher_parts.append(f"MATCH (entity:{self.label})")

        # 2. WHERE clause for property filters
        where_clauses = ["1=1"]
        for field, value in property_filters.items():
            param_name = f"filter_{field}"
            where_clauses.append(f"entity.{field} = ${param_name}")
            params[param_name] = value

        # 3. Text search on search_fields
        if query_text:
            params["query_text"] = query_text.lower()
            text_conditions = [
                f"toLower(entity.{field}) CONTAINS $query_text" for field in search_fields
            ]
            if text_conditions:
                where_clauses.append(f"({' OR '.join(text_conditions)})")

        # 4. Graph patterns from request
        if graph_patterns:
            for pattern_cypher in graph_patterns.values():
                adjusted_pattern = pattern_cypher.replace("(ku)", "(entity)")
                where_clauses.append(adjusted_pattern.strip())

        cypher_parts.append(f"WHERE {' AND '.join(where_clauses)}")

        # 5. Graph enrichment via OPTIONAL MATCHes
        enrichment_returns = []
        for pattern in graph_enrichment_patterns:
            if len(pattern) == 4:
                rel_type, target_label, context_name, direction = pattern
            else:
                rel_type, target_label, context_name = pattern[0], pattern[1], pattern[2]
                direction = "outgoing"

            if direction == "incoming":
                rel_pattern = f"({context_name}:{target_label})-[:{rel_type}]->(entity)"
            elif direction == "both":
                rel_pattern = f"(entity)-[:{rel_type}]-({context_name}:{target_label})"
            else:
                rel_pattern = f"(entity)-[:{rel_type}]->({context_name}:{target_label})"

            cypher_parts.append(f"OPTIONAL MATCH {rel_pattern}")
            enrichment_returns.append(
                f"collect(DISTINCT {{{context_name}_uid: {context_name}.uid, "
                f"{context_name}_title: {context_name}.title}}) as {context_name}_list"
            )

        # 6. RETURN clause
        return_fields = ["entity"]
        return_fields.extend(enrichment_returns)
        cypher_parts.append(f"RETURN {', '.join(return_fields)}")

        # 7. Ordering and limit
        cypher_parts.append(f"ORDER BY entity.{search_order_by} DESC")
        cypher_parts.append(f"LIMIT {limit}")

        cypher_query = "\n".join(cypher_parts)

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    # ============================================================================
    # D: TEMPORAL QUERY OPERATIONS (April 2026)
    # ============================================================================

    @safe_backend_operation("user_activity_range_raw")
    async def user_activity_range_raw(
        self,
        user_uid: UserUID,
        date_field: str,
        start_date: date,
        end_date: date,
        exclude_statuses: builtins.list[str] | None = None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Query user entities within a date range.

        Args:
            user_uid: User identifier
            date_field: Date field name for range filter
            start_date: Range start
            end_date: Range end
            exclude_statuses: Status values to exclude

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query import build_user_activity_query

        cypher_query, params = build_user_activity_query(
            user_uid=user_uid,
            node_label=self.label,
            date_field=date_field,
            start_date=start_date,
            end_date=end_date,
            exclude_statuses=exclude_statuses or [],
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("due_soon_raw")
    async def due_soon_raw(
        self,
        date_field: str,
        days_ahead: int = 7,
        *,
        exclude_statuses: builtins.list[str] | None = None,
        user_uid: UserUID | None = None,
        limit: int = 100,
        secondary_sort_field: str | None = None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Query entities due within N days.

        Args:
            date_field: Date field for comparison
            days_ahead: Days ahead to look
            exclude_statuses: Status values to exclude
            user_uid: Optional user scope
            limit: Maximum results
            secondary_sort_field: Optional secondary sort

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query.cypher import build_due_soon_query

        cypher_query, params = build_due_soon_query(
            node_label=self.label,
            date_field=date_field,
            days_ahead=days_ahead,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            user_uid=user_uid,
            limit=limit,
            secondary_sort_field=secondary_sort_field,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("overdue_raw")
    async def overdue_raw(
        self,
        date_field: str,
        *,
        exclude_statuses: builtins.list[str] | None = None,
        user_uid: UserUID | None = None,
        limit: int = 100,
        secondary_sort_field: str | None = None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Query entities past their due date.

        Args:
            date_field: Date field for comparison
            exclude_statuses: Status values to exclude
            user_uid: Optional user scope
            limit: Maximum results
            secondary_sort_field: Optional secondary sort

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query.cypher import build_overdue_query

        cypher_query, params = build_overdue_query(
            node_label=self.label,
            date_field=date_field,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            user_uid=user_uid,
            limit=limit,
            secondary_sort_field=secondary_sort_field,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    # ============================================================================
    # E: PREREQUISITE & HIERARCHY QUERY OPERATIONS (April 2026)
    # ============================================================================

    @safe_backend_operation("prerequisite_traversal_raw")
    async def prerequisite_traversal_raw(
        self,
        uid: str,
        relationship_types: builtins.list[str],
        depth: int = 3,
        direction: Direction = "outgoing",
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Traverse prerequisite relationships and return raw records.

        Args:
            uid: Entity UID to start from
            relationship_types: Prerequisite relationship type strings
            depth: Maximum traversal depth
            direction: "outgoing" for prerequisites, "incoming" for enables

        Returns:
            Result[list[dict]]: Raw Neo4j records with node key "n"
        """
        from adapters.persistence.neo4j.query.cypher import build_prerequisite_traversal_query

        cypher_query, params = build_prerequisite_traversal_query(
            label=self.label,
            uid=uid,
            relationship_types=relationship_types,
            depth=depth,
            direction=direction,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("hierarchy_query_raw")
    async def hierarchy_query_raw(
        self,
        uid: str,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get hierarchical structure (parents + children) for an entity.

        Args:
            uid: Entity UID

        Returns:
            Result[list[dict]]: Records with "parents" and "children" keys
        """
        from adapters.persistence.neo4j.query.cypher import build_hierarchy_query

        cypher_query, params = build_hierarchy_query(
            label=self.label,
            uid=uid,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    # ============================================================================
    # F: USER PROGRESS QUERY OPERATIONS (April 2026)
    # ============================================================================

    @safe_backend_operation("user_progress_raw")
    async def user_progress_raw(
        self,
        user_uid: UserUID,
        entity_uid: EntityUID,
        mastery_threshold: float,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get user's progress/mastery for an entity.

        Args:
            user_uid: User identifier
            entity_uid: Entity identifier
            mastery_threshold: Threshold for mastery classification

        Returns:
            Result[list[dict]]: Records with "progress" key
        """
        from adapters.persistence.neo4j.query.cypher import build_user_progress_query

        cypher_query, params = build_user_progress_query(
            label=self.label,
            user_uid=user_uid,
            entity_uid=entity_uid,
            mastery_threshold=mastery_threshold,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("update_user_mastery_rel")
    async def update_user_mastery_rel(
        self,
        user_uid: UserUID,
        entity_uid: EntityUID,
        mastery_level: float,
        rel_type: str,
    ) -> Result[bool]:
        """
        Create/update a user mastery relationship on an entity.

        Args:
            user_uid: User identifier
            entity_uid: Entity identifier
            mastery_level: Mastery level (0.0-1.0)
            rel_type: Relationship type ("MASTERED" or "STUDYING")

        Returns:
            Result[bool]: True if successful
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})
        MATCH (e:{self.label} {{uid: $entity_uid}})
        MERGE (u)-[r:{rel_type}]->(e)
        SET r.level = $mastery_level,
            r.last_accessed = datetime(),
            r.updated_at = datetime()
        RETURN true as success
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "user_uid": user_uid,
                    "entity_uid": entity_uid,
                    "mastery_level": mastery_level,
                },
            )
            await result.consume()
            return Result.ok(True)

    @safe_backend_operation("user_curriculum_raw")
    async def user_curriculum_raw(
        self,
        user_uid: UserUID,
        include_completed: bool = False,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get entities the user is studying or has mastered.

        Args:
            user_uid: User identifier
            include_completed: Include mastered entities

        Returns:
            Result[list[dict]]: Raw Neo4j records with node key "n"
        """
        from adapters.persistence.neo4j.query.cypher import build_user_curriculum_query

        cypher_query, params = build_user_curriculum_query(
            label=self.label,
            user_uid=user_uid,
            include_completed=include_completed,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    # ============================================================================
    # G: CONTEXT QUERY OPERATIONS (April 2026)
    # ============================================================================

    @safe_backend_operation("context_query_raw")
    async def context_query_raw(
        self,
        uid: str,
        *,
        include_relationships: builtins.list[str] | None = None,
        exclude_relationships: builtins.list[str] | None = None,
        default_confidence: float = 0.7,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Registry-driven context query for entity with graph neighborhood.

        Args:
            uid: Entity UID
            include_relationships: Only include these context field names
            exclude_relationships: Exclude these context field names
            default_confidence: Minimum confidence threshold

        Returns:
            Result[list[dict]]: Records with entity and relationship collections
        """
        from adapters.persistence.neo4j.query.cypher.context_query_generator import (
            generate_context_query,
        )

        cypher_query, params = generate_context_query(
            entity_label=self.label,
            include_relationships=include_relationships,
            exclude_relationships=exclude_relationships,
            default_confidence=default_confidence,
        )
        params["uid"] = uid

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("basic_context_query_raw")
    async def basic_context_query_raw(
        self,
        uid: str,
        prereq_rels: str,
        min_confidence: float = 0.7,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Basic 3-relationship context query for entities not in the registry.

        Args:
            uid: Entity UID
            prereq_rels: Pipe-separated prerequisite relationship types
            min_confidence: Minimum confidence threshold

        Returns:
            Result[list[dict]]: Records with n, prerequisites, enables, related
        """
        label = self.label
        query = f"""
        MATCH (n:{label} {{uid: $uid}})

        // Prerequisites (outgoing REQUIRES relationships)
        OPTIONAL MATCH (n)-[r1:{prereq_rels}]->(prereq:{label})
        WHERE coalesce(r1.confidence, 1.0) >= $min_confidence
        WITH n, collect(DISTINCT {{
            uid: prereq.uid,
            title: prereq.title,
            confidence: coalesce(r1.confidence, 1.0)
        }}) as prerequisites

        // Entities this enables (incoming relationships)
        OPTIONAL MATCH (enabled:{label})-[r2:{prereq_rels}]->(n)
        WHERE coalesce(r2.confidence, 1.0) >= $min_confidence
        WITH n, prerequisites, collect(DISTINCT {{
            uid: enabled.uid,
            title: enabled.title,
            confidence: coalesce(r2.confidence, 1.0)
        }}) as enables

        // Related entities (lateral connections)
        OPTIONAL MATCH (n)-[r3:RELATED_TO|SIMILAR_TO]-(related:{label})
        WHERE coalesce(r3.confidence, 1.0) >= $min_confidence * 0.8
        WITH n, prerequisites, enables, collect(DISTINCT {{
            uid: related.uid,
            title: related.title,
            confidence: coalesce(r3.confidence, 1.0)
        }}) as related

        RETURN n, prerequisites, enables, related
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"uid": uid, "min_confidence": min_confidence})
            return Result.ok(await result.data())
