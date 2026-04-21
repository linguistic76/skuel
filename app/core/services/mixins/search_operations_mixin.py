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
        - get_by_domain: Filter by domain enum
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
from typing import TYPE_CHECKING, Any, ClassVar

from core.models.enums import EntityStatus
from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
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
        _search_fields: tuple[str, ...] - Fields to search
        _search_order_by: str - Default sort field
        _category_field: str - Field for categorization
        _dto_class: type[DTOProtocol] - DTO class
        _model_class: type[T] - Domain model class
        _graph_enrichment_patterns: tuple - Graph enrichment config
        _user_ownership_relationship: str | None - Ownership relationship
        _to_domain_models: Conversion method
        _get_config_value: Config accessor method
    """

    # Type hints for attributes that must be provided by composing class
    backend: B
    logger: Logger
    service_name: str
    _search_fields: ClassVar[tuple[str, ...]]
    _search_order_by: str
    _category_field: str
    _dto_class: type[DTOProtocol] | None
    _model_class: type[T] | None
    _graph_enrichment_patterns: ClassVar[
        tuple[tuple[str, str, str] | tuple[str, str, str, str], ...]
    ]
    _user_ownership_relationship: ClassVar[str | None]

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

    def _ensure_configured_for_search(self) -> Result[None]:
        """
        Fail-fast validation: ensure search configuration exists.

        Checks that _dto_class and _model_class are configured, which are
        required for all search operations using CypherGenerator.

        Returns:
            Result.ok(None) if configured, Result.fail() with clear error otherwise
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
        return Result.ok(None)

    # ========================================================================
    # SEARCH AND QUERY OPERATIONS
    # ========================================================================

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

        result = await self.backend.text_search_raw(
            query,
            self._search_fields,
            limit=limit,
            order_by=self._search_order_by,
            order_desc=True,
            user_uid=user_uid,
        )
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

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

        result = await self.backend.relationship_traversal_raw(
            source_uid=related_uid,
            relationship_type=relationship_type.value,
            target_label=self.config_lookup_label,
            direction=direction,
        )
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

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

        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)

        result = await self.backend.graph_aware_search_raw(
            query,
            source_uid=related_uid,
            relationship_type=relationship_type.value,
            search_fields=self._search_fields,
            direction=direction,
            limit=limit,
            order_by=self._search_order_by,
            order_desc=True,
        )
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

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

        result = await self.backend.array_contains_raw(
            field,
            value,
            limit=limit,
            order_by=self._search_order_by,
            order_desc=True,
        )
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

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
        user_uid: UserUID,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Graph-aware faceted search - THE unified method for all domains.

        Combines:
        1. User ownership filter (if _user_ownership_relationship is set)
        2. Property filters from request.to_property_filters()
        3. Text search on _search_fields
        4. Graph pattern enrichment from _graph_enrichment_patterns
        5. Relationship filters from request.to_graph_patterns()

        Args:
            request: SearchRequest with query and facets
            user_uid: User identifier for ownership and graph patterns

        Returns:
            Result[list[dict]]: Results with _graph_context enrichment
        """
        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)

        # Extract request parameters
        property_filters = request.to_property_filters()
        query_text = getattr(request, "query_text", None)
        graph_patterns = request.to_graph_patterns() if request.has_relationship_filters() else None
        limit = getattr(request, "limit", 50)

        result = await self.backend.faceted_search_raw(
            user_uid,
            user_ownership_relationship=self._user_ownership_relationship,
            search_fields=self._search_fields,
            search_order_by=self._search_order_by,
            graph_enrichment_patterns=self._graph_enrichment_patterns,
            property_filters=property_filters,
            query_text=query_text,
            graph_patterns=graph_patterns,
            limit=limit,
        )
        if result.is_error:
            return Result.fail(result)

        # Convert results to dict format with _graph_context
        results = []
        for record in result.value or []:
            entity_data = record.get("entity", {})

            result_dict = dict(entity_data) if isinstance(entity_data, dict) else {}
            result_dict["_domain"] = self.config_lookup_label.lower()

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

        status_str = status.value if isinstance(status, EntityStatus) else status
        filters: dict[str, Any] = {"status": status_str, "limit": limit}
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(**filters)
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(
            f"Found {len(entities)} {self.config_lookup_label}(s) with status '{status}'"
        )
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
        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)

        from core.ports import get_enum_value

        domain_value = get_enum_value(domain)
        result = await self.backend.find_by(domain=domain_value, limit=limit)
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(
            f"Found {len(entities)} {self.config_lookup_label}(s) in domain '{domain_value}'"
        )
        return Result.ok(entities)

    @with_error_handling("get_by_category", error_type="database")
    async def get_by_category(
        self, category: str, user_uid: UserUID | None = None, limit: int = 100
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
        config_result = self._ensure_configured_for_search()
        if config_result.is_error:
            return Result.fail(config_result)

        filters: dict[str, Any] = {self._category_field: category, "limit": limit}
        if user_uid:
            filters["user_uid"] = user_uid

        result = await self.backend.find_by(**filters)
        if result.is_error:
            return Result.fail(result)

        entities = self._to_domain_models(result.value, self._dto_class, self._model_class)

        self.logger.debug(
            f"Found {len(entities)} {self.config_lookup_label}(s) in {self._category_field} '{category}'"
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
            self._category_field,
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
            self._category_field,
            user_uid=None,
        )
        if result.is_error:
            return Result.fail(result)

        categories = [record["value"] for record in result.value if record.get("value")]

        self.logger.debug(f"Found {len(categories)} total {self.config_lookup_label} categories")
        return Result.ok(categories)

    async def count(self, **filters: Any) -> Result[int]:
        """Count entities matching filters."""
        return await self.backend.count(**filters)


# ============================================================================
# PROTOCOL COMPLIANCE VERIFICATION (January 2026)
# ============================================================================
if TYPE_CHECKING:
    from core.ports.base_service_interface import SearchOperations

    _protocol_check: type[SearchOperations[Any]] = SearchOperationsMixin  # type: ignore[type-arg, type-abstract, assignment]
