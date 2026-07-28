"""
Search Operations Mixin
=======================

Provides text search, graph-aware search, filtering, and faceted search.

REQUIRES (Mixin Dependencies):
    - ConversionHelpersMixin: Uses _to_domain_models() for result conversion

PROVIDES (Methods for Routes/Facades):
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
        - get_by_category: Filter by category field
        - list_user_categories: List unique categories for user
        - list_all_categories: List all categories (admin)
        - count: Count entities matching filters

Type Safety (January 2026)
--------------------------
Filter parameters accept BaseFilterSpec (or domain-specific TypedDicts like
ActivityFilterSpec) for type safety while remaining backward compatible.

    from core.ports import ActivityFilterSpec

    filters: ActivityFilterSpec = {"status": "active", "priority": "high"}
    result = await service.get_by_category("work", filters=filters)
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar

from core.models.enums import EntityStatus, SearchVisibility
from core.models.enums.neo_labels import NeoLabel
from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.relationship_names import RelationshipName
from core.models.type_hints import FilterParams, UserUID
from core.ports import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    from logging import Logger

    from core.models.search_request import SearchRequest
    from core.ports.base_protocols import Direction


class SearchOperationsMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing search, graph search, and filtering operations.

    Uses typed backend methods for all Cypher execution. No query builders
    are imported from the adapter layer — all Cypher lives in the backend.

    Required attributes from composing class:
        backend: B - Backend implementation
        logger: Logger - For debug logging
        entity_label: str - Neo4j base-label for Cypher matching (e.g., "Entity", "Ku")
        config_lookup_label: str - LABEL_CONFIGS registry key (e.g., "Task", "PathStep").
            Used for domain-specific target_label filters and log/_domain strings.
        service_name: str - For error messages
        search_fields: tuple[str, ...] - Fields to search (DomainConfig-resolved property)
        search_order_by: str - Default sort field (DomainConfig-resolved property)
        category_field: str - Field for categorization (DomainConfig-resolved property)
        search_visibility: SearchVisibility - Scoping declaration (DomainConfig-resolved property)
        user_ownership_relationship: RelationshipName | None - Ownership relationship
            (DomainConfig-resolved property)
        _dto_class: type[DTOProtocol] - DTO class
        _model_class: type[T] - Domain model class
        _graph_enrichment_patterns: tuple - Graph enrichment config
        _to_domain_models: Conversion method
        _get_config_value: Config accessor method
    """

    # Type hints for attributes that must be provided by composing class
    backend: B
    logger: Logger
    service_name: str
    _dto_class: type[DTOProtocol] | None
    _model_class: type[T] | None
    _graph_enrichment_patterns: ClassVar[
        tuple[tuple[str, str, str] | tuple[str, str, str, str], ...]
    ]

    @property
    @abstractmethod
    def entity_label(self) -> str:
        """Neo4j base-label (e.g., ``"Entity"``, ``"Ku"``) - provided by composing class."""
        ...

    @property
    @abstractmethod
    def config_lookup_label(self) -> str:
        """LABEL_CONFIGS registry key (e.g., ``"Task"``, ``"PathStep"``) - provided by composing class."""
        ...

    @property
    @abstractmethod
    def entity_type_value(self) -> str:
        """DomainConfig-resolved EntityType value (e.g. ``"task"``, ``"path_step"``,
        ``"ku"``) — provided by composing class.

        THE single vocabulary for stamping ``_domain`` on search records, so
        every producer path agrees and consumers see one spelling. Distinct
        from ``config_lookup_label`` (a registry key, not an EntityType).
        """
        ...

    @property
    @abstractmethod
    def category_field(self) -> str:
        """DomainConfig-resolved category field — provided by composing class.

        The old raw ``_category_field`` class attribute bypassed DomainConfig —
        domains configuring ``category_field`` via config (e.g. Goals ``"domain"``)
        were silently ignored by category queries.
        """
        ...

    @property
    @abstractmethod
    def search_fields(self) -> tuple[str, ...]:
        """DomainConfig-resolved search fields — provided by composing class.

        Same bug class as ``category_field``: the raw ``_search_fields``
        class attribute bypassed DomainConfig, so domains configuring custom
        fields (e.g. UserEntry ``content``/``processed_content``) silently
        searched only the ``("title", "description")`` default.
        """
        ...

    @property
    @abstractmethod
    def search_order_by(self) -> str:
        """DomainConfig-resolved sort field — provided by composing class."""
        ...

    @property
    @abstractmethod
    def search_visibility(self) -> SearchVisibility:
        """DomainConfig-resolved search-visibility declaration — provided by composing class.

        THE scoping input for every search strategy. See
        ``DomainConfig.get_search_visibility()`` for the derivation.
        """
        ...

    @property
    @abstractmethod
    def user_ownership_relationship(self) -> RelationshipName | None:
        """DomainConfig-resolved ownership relationship — provided by composing class.

        Same bug class as ``search_fields``: the raw
        ``_user_ownership_relationship`` ClassVar bypassed DomainConfig, so
        curriculum domains declaring ``None`` were silently OWNS-scoped by
        faceted search — hiding all shared content from /search.
        """
        ...

    @abstractmethod
    def _to_domain_models(
        self, data_list: builtins.list[Any], dto_class: type[DTOProtocol], model_class: type[T]
    ) -> builtins.list[T]:
        """Conversion method - provided by ConversionHelpersMixin."""
        ...

    @abstractmethod
    def _get_config_value(self, attr_name: str, default: Any = None) -> Any:
        """Config accessor - must be provided by composing class."""
        ...

    # ========================================================================
    # CONFIGURATION VALIDATION
    # ========================================================================

    def _ensure_configured_for_search(
        self,
    ) -> Result[tuple[type[DTOProtocol], type[T]]]:
        """
        Fail-fast validation: ensure search configuration exists.

        Checks that _dto_class and _model_class are configured, which are
        required for all search operations using CypherGenerator. Returns
        the narrowed (non-None) pair so call sites can pass them straight
        to ``_to_domain_models`` without re-checking.

        Returns:
            Result.ok((dto_class, model_class)) if configured,
            Result.fail() with clear error otherwise.
        """
        if self._dto_class is None or self._model_class is None:
            return Result.fail(
                Errors.validation(
                    message=f"{self.service_name} is not configured for search operations. "
                    "Set _dto_class and _model_class via DomainConfig or class attributes.",
                    field="configuration",
                    user_message="Search is not available for this entity type",
                )
            )
        return Result.ok((self._dto_class, self._model_class))

    # ========================================================================
    # SEARCH AND QUERY OPERATIONS
    # ========================================================================

    @with_error_handling("list_recent_for_user", error_type="database")
    async def list_recent_for_user(
        self,
        user_uid: UserUID,
        limit: int = 10,
        exclude: builtins.set[str] | None = None,
    ) -> Result[builtins.list[T]]:
        """
        List a user's most-recently-updated entities, with optional exclusions.

        Used by the entity-picker UI to populate the dropdown when no query has
        been typed yet. Returns up to ``limit`` entries even when ``exclude`` is
        non-empty — over-fetches to compensate.

        Args:
            user_uid: Owner of the entities.
            limit: Maximum entries to return.
            exclude: UIDs to filter out of the result.

        Returns:
            Result containing the user's entities sorted by ``updated_at`` desc.
        """
        exclude = exclude or set()
        fetch_limit = limit + len(exclude)
        result = await self.backend.get_user_entities(
            user_uid, limit=fetch_limit, sort_by="updated_at", sort_order="desc"
        )
        if result.is_error:
            return Result.fail(result)
        entities, _ = result.value
        return Result.ok([e for e in entities if e.uid not in exclude][:limit])

    @with_error_handling("search_for_user", error_type="database")
    async def search_for_user(
        self,
        query: str,
        user_uid: UserUID,
        limit: int = 10,
        exclude: builtins.set[str] | None = None,
    ) -> Result[builtins.list[T]]:
        """
        User-scoped title/description search with optional UID exclusions.

        Wraps ``search()`` (which already respects ``user_uid`` and the
        configured ``_search_fields``) and post-filters excluded UIDs.

        Args:
            query: Search string (case-insensitive).
            user_uid: Owner of the entities.
            limit: Maximum entries to return.
            exclude: UIDs to filter out of the result.

        Returns:
            Result containing matching entities sorted by ``_search_order_by`` desc.
        """
        exclude = exclude or set()
        fetch_limit = limit + len(exclude)
        result = await self.search(query, limit=fetch_limit, user_uid=user_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([e for e in result.value if e.uid not in exclude][:limit])

    @with_error_handling("search", error_type="database")
    async def search(
        self, query: str, limit: int = 50, user_uid: UserUID | None = None
    ) -> Result[builtins.list[T]]:
        """
        Text search across configured search fields.

        Uses backend.text_search_raw() for consistent text search
        with OR semantics across multiple fields (case-insensitive CONTAINS).

        Args:
            query: Search string (case-insensitive)
            limit: Maximum results to return (default 50)
            user_uid: Optional user UID to scope results to owner

        Returns:
            Result containing matching entities sorted by _search_order_by DESC
        """
        if not query:
            return Result.fail(Errors.validation(message="Search query is required", field="query"))

        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)
        dto_class, model_class = config_result.value

        result = await self.backend.text_search_raw(
            query,
            self.search_fields,
            limit=limit,
            order_by=self.search_order_by,
            order_desc=True,
            user_uid=user_uid,
            visibility=self.search_visibility,
        )
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, dto_class, model_class)

        self.logger.debug(f"Found {len(entities)} {self.config_lookup_label}(s) matching '{query}'")
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
        backend.relationship_traversal_raw().

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

        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)
        dto_class, model_class = config_result.value

        result = await self.backend.relationship_traversal_raw(
            source_uid=related_uid,
            relationship_type=relationship_type.value,
            target_label=NeoLabel(self.config_lookup_label),
            direction=direction,
        )
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, dto_class, model_class)

        self.logger.debug(
            f"Found {len(entities)} {self.config_lookup_label}(s) via "
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
        user_uid: UserUID | None = None,
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
            user_uid: Requesting user — scoped per the domain's search_visibility

        Returns:
            Result containing entities matching query AND connected via relationship
        """
        if not query:
            return Result.fail(Errors.validation(message="Search query is required", field="query"))

        if not related_uid:
            return Result.fail(
                Errors.validation(message="related_uid is required", field="related_uid")
            )

        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)
        dto_class, model_class = config_result.value

        result = await self.backend.graph_aware_search_raw(
            query,
            source_uid=related_uid,
            relationship_type=relationship_type.value,
            search_fields=self.search_fields,
            direction=direction,
            limit=limit,
            order_by=self.search_order_by,
            order_desc=True,
            user_uid=user_uid,
            visibility=self.search_visibility,
        )
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, dto_class, model_class)

        self.logger.debug(
            f"Graph-aware search for '{query}' via {relationship_type.value} "
            f"from {related_uid} returned {len(entities)} {self.config_lookup_label}(s)"
        )
        return Result.ok(entities)

    @with_error_handling("search_by_tags", error_type="database")
    async def search_by_tags(
        self,
        tags: builtins.list[str],
        match_all: bool = False,
        limit: int = 50,
        user_uid: UserUID | None = None,
    ) -> Result[builtins.list[T]]:
        """
        Search entities by tags (array field search).

        Args:
            tags: List of tag values to search for
            match_all: If True, require ALL tags; if False, ANY tag matches
            limit: Maximum results (default 50)
            user_uid: Requesting user — scoped per the domain's search_visibility

        Returns:
            Result containing entities with matching tags
        """
        if not tags:
            return Result.fail(
                Errors.validation(message="At least one tag is required", field="tags")
            )

        dto_class = self._get_config_value("dto_class")
        model_class = self._get_config_value("model_class")
        search_order_by = self._get_config_value("search_order_by", "created_at")

        if dto_class is None or model_class is None:
            return Result.fail(
                Errors.system(
                    message=f"{self.service_name} must configure dto_class and model_class "
                    "via DomainConfig or class attributes to use search_by_tags()",
                    operation="search_by_tags",
                )
            )

        result = await self.backend.array_any_match_raw(
            "tags",
            tags,
            match_all=match_all,
            limit=limit,
            order_by=search_order_by,
            order_desc=True,
            user_uid=user_uid,
            visibility=self.search_visibility,
        )
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, dto_class, model_class)

        mode = "ALL" if match_all else "ANY"
        self.logger.debug(
            f"Tag search ({mode} of {tags}) returned {len(entities)} {self.config_lookup_label}(s)"
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

        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)
        dto_class, model_class = config_result.value

        result = await self.backend.array_contains_raw(
            field,
            value,
            limit=limit,
            order_by=self.search_order_by,
            order_desc=True,
        )
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, dto_class, model_class)

        self.logger.debug(
            f"Array search on {field} for '{value}' returned {len(entities)} {self.config_lookup_label}(s)"
        )
        return Result.ok(entities)

    # ========================================================================
    # UNIFIED GRAPH-AWARE FACETED SEARCH (January 2026)
    # ========================================================================

    @with_error_handling("graph_aware_faceted_search", error_type="database")
    async def graph_aware_faceted_search(
        self,
        request: SearchRequest,
        user_uid: UserUID | None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Graph-aware faceted search - THE unified method for all domains.

        Combines:
        1. Visibility scoping per the domain's search_visibility declaration
           (OWNER_ONLY: ownership MATCH; PUBLIC: none; SCOPE_AWARE: scope/
           sharing WHERE fragment)
        2. Property filters from request.to_property_filters()
        3. Text search on _search_fields
        4. Graph pattern enrichment from _graph_enrichment_patterns
        5. Relationship filters from request.to_relationship_filters()
        6. Tag facet (tags_contain ANY/ALL), sort (SearchSortOrder), offset

        Args:
            request: SearchRequest with query and facets
            user_uid: User identifier for ownership and graph patterns.
                None is valid only for PUBLIC-visibility domains (anonymous
                catalog browse); OWNER_ONLY domains fail closed.

        Returns:
            Result[list[dict]]: Results with _graph_context enrichment
        """
        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)

        # PUBLIC domains (PS, LP, KU) get no ownership MATCH; SCOPE_AWARE
        # (Exercise) scopes via WHERE in the backend instead of the MATCH.
        visibility = self.search_visibility

        # Fail-closed anonymous gate: without a user there is nothing to own,
        # so an OWNER_ONLY domain must refuse rather than leak or return all.
        if user_uid is None and visibility is not SearchVisibility.PUBLIC:
            return Result.fail(
                Errors.validation(
                    message=f"{self.config_lookup_label} search requires an authenticated user",
                    field="user_uid",
                    value=None,
                )
            )

        # Extract request parameters
        property_filters = request.to_property_filters()
        query_text = getattr(request, "query_text", None)
        relationship_filters = (
            request.to_relationship_filters() if request.has_relationship_filters() else None
        )
        limit = getattr(request, "limit", 50)

        # Explicit sort override; RELEVANCE maps to None → the backend falls
        # back to the domain's search_order_by DESC (historical behavior).
        sort = request.get_sort_order()

        ownership_relationship = (
            self.user_ownership_relationship if visibility is SearchVisibility.OWNER_ONLY else None
        )

        result = await self.backend.faceted_search_raw(
            user_uid,
            # Pass the RelationshipName enum straight through — no from_string
            # round-trip (which would silently drop the ownership filter on an
            # unknown name; see ADR / project_security_posture fail-open risk).
            user_ownership_relationship=ownership_relationship,
            search_fields=self.search_fields,
            search_order_by=self.search_order_by,
            graph_enrichment_patterns=self._graph_enrichment_patterns,
            property_filters=property_filters,
            query_text=query_text,
            relationship_filters=relationship_filters,
            tags_contain=request.tags_contain if request.has_tag_filter() else None,
            tags_match_all=request.tags_match_all,
            order_by=sort.get_sort_field(),
            order_desc=sort.is_descending(),
            limit=limit,
            offset=request.offset,
            visibility=visibility,
        )
        if result.is_error:
            return Result.fail(result)

        # Convert results to dict format with _graph_context
        results = []
        for record in result.value or []:
            entity_data = record.get("entity", {})

            result_dict = dict(entity_data) if isinstance(entity_data, dict) else {}
            result_dict["_domain"] = self.entity_type_value

            graph_context: dict[str, Any] = {}
            for pattern in self._graph_enrichment_patterns:
                context_name = pattern[2]
                context_list = record.get(f"{context_name}_list", [])
                filtered_list = [
                    item for item in context_list if item.get(f"{context_name}_uid") is not None
                ]
                graph_context[context_name] = filtered_list
                graph_context[f"{context_name}_count"] = len(filtered_list)

            if graph_context:
                result_dict["_graph_context"] = graph_context

            results.append(result_dict)

        self.logger.debug(
            f"Graph-aware faceted search returned {len(results)} {self.config_lookup_label}(s)"
        )
        return Result.ok(results)

    # ========================================================================
    # GENERIC FILTER METHODS - DomainSearchOperations Protocol
    # ========================================================================

    @with_error_handling("get_by_status", error_type="database")
    async def get_by_status(
        self, status: EntityStatus | str, limit: int = 100, user_uid: UserUID | None = None
    ) -> Result[builtins.list[T]]:
        """
        Filter entities by status field.

        Args:
            status: EntityStatus enum or status string (e.g., "active", "completed")
            limit: Maximum results to return
            user_uid: Optional user UID to scope results to owner

        Returns:
            Result containing entities with matching status
        """
        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)
        dto_class, model_class = config_result.value

        status_str = status.value if isinstance(status, EntityStatus) else status
        filters: dict[str, Any] = {"status": status_str, "limit": limit}
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(**filters)
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, dto_class, model_class)

        self.logger.debug(
            f"Found {len(entities)} {self.config_lookup_label}(s) with status '{status}'"
        )
        return Result.ok(entities)

    @with_error_handling("get_for_user_filtered", error_type="database")
    async def get_for_user_filtered(
        self, user_uid: UserUID, status_filter: str = "all"
    ) -> Result[builtins.list[T]]:
        """
        Fetch the user's entities with the status filter pushed to Cypher WHERE.

        The filter vocabulary is domain-configured via DomainConfig.status_filters
        (filter-name -> extra find_by kwargs). "all" or an unconfigured name
        applies no status constraint; domains with no status_filters (Principles)
        always return every entity for the user.

        Args:
            user_uid: Owner of the entities (required)
            status_filter: Domain filter name (e.g., "active", "completed")

        Returns:
            Result containing the user's entities matching the filter
        """
        if not user_uid:
            return Result.fail(Errors.validation(message="user_uid is required", field="user_uid"))

        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)
        dto_class, model_class = config_result.value

        status_filters: Mapping[str, FilterParams] = self._get_config_value("status_filters", {})
        # Same call-boundary shape as get_by_status: find_by's **kwargs signature
        # needs a plain dict for unpacking alongside its typed keywords.
        filters: dict[str, Any] = {"user_uid": user_uid, **status_filters.get(status_filter, {})}

        result = await self.backend.find_by(**filters)
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, dto_class, model_class)

        self.logger.debug(
            f"Found {len(entities)} {self.config_lookup_label}(s) for user {user_uid} "
            f"(status_filter={status_filter!r})"
        )
        return Result.ok(entities)

    @with_error_handling("get_by_category", error_type="database")
    async def get_by_category(
        self, category: str, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[builtins.list[T]]:
        """
        Filter entities by category field.

        Uses the DomainConfig-resolved category_field to determine which field to query.

        Args:
            category: Category name to filter by
            user_uid: Optional user filter
            limit: Maximum results to return

        Returns:
            Result containing entities in the specified category
        """
        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)
        dto_class, model_class = config_result.value

        # `has` = exact match on scalar category fields (Goals `domain`),
        # element membership on array fields (Ku/PS `nous` topic lists).
        filters: dict[str, Any] = {f"{self.category_field}__has": category, "limit": limit}
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(**filters)
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, dto_class, model_class)

        self.logger.debug(
            f"Found {len(entities)} {self.config_lookup_label}(s) in {self.category_field} '{category}'"
        )
        return Result.ok(entities)

    @with_error_handling("list_user_categories", error_type="database")
    async def list_user_categories(self, user_uid: UserUID) -> Result[builtins.list[str]]:
        """
        List unique category values for a specific user's entities.

        Args:
            user_uid: Required user identifier

        Returns:
            Result containing list of category strings for this user
        """
        result = await self.backend.distinct_values_raw(
            self.category_field,
            user_uid=user_uid,
        )
        if result.is_error:
            return Result.fail(result)

        categories = [record["value"] for record in result.value if record.get("value")]

        self.logger.debug(
            f"Found {len(categories)} {self.config_lookup_label} categories for user {user_uid}"
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
        result = await self.backend.distinct_values_raw(
            self.category_field,
            user_uid=None,
        )
        if result.is_error:
            return Result.fail(result)

        categories = [record["value"] for record in result.value if record.get("value")]

        self.logger.debug(f"Found {len(categories)} total {self.config_lookup_label} categories")
        return Result.ok(categories)

    @with_error_handling("tag_frequencies", error_type="database")
    async def tag_frequencies(self) -> Result[dict[str, int]]:
        """
        Map each distinct tag on this domain's entities to its usage count.

        The tag-facet vocabulary source (library chips, /search tags filter).
        Mirrors ``list_all_categories`` on the universal ``tags`` array field,
        but keeps the per-tag counts so consumers can rank by usage.

        Backend: ``distinct_values_raw`` UNWINDs array properties, so each
        distinct tag comes back as its own row with an occurrence ``count``.
        """
        result = await self.backend.distinct_values_raw(
            "tags",
            user_uid=None,
        )
        if result.is_error:
            return Result.fail(result)

        frequencies = {
            str(record["value"]): int(record.get("count", 1))
            for record in result.value
            if record.get("value")
        }

        self.logger.debug(f"Found {len(frequencies)} distinct {self.config_lookup_label} tags")
        return Result.ok(frequencies)

    async def count(self, **filters: Any) -> Result[int]:
        """Count entities matching filters."""
        return await self.backend.count(**filters)


# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION (January 2026)
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import SearchOperations

    # Only `type-abstract` remains: the `assignment` half was masking a real
    # conformance error — SearchOperations declared `relationship_type: Any`
    # and `direction: str` where the mixin declares RelationshipName/Direction.
    # With the protocol tightened to match, the mixin conforms for real.
    _protocol_check: type[SearchOperations[Any]] = SearchOperationsMixin  # type: ignore[type-abstract]
