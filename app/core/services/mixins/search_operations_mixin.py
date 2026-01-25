"""
Search Operations Mixin
=======================

Provides text search, graph-aware search, filtering, and faceted search.

Methods:
    Text Search:
        - search: Text search across configured fields
        - search_by_tags: Search by tag array field
        - search_array_field: Generic array field search

    Graph Search:
        - get_by_relationship: Get entities via graph relationship
        - search_connected_to: Text search + relationship traversal
        - graph_aware_faceted_search: Unified faceted search

    Filtering:
        - get_by_status: Filter by status field
        - get_by_domain: Filter by domain enum
        - get_by_category: Filter by category field
        - list_user_categories: List unique categories for user
        - list_all_categories: List all categories (admin)
        - count: Count entities matching filters

Type Safety (January 2026)
--------------------------
Filter parameters accept BaseFilterSpec (or domain-specific TypedDicts like
ActivityFilterSpec) for type safety while remaining backward compatible.

    from core.services.protocols import ActivityFilterSpec

    filters: ActivityFilterSpec = {"status": "active", "priority": "high"}
    result = await service.get_by_category("work", filters=filters)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.query import (
    build_relationship_traversal_query,
    build_text_search_query,
)
from core.models.relationship_names import RelationshipName
from core.services.protocols import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    from logging import Logger

    from core.models.search_request import SearchRequest
    from core.services.protocols.base_protocols import Direction


class SearchOperationsMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing search, graph search, and filtering operations.

    Uses CypherGenerator for consistent query building with OR semantics
    across multiple fields (case-insensitive CONTAINS).

    Required attributes from composing class:
        backend: B - Backend implementation
        logger: Logger - For debug logging
        entity_label: str - Neo4j node label
        service_name: str - For error messages
        _search_fields: list[str] - Fields to search
        _search_order_by: str - Default sort field
        _category_field: str - Field for categorization
        _dto_class: type[DTOProtocol] - DTO class
        _model_class: type[T] - Domain model class
        _graph_enrichment_patterns: list - Graph enrichment config
        _user_ownership_relationship: str | None - Ownership relationship
        _to_domain_models: Conversion method
        _get_config_value: Config accessor method
    """

    # Type hints for attributes that must be provided by composing class
    backend: B
    logger: Logger
    service_name: str
    _search_fields: ClassVar[list[str]]
    _search_order_by: str
    _category_field: str
    _dto_class: type[DTOProtocol] | None
    _model_class: type[T] | None
    _graph_enrichment_patterns: ClassVar[list[tuple[str, str, str] | tuple[str, str, str, str]]]
    _user_ownership_relationship: ClassVar[str | None]

    @property
    def entity_label(self) -> str:
        """Entity label - must be provided by composing class."""
        raise NotImplementedError

    def _to_domain_models(
        self, data_list: builtins.list[Any], dto_class: type[DTOProtocol], model_class: type[T]
    ) -> builtins.list[T]:
        """Conversion method - provided by ConversionHelpersMixin."""
        raise NotImplementedError

    def _get_config_value(self, attr_name: str, default: Any = None) -> Any:
        """Config accessor - must be provided by composing class."""
        raise NotImplementedError

    # ========================================================================
    # SEARCH AND QUERY OPERATIONS
    # ========================================================================

    @with_error_handling("search", error_type="database")
    async def search(self, query: str, limit: int = 50) -> Result[builtins.list[T]]:
        """
        Text search across configured search fields.

        Uses CypherGenerator.build_text_search_query() for consistent text search
        with OR semantics across multiple fields (case-insensitive CONTAINS).

        **Class Attributes Used:**
        - _search_fields: Fields to search (default: ["title", "description"])
        - _search_order_by: Field to order results by (default: "created_at")
        - _dto_class: DTO class for conversion
        - _model_class: Domain model class for conversion

        Args:
            query: Search string (case-insensitive)
            limit: Maximum results to return (default 50)

        Returns:
            Result containing matching entities sorted by _search_order_by DESC
        """
        if not query:
            return Result.fail(Errors.validation(message="Search query is required", field="query"))

        # Check if we have the required configuration for CypherGenerator search
        if self._dto_class is None or self._model_class is None:
            # Fall back to backend.search() for unconfigured services
            return await self.backend.search(query, limit)

        # Use modular cypher query for consistent text search pattern
        cypher_query, params = build_text_search_query(
            self._model_class,
            query,
            search_fields=self._search_fields,
            label=self.entity_label,
            limit=limit,
            order_by=self._search_order_by,
            order_desc=True,
        )

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to domain models
        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(f"Found {len(entities)} {self.entity_label}(s) matching '{query}'")
        return Result.ok(entities)

    @with_error_handling("get_by_relationship", error_type="database", uid_param="related_uid")
    async def get_by_relationship(
        self,
        related_uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
    ) -> Result[builtins.list[T]]:
        """
        Get entities connected via graph relationship.

        Uses single-query traversal (eliminates N+1 pattern) via
        CypherGenerator.build_relationship_traversal_query().

        Args:
            related_uid: UID of the related entity (source node)
            relationship_type: Type-safe RelationshipName enum
            direction: "outgoing", "incoming", or "both" (default "outgoing")

        Returns:
            Result containing related entities
        """
        if not related_uid:
            return Result.fail(
                Errors.validation(message="related_uid is required", field="related_uid")
            )

        # Check if we have the required configuration
        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class "
                    "class attributes to use get_by_relationship()",
                    operation="get_by_relationship",
                )
            )

        # Single-query traversal - returns full entities (no N+1)
        cypher_query, params = build_relationship_traversal_query(
            source_uid=related_uid,
            relationship_type=relationship_type.value,
            target_label=self.entity_label,
            direction=direction,
        )

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to domain models
        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(
            f"Found {len(entities)} {self.entity_label}(s) via "
            f"{relationship_type.value} from {related_uid}"
        )
        return Result.ok(entities)

    @with_error_handling("search_connected_to", error_type="database")
    async def search_connected_to(
        self,
        query: str,
        related_uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        limit: int = 50,
    ) -> Result[builtins.list[T]]:
        """
        Graph-aware search: text search + relationship traversal in ONE query.

        This is Neo4j's unique value proposition - combining property search
        with graph traversal.

        Args:
            query: Search text (case-insensitive CONTAINS)
            related_uid: UID of the entity to traverse from
            relationship_type: Type-safe RelationshipName enum
            direction: "outgoing", "incoming", or "both" (default "outgoing")
            limit: Maximum results (default 50)

        Returns:
            Result containing entities matching query AND connected via relationship
        """
        if not query:
            return Result.fail(Errors.validation(message="Search query is required", field="query"))

        if not related_uid:
            return Result.fail(
                Errors.validation(message="related_uid is required", field="related_uid")
            )

        # Check if we have the required configuration
        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class "
                    "class attributes to use search_connected_to()",
                    operation="search_connected_to",
                )
            )

        # Use graph-aware search query builder
        from core.models.query.cypher import build_graph_aware_search_query

        cypher_query, params = build_graph_aware_search_query(
            self._model_class,
            query=query,
            source_uid=related_uid,
            relationship_type=relationship_type.value,
            search_fields=self._search_fields,
            label=self.entity_label,
            direction=direction,
            limit=limit,
            order_by=self._search_order_by,
            order_desc=True,
        )

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to domain models
        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(
            f"Graph-aware search for '{query}' via {relationship_type.value} "
            f"from {related_uid} returned {len(entities)} {self.entity_label}(s)"
        )
        return Result.ok(entities)

    @with_error_handling("search_by_tags", error_type="database")
    async def search_by_tags(
        self,
        tags: builtins.list[str],
        match_all: bool = False,
        limit: int = 50,
    ) -> Result[builtins.list[T]]:
        """
        Search entities by tags (array field search).

        Args:
            tags: List of tag values to search for
            match_all: If True, require ALL tags; if False, ANY tag matches
            limit: Maximum results (default 50)

        Returns:
            Result containing entities with matching tags
        """
        if not tags:
            return Result.fail(
                Errors.validation(message="At least one tag is required", field="tags")
            )

        # Get configuration values (DomainConfig or class attributes)
        dto_class = self._get_config_value("dto_class")
        model_class = self._get_config_value("model_class")
        search_order_by = self._get_config_value("search_order_by", "created_at")

        # Check if we have the required configuration
        if dto_class is None or model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure dto_class and model_class "
                    "via DomainConfig or class attributes to use search_by_tags()",
                    operation="search_by_tags",
                )
            )

        # Use array search query builder
        from core.models.query.cypher import build_array_any_match_query

        cypher_query, params = build_array_any_match_query(
            label=self.entity_label,
            field="tags",
            values=tags,
            match_all=match_all,
            limit=limit,
            order_by=search_order_by,
            order_desc=True,
        )

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to domain models
        entities = self._to_domain_models(result.value, dto_class, model_class)

        mode = "ALL" if match_all else "ANY"
        self.logger.debug(
            f"Tag search ({mode} of {tags}) returned {len(entities)} {self.entity_label}(s)"
        )
        return Result.ok(entities)

    @with_error_handling("search_array_field", error_type="database")
    async def search_array_field(
        self,
        field: str,
        value: str,
        limit: int = 50,
    ) -> Result[builtins.list[T]]:
        """
        Search any array field for a value (generic array search).

        Args:
            field: Name of the array field to search (e.g., "tags", "categories")
            value: Value to search for (case-insensitive contains)
            limit: Maximum results (default 50)

        Returns:
            Result containing entities where array field contains value
        """
        if not field:
            return Result.fail(Errors.validation(message="Field name is required", field="field"))
        if not value:
            return Result.fail(Errors.validation(message="Search value is required", field="value"))

        # Check if we have the required configuration
        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class "
                    "class attributes to use search_array_field()",
                    operation="search_array_field",
                )
            )

        # Use array contains query builder
        from core.models.query.cypher import build_array_contains_query

        cypher_query, params = build_array_contains_query(
            label=self.entity_label,
            field=field,
            value=value,
            limit=limit,
            order_by=self._search_order_by,
            order_desc=True,
        )

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to domain models
        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(
            f"Array search on {field} for '{value}' returned {len(entities)} {self.entity_label}(s)"
        )
        return Result.ok(entities)

    # ========================================================================
    # UNIFIED GRAPH-AWARE FACETED SEARCH (January 2026)
    # ========================================================================

    @with_error_handling("graph_aware_faceted_search", error_type="database")
    async def graph_aware_faceted_search(
        self,
        request: SearchRequest,
        user_uid: str,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Graph-aware faceted search - THE unified method for all domains.

        Combines:
        1. User ownership filter (if _user_ownership_relationship is set)
        2. Property filters from request.to_neo4j_filters()
        3. Text search on _search_fields
        4. Graph pattern enrichment from _graph_enrichment_patterns
        5. Relationship filters from request.to_graph_patterns()

        Args:
            request: SearchRequest with query and facets
            user_uid: User identifier for ownership and graph patterns

        Returns:
            Result[list[dict]]: Results with _graph_context enrichment
        """
        # Validate configuration
        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class",
                    operation="graph_aware_faceted_search",
                )
            )

        # Build dynamic Cypher query
        # Note: Using dict[str, Any] for params because we dynamically add keys
        # Callers can use CypherParams for type-safe construction before passing
        cypher_parts: list[str] = []
        params: dict[str, Any] = {"user_uid": user_uid}

        # 1. Base MATCH with optional user ownership
        if self._user_ownership_relationship:
            # Activity Domain: User OWNS entity
            cypher_parts.append(
                f"MATCH (user:User {{uid: $user_uid}})-[:{self._user_ownership_relationship}]->"
                f"(entity:{self.entity_label})"
            )
        else:
            # Curriculum Domain: Shared content, no ownership
            cypher_parts.append(f"MATCH (entity:{self.entity_label})")

        # 2. WHERE clause for property filters
        where_clauses = ["1=1"]  # Base condition

        # Property filters from SearchRequest (always present - type-safe)
        neo4j_filters = request.to_neo4j_filters()
        for field, value in neo4j_filters.items():
            param_name = f"filter_{field}"
            where_clauses.append(f"entity.{field} = ${param_name}")
            params[param_name] = value

        # 3. Text search on _search_fields
        query_text = getattr(request, "query_text", None)
        if query_text:
            text_conditions = []
            params["query_text"] = query_text.lower()
            for field in self._search_fields:
                text_conditions.append(f"toLower(entity.{field}) CONTAINS $query_text")
            if text_conditions:
                where_clauses.append(f"({' OR '.join(text_conditions)})")

        # 4. Graph patterns from SearchRequest (for Curriculum domains like KU)
        if request.has_relationship_filters():
            graph_patterns = request.to_graph_patterns()
            for pattern_cypher in graph_patterns.values():
                # Replace 'ku' with 'entity' for generic use
                adjusted_pattern = pattern_cypher.replace("(ku)", "(entity)")
                where_clauses.append(adjusted_pattern.strip())

        cypher_parts.append(f"WHERE {' AND '.join(where_clauses)}")

        # 5. Graph enrichment via OPTIONAL MATCHes
        enrichment_returns = []
        for pattern in self._graph_enrichment_patterns:
            # Support both 3-tuple (default outgoing) and 4-tuple (with direction)
            if len(pattern) == 4:
                rel_type, target_label, context_name, direction = pattern
            else:
                rel_type, target_label, context_name = pattern
                direction = "outgoing"

            # Build relationship pattern based on direction
            if direction == "incoming":
                rel_pattern = f"({context_name}:{target_label})-[:{rel_type}]->(entity)"
            elif direction == "both":
                rel_pattern = f"(entity)-[:{rel_type}]-({context_name}:{target_label})"
            else:  # outgoing (default)
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
        cypher_parts.append(f"ORDER BY entity.{self._search_order_by} DESC")
        limit = getattr(request, "limit", 50)
        cypher_parts.append(f"LIMIT {limit}")

        # Build final query
        cypher_query = "\n".join(cypher_parts)

        self.logger.debug(f"Graph-aware faceted search query:\n{cypher_query}")

        # Execute query
        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert results to dict format with _graph_context
        results = []
        for record in result.value or []:
            entity_data = record.get("entity", {})

            # Build result dict from entity properties
            result_dict = dict(entity_data) if isinstance(entity_data, dict) else {}
            result_dict["_domain"] = self.entity_label.lower()

            # Add graph context from enrichment patterns
            graph_context: dict[str, Any] = {}
            for pattern in self._graph_enrichment_patterns:
                # Extract context_name (3rd element in both 3-tuple and 4-tuple)
                context_name = pattern[2]
                context_list = record.get(f"{context_name}_list", [])
                # Filter out None entries
                filtered_list = [
                    item for item in context_list if item.get(f"{context_name}_uid") is not None
                ]
                graph_context[context_name] = filtered_list
                graph_context[f"{context_name}_count"] = len(filtered_list)

            if graph_context:
                result_dict["_graph_context"] = graph_context

            results.append(result_dict)

        self.logger.debug(
            f"Graph-aware faceted search returned {len(results)} {self.entity_label}(s)"
        )
        return Result.ok(results)

    # ========================================================================
    # GENERIC FILTER METHODS - DomainSearchOperations Protocol
    # ========================================================================

    @with_error_handling("get_by_status", error_type="database")
    async def get_by_status(self, status: str, limit: int = 100) -> Result[builtins.list[T]]:
        """
        Filter entities by status field.

        Args:
            status: Status string (e.g., "active", "completed", "archived")
            limit: Maximum results to return

        Returns:
            Result containing entities with matching status
        """
        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class",
                    operation="get_by_status",
                )
            )

        result = await self.backend.find_by(status=status, limit=limit)
        if result.is_error:
            return Result.fail(result.expect_error())

        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(f"Found {len(entities)} {self.entity_label}(s) with status '{status}'")
        return Result.ok(entities)

    @with_error_handling("get_by_domain", error_type="database")
    async def get_by_domain(self, domain: Any, limit: int = 100) -> Result[builtins.list[T]]:
        """
        Filter entities by Domain enum.

        Args:
            domain: Domain enum value (TECH, HEALTH, PERSONAL, etc.)
            limit: Maximum results to return

        Returns:
            Result containing entities in specified domain
        """
        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class",
                    operation="get_by_domain",
                )
            )

        from core.services.protocols import get_enum_value

        domain_value = get_enum_value(domain)
        result = await self.backend.find_by(domain=domain_value, limit=limit)
        if result.is_error:
            return Result.fail(result.expect_error())

        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(
            f"Found {len(entities)} {self.entity_label}(s) in domain '{domain_value}'"
        )
        return Result.ok(entities)

    @with_error_handling("get_by_category", error_type="database")
    async def get_by_category(
        self, category: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[builtins.list[T]]:
        """
        Filter entities by category field.

        Uses _category_field class attribute to determine which field to query.

        Args:
            category: Category name to filter by
            user_uid: Optional user filter
            limit: Maximum results to return

        Returns:
            Result containing entities in the specified category
        """
        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure _dto_class and _model_class",
                    operation="get_by_category",
                )
            )

        # Build filter kwargs dynamically using _category_field
        filters: dict[str, Any] = {self._category_field: category, "limit": limit}
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(**filters)
        if result.is_error:
            return Result.fail(result.expect_error())

        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(
            f"Found {len(entities)} {self.entity_label}(s) in {self._category_field} '{category}'"
        )
        return Result.ok(entities)

    @with_error_handling("list_user_categories", error_type="database")
    async def list_user_categories(self, user_uid: str) -> Result[builtins.list[str]]:
        """
        List unique category values for a specific user's entities.

        Args:
            user_uid: Required user identifier

        Returns:
            Result containing list of category strings for this user
        """
        from core.models.query.cypher import build_distinct_values_query

        query, params = build_distinct_values_query(
            label=self.entity_label,
            field=self._category_field,
            user_uid=user_uid,
        )

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        categories = [record["value"] for record in result.value if record.get("value")]

        self.logger.debug(
            f"Found {len(categories)} {self.entity_label} categories for user {user_uid}"
        )
        return Result.ok(categories)

    @with_error_handling("list_all_categories", error_type="database")
    async def list_all_categories(self) -> Result[builtins.list[str]]:
        """
        List all unique category values across all users.

        WARNING: This is for admin/system use only.

        Returns:
            Result containing list of all category strings
        """
        from core.models.query.cypher import build_distinct_values_query

        query, params = build_distinct_values_query(
            label=self.entity_label,
            field=self._category_field,
            user_uid=None,  # No user filter = all users
        )

        result = await self.backend.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        categories = [record["value"] for record in result.value if record.get("value")]

        self.logger.debug(f"Found {len(categories)} total {self.entity_label} categories")
        return Result.ok(categories)

    async def count(self, **filters: Any) -> Result[int]:
        """Count entities matching filters."""
        return await self.backend.count(**filters)
