"""
Search Raw Mixin
================

Typed search operations (April 2026) — encapsulate query builder +
execute_query into typed backend methods. Service mixins call these
instead of importing query builders directly.

Provides:
    text_search_raw: Text search across multiple fields
    relationship_traversal_raw: Graph traversal returning raw dicts
    graph_aware_search_raw: Combined text search + traversal
    array_any_match_raw: Array field ANY/ALL matching
    array_contains_raw: Array field contains single value
    distinct_values_raw: Distinct values for a field
    faceted_search_raw: Graph-aware faceted search

Requires on concrete class:
    driver, label, entity_class
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import SearchVisibility
from core.models.protocols import DomainModelProtocol
from core.models.type_hints import UserUID
from core.utils.error_boundary import safe_backend_operation
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins

    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel
    from core.models.relationship_filters import RelationshipFilters
    from core.models.relationship_names import RelationshipName
    from core.ports.base_protocols import Direction


class _SearchRawMixin[T: DomainModelProtocol]:
    """
    Typed search operations that return raw dicts.

    Requires on concrete class:
        driver: AsyncDriver
        label: NeoLabel
        entity_class: type[T]
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: NeoLabel
        entity_class: type[T]

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
        visibility: SearchVisibility | None = None,
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
            user_uid: Requesting user for the visibility clause
            visibility: Domain search-visibility declaration
                (build_search_visibility_clause composes the WHERE fragment)

        Returns:
            Result[list[dict]]: Raw node property dicts
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
            visibility=visibility,
            user_uid=user_uid,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            data = await result.data()
            return Result.ok([record["n"] for record in data])

    @safe_backend_operation("relationship_traversal_raw")
    async def relationship_traversal_raw(
        self,
        source_uid: str,
        relationship_type: str,
        target_label: NeoLabel,
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
            Result[list[dict]]: Raw node property dicts for related entities
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
            data = await result.data()
            return Result.ok([record["target"] for record in data])

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
        user_uid: UserUID | None = None,
        visibility: SearchVisibility | None = None,
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
            user_uid: Requesting user for the visibility clause
            visibility: Domain search-visibility declaration

        Returns:
            Result[list[dict]]: Raw node property dicts
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
            visibility=visibility,
            user_uid=user_uid,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            data = await result.data()
            return Result.ok([record["target"] for record in data])

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
        user_uid: UserUID | None = None,
        visibility: SearchVisibility | None = None,
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
            user_uid: Requesting user for the visibility clause
            visibility: Domain search-visibility declaration

        Returns:
            Result[list[dict]]: Raw node property dicts
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
            visibility=visibility,
            user_uid=user_uid,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            data = await result.data()
            return Result.ok([record["n"] for record in data])

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
            Result[list[dict]]: Raw node property dicts
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
            data = await result.data()
            return Result.ok([record["n"] for record in data])

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
        user_ownership_relationship: RelationshipName | None,
        search_fields: tuple[str, ...],
        search_order_by: str,
        graph_enrichment_patterns: tuple[tuple[str, ...], ...],
        property_filters: dict[str, Any],
        query_text: str | None = None,
        relationship_filters: RelationshipFilters | None = None,
        limit: int = 50,
        visibility: SearchVisibility | None = None,
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
            relationship_filters: Optional graph-aware relationship-filter intent;
                its Cypher WHERE-clause fragments are authored below the boundary
            limit: Maximum results
            visibility: SCOPE_AWARE replaces the ownership MATCH with the
                scope/sharing WHERE fragment (curriculum + OWNS/SHARES_WITH/
                group membership); other values keep the MATCH-based path

        Returns:
            Result[list[dict]]: Records with entity data and enrichment collections
        """
        from adapters.persistence.neo4j.query.cypher import (
            build_relationship_filter_fragments,
            build_search_visibility_clause,
        )

        cypher_parts: builtins.list[str] = []
        params: dict[str, Any] = {"user_uid": user_uid}

        # 1. Base MATCH with optional user ownership. SCOPE_AWARE domains
        # (Exercise) can't use an ownership MATCH — it would hide CURRICULUM
        # content that has no owner — so they scope via WHERE instead.
        scope_aware = visibility is SearchVisibility.SCOPE_AWARE
        if user_ownership_relationship and not scope_aware:
            cypher_parts.append(
                f"MATCH (user:User {{uid: $user_uid}})-[:{user_ownership_relationship}]->"
                f"(entity:{self.label})"
            )
        else:
            cypher_parts.append(f"MATCH (entity:{self.label})")

        # 2. WHERE clause for property filters
        where_clauses = ["1=1"]
        if scope_aware:
            visibility_scope = build_search_visibility_clause(
                visibility, entity_alias="entity", has_user=True
            )
            if visibility_scope:
                scope_clause, scope_params = visibility_scope
                where_clauses.append(scope_clause)
                params.update(scope_params)
        for field, value in property_filters.items():
            param_name = f"filter_{field}"
            if isinstance(value, list):
                # List param: whole-value equality (unchanged semantics)
                where_clauses.append(f"entity.{field} = ${param_name}")
            else:
                # Scalar param: exact match on scalar properties, element
                # membership on array properties (e.g. the `nous` topic list
                # on Ku/PathStep). CASE guards the IN from type errors on
                # non-list properties.
                where_clauses.append(
                    f"(CASE WHEN entity.{field} IS :: LIST<ANY> "
                    f"THEN ${param_name} IN entity.{field} "
                    f"ELSE entity.{field} = ${param_name} END)"
                )
            params[param_name] = value

        # 3. Text search on search_fields
        if query_text:
            params["query_text"] = query_text.lower()
            text_conditions = [
                f"toLower(entity.{field}) CONTAINS $query_text" for field in search_fields
            ]
            if text_conditions:
                where_clauses.append(f"({' OR '.join(text_conditions)})")

        # 4. Relationship filters from request (Cypher authored below the boundary)
        if relationship_filters is not None:
            where_clauses.extend(build_relationship_filter_fragments(relationship_filters))

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
