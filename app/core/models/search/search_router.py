"""
EntityType-Driven Search Router
================================

*Last updated: 2026-02-14*

Type-safe search routing based on EntityType and NonKuDomain enums.

Design Philosophy:
- EntityType/NonKuDomain is the single source of truth for domain classification
- Router maps EntityType/NonKuDomain → SearchService automatically
- Eliminates manual dispatch logic scattered across codebase
- Provides unified entry point for cross-domain search

Architecture:
    EntityType/NonKuDomain (enum) → SearchRouter → DomainSearchService
                                      ↓
                                PriorityScore (unified scoring)

Key Features:
1. Type-safe routing via EntityType/NonKuDomain pattern matching
2. Automatic service discovery from Services container
3. Unified search results with domain tagging
4. Cross-domain search with merged results
5. Integration with unified scoring framework

One Path Forward (January 2026):
    SearchRequest is THE canonical search request model. UnifiedSearchRequest
    was merged into SearchRequest. All advanced_search calls use SearchRequest.

Usage:
    from core.models.search import SearchRouter, UnifiedSearchResult
    from core.models.search_request import SearchRequest

    # Initialize router with services
    router = SearchRouter(services)

    # Route by EntityType
    result = await router.search(EntityType.TASK, "urgent deadline")

    # Search across multiple domains
    results = await router.search_domains(
        [EntityType.TASK, EntityType.GOAL, EntityType.HABIT],
        "health fitness"
    )

    # Unified cross-domain search
    results = await router.unified_search("urgent health tasks")

    # Advanced search with graph and tag filters
    request = SearchRequest(
        query_text="machine learning",
        entity_types=[EntityType.CURRICULUM],
        connected_to_uid="ku.python-basics",
        connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
        tags_contain=["python"],
    )
    result = await router.advanced_search(request)

Version: 3.0.0
Date: 2026-02-14
Changes:
- v3.0.0: EntityType migrated to EntityType/NonKuDomain (One Path Forward)
- v2.0.0: UnifiedSearchRequest merged into SearchRequest (One Path Forward)
- v1.0.0: Initial implementation
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.ports.search_protocols import (
    SupportsGraphAwareSearch,
    SupportsGraphTraversalSearch,
    SupportsTagSearch,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_combined_score, get_dict_score

if TYPE_CHECKING:
    from core.models.search.query_parser import ParsedSearchQuery
    from core.models.search_request import SearchRequest, SearchResponse
    from core.services.user import UserContext
    from services_bootstrap import Services

T = TypeVar("T")

logger = get_logger(__name__)


# =============================================================================
# UNIFIED SEARCH RESULT - Cross-domain result container
# =============================================================================


@dataclass(frozen=True)
class SearchResultItem:
    """
    Individual search result with domain context.

    Wraps any domain entity with metadata about the search.
    """

    entity: Any  # Task, Goal, Habit, Event, Choice, Principle, etc.
    entity_type: EntityType | NonKuDomain
    uid: str
    title: str
    relevance_score: float = 0.0  # Text search relevance
    priority_score: float = 0.0  # Unified priority score
    match_reason: str = ""  # Why this matched

    @property
    def combined_score(self) -> float:
        """Get combined relevance + priority score."""
        return (self.relevance_score * 0.6) + (self.priority_score * 0.4)


@dataclass(frozen=True)
class UnifiedSearchResult:
    """
    Results from a cross-domain search.

    Contains results grouped by domain plus merged top results.
    """

    query: str
    parsed_query: "ParsedSearchQuery | None" = None
    results_by_domain: dict[EntityType | NonKuDomain, list[SearchResultItem]] = field(
        default_factory=dict
    )
    total_count: int = 0

    @property
    def top_results(self) -> list[SearchResultItem]:
        """Get top 10 results across all domains, sorted by combined score."""
        all_results = []
        for items in self.results_by_domain.values():
            all_results.extend(items)
        return sorted(all_results, key=get_combined_score, reverse=True)[:10]

    @property
    def domains_searched(self) -> list[EntityType | NonKuDomain]:
        """Get list of domains that returned results."""
        return [k for k, v in self.results_by_domain.items() if v]

    def get_domain_results(self, entity_type: EntityType | NonKuDomain) -> list[SearchResultItem]:
        """Get results for a specific domain."""
        return self.results_by_domain.get(entity_type, [])

    def summary(self) -> str:
        """Generate human-readable result summary."""
        parts = [f"Search: '{self.query}'"]
        parts.append(f"Total: {self.total_count} results")
        for domain, items in self.results_by_domain.items():
            if items:
                parts.append(f"  • {domain.value}: {len(items)}")
        return "\n".join(parts)


# =============================================================================
# SEARCHABLE PROTOCOL - Interface for domain search services
# =============================================================================


class SearchableService(Protocol[T]):
    """
    Protocol for services that support search operations.

    All 6 Activity Domain search services implement this interface.
    """

    async def search(self, query: str, limit: int = 50) -> Result[list[T]]:
        """Text search on title and description."""
        ...


# =============================================================================
# SEARCH ROUTER - EntityType/NonKuDomain-driven dispatch
# =============================================================================


class SearchRouter:
    """
    Routes search requests to appropriate domain services based on EntityType/NonKuDomain.

    Provides a unified entry point for searching across SKUEL's 15 domains,
    with automatic service discovery and result aggregation.

    The router uses EntityType/NonKuDomain enums for type-safe dispatch, eliminating
    stringly-typed domain checks scattered across the codebase.

    Example:
        router = SearchRouter(services)

        # Search single domain
        tasks = await router.search(EntityType.TASK, "urgent")

        # Search multiple domains
        results = await router.search_domains(
            [EntityType.TASK, EntityType.GOAL],
            "health fitness"
        )

        # Intelligent cross-domain search
        results = await router.intelligent_search(
            "show me urgent health tasks",
            user_context
        )
    """

    # Mapping of EntityType/NonKuDomain to Services attribute name
    # This enables automatic service discovery from Services container
    # Note: Attribute names follow consistent plural pattern for activity domains
    _SERVICE_REGISTRY: dict[EntityType | NonKuDomain, str] = {
        # Activity Domains (6) - have dedicated search services (all plural)
        EntityType.TASK: "tasks",
        EntityType.GOAL: "goals",
        EntityType.HABIT: "habits",
        EntityType.EVENT: "events",
        EntityType.CHOICE: "choices",
        EntityType.PRINCIPLE: "principles",
        # Finance (singular - standalone domain group)
        NonKuDomain.FINANCE: "finance",
        # Curriculum Domains (3) - ku, ls, lp form the knowledge foundation
        EntityType.CURRICULUM: "ku",
        EntityType.LEARNING_STEP: "learning_steps",
        EntityType.LEARNING_PATH: "learning_paths",
        # Content/Organization Domains
        EntityType.SUBMISSION: "reports",
        # The Destination - LifePath
        # "Everything flows toward the life path"
        EntityType.LIFE_PATH: "lifepath",
        # Cross-cutting Systems (not domains)
        NonKuDomain.CALENDAR: "calendar",  # Aggregation: Tasks + Events + Habits + Goals
    }

    # EntityTypes that support DomainSearchOperations[T] protocol
    _SEARCHABLE_DOMAINS: frozenset[EntityType] = frozenset(
        {
            # Activity Domains (6)
            EntityType.TASK,
            EntityType.GOAL,
            EntityType.HABIT,
            EntityType.EVENT,
            EntityType.CHOICE,
            EntityType.PRINCIPLE,
            # Curriculum Domains (3) - KU, LS, LP
            EntityType.CURRICULUM,
            EntityType.LEARNING_STEP,
            EntityType.LEARNING_PATH,
        }
    )

    def __init__(self, services: "Services") -> None:
        """
        Initialize router with service container.

        Args:
            services: Bootstrapped Services container with all domain services
        """
        self.services = services
        self.logger = get_logger(__name__)

    def get_service(self, entity_type: EntityType | NonKuDomain) -> Any | None:
        """
        Get the appropriate service for a EntityType or NonKuDomain.

        Args:
            entity_type: The domain to get service for

        Returns:
            Service instance or None if not found/not initialized
        """
        attr_name = self._SERVICE_REGISTRY.get(entity_type)

        if not attr_name:
            self.logger.warning(f"No service registered for domain: {entity_type}")
            return None

        service = getattr(self.services, attr_name, None)
        if service is None:
            self.logger.debug(f"Service '{attr_name}' not initialized for {entity_type}")

        return service

    def supports_search(self, entity_type: EntityType | NonKuDomain) -> bool:
        """
        Check if a EntityType or NonKuDomain supports the DomainSearchOperations protocol.

        Args:
            entity_type: EntityType or NonKuDomain to check

        Returns:
            True if this domain has a search service implementing the protocol
        """
        return entity_type in self._SEARCHABLE_DOMAINS

    async def search(
        self,
        entity_type: EntityType | NonKuDomain,
        query: str,
        limit: int = 50,
    ) -> Result[list[Any]]:
        """
        Search within a single domain.

        Routes the search to the appropriate domain service based on EntityType/NonKuDomain.

        Args:
            entity_type: Domain to search in
            query: Search query string
            limit: Maximum results to return

        Returns:
            Result containing list of domain entities
        """
        # Type-safe check: only searchable domains proceed
        if not self.supports_search(entity_type):
            return Result.fail(
                Errors.validation(
                    field="entity_type",
                    message=f"{entity_type.value} does not support search",
                )
            )

        service = self.get_service(entity_type)
        if service is None:
            return Result.fail(
                Errors.not_found(
                    resource=f"{entity_type.value}_search_service",
                    identifier=entity_type.value,
                )
            )

        try:
            # Get the search service (might be a sub-service for Activity Domains)
            search_service = self._get_search_service(service, entity_type)
            if search_service is None:
                search_service = service

            return await search_service.search(query, limit)

        except Exception as e:
            self.logger.error(f"Search failed for {entity_type.value}: {e}")
            return Result.fail(Errors.database(operation="search", message=str(e)))

    def _get_search_service(
        self, service: Any, entity_type: EntityType | NonKuDomain
    ) -> Any | None:
        """
        Get the search sub-service from a domain service.

        Activity Domain services have a .search property that returns
        the SearchService (e.g., TasksService.search → TasksSearchService).

        Args:
            service: Domain service instance
            entity_type: EntityType or NonKuDomain for logging

        Returns:
            Search service or None

        Note:
            This method is only called after supports_search() validation,
            so entity_type is guaranteed to be in _SEARCHABLE_DOMAINS.
            Activity Domain services expose search via a .search property.
        """
        # Activity Domain pattern: .search is a property returning SearchService
        # Access directly - supports_search() already validated this is a searchable domain
        search_attr = getattr(service, "search", None)

        # If .search is a property (not a method), it returns the search sub-service
        if search_attr is not None and not callable(search_attr):
            return search_attr

        # Fall back to the service itself (service implements search directly)
        return None

    async def search_domains(
        self,
        entity_types: list[EntityType | NonKuDomain],
        query: str,
        limit_per_domain: int = 20,
    ) -> UnifiedSearchResult:
        """
        Search across multiple domains.

        Performs parallel searches across specified domains and aggregates results.

        Args:
            entity_types: List of domains to search
            query: Search query string
            limit_per_domain: Max results per domain

        Returns:
            UnifiedSearchResult with results grouped by domain
        """
        results_by_domain: dict[EntityType | NonKuDomain, list[SearchResultItem]] = {}
        total_count = 0

        for entity_type in entity_types:
            if not self.supports_search(entity_type):
                continue

            result = await self.search(entity_type, query, limit_per_domain)
            if result.is_ok and result.value:
                items = self._wrap_results(result.value, entity_type)
                results_by_domain[entity_type] = items
                total_count += len(items)

        return UnifiedSearchResult(
            query=query,
            results_by_domain=results_by_domain,
            total_count=total_count,
        )

    # =========================================================================
    # FACETED SEARCH - One Path Forward (Complete)
    # =========================================================================

    async def faceted_search(
        self,
        request: "SearchRequest",
        user_uid: str | None = None,
    ) -> Result["SearchResponse"]:
        """
        Faceted search - THE entry point for all UI-driven search.

        One Path Forward: All search flows through SearchRouter.

        Strategy:
        1. Activity Domains (with user) → graph_aware_faceted_search()
        2. Curriculum Domains → simple text search via domain service
        3. Cross-domain (no domain) → aggregate from multiple domains

        Args:
            request: SearchRequest with query and facets
            user_uid: User identifier for personalized graph patterns

        Returns:
            Result[SearchResponse] with results

        Example:
            request = SearchRequest(
                query_text="meditation",
                domain=Domain.HEALTH,
            )
            result = await router.faceted_search(request, user_uid="user_123")
        """
        from datetime import datetime

        from core.models.search_request import SearchResponse

        start_time = datetime.now()

        try:
            # Route 1: Single domain specified
            if request.domain:
                domain_str = (
                    request.domain if isinstance(request.domain, str) else request.domain.value
                )

                # Graph-aware domains (Activity + KU) with user → graph_aware_faceted_search
                # January 2026: Unified search for Activity Domains + Curriculum Domains
                if domain_str in self._GRAPH_AWARE_DOMAINS and user_uid:
                    result = await self._graph_aware_domain_search(request, user_uid, domain_str)
                    if result is not None:
                        return result

                # Curriculum or other domains → simple text search
                result = await self._simple_domain_search(request, domain_str)
                if result is not None:
                    return result

            # Route 2: Cross-domain search (no domain specified)
            result = await self._cross_domain_search(request)
            search_time = (datetime.now() - start_time).total_seconds() * 1000
            return Result.ok(
                SearchResponse(
                    results=result,
                    total=len(result),
                    limit=request.limit,
                    offset=request.offset,
                    query_text=request.query_text,
                    domain=None,
                    facet_counts={},
                    applied_filters=request.to_neo4j_filters(),
                    search_time_ms=search_time,
                )
            )

        except Exception as e:
            self.logger.error(f"Faceted search failed: {e}")
            return Result.fail(Errors.database(operation="faceted_search", message=str(e)))

    # Domains that support graph_aware_faceted_search (January 2026 - Unified Search)
    # Includes Activity Domains + All Curriculum Domains (KU, LS, LP)
    # One Path Forward: All domains use the same search pattern
    _GRAPH_AWARE_DOMAINS: frozenset[str] = frozenset(
        {"tasks", "goals", "habits", "events", "choices", "principles", "ku", "ls", "lp"}
    )

    async def _graph_aware_domain_search(
        self,
        request: "SearchRequest",
        user_uid: str,
        domain_str: str,
    ) -> Result["SearchResponse"] | None:
        """
        Graph-aware search for domains that support graph_aware_faceted_search.

        Works for both Activity Domains (Tasks, Goals, etc.) and Curriculum Domains (KU).

        January 2026: Unified search architecture - One Path Forward.
        """
        from datetime import datetime

        from core.models.search_request import SearchResponse

        # Map domain to service attribute
        service_attr = domain_str  # tasks, goals, ku, etc.
        domain_service = getattr(self.services, service_attr, None)
        if domain_service is None:
            return None

        search_service = getattr(domain_service, "search", None)
        if search_service is None or not isinstance(search_service, SupportsGraphAwareSearch):
            return None

        self.logger.debug(f"Graph-aware domain search: {domain_str}")
        start_time = datetime.now()

        result = await search_service.graph_aware_faceted_search(
            request=request,
            user_uid=user_uid,
        )

        if result.is_error:
            self.logger.warning(f"Graph-aware domain search failed: {result.error}")
            return None

        search_time = (datetime.now() - start_time).total_seconds() * 1000
        return Result.ok(
            SearchResponse(
                results=result.value,
                total=len(result.value),
                limit=request.limit,
                offset=request.offset,
                query_text=request.query_text,
                domain=domain_str,
                facet_counts={},
                applied_filters=request.to_neo4j_filters(),
                search_time_ms=search_time,
            )
        )

    async def _simple_domain_search(
        self,
        request: "SearchRequest",
        domain_str: str,
    ) -> Result["SearchResponse"] | None:
        """Simple text search for curriculum and other domains."""
        from datetime import datetime

        from core.models.search_request import SearchResponse

        # Map domain string to EntityType
        domain_to_entity = {
            "knowledge": EntityType.CURRICULUM,
            "ku": EntityType.CURRICULUM,
            "ls": EntityType.LEARNING_STEP,
            "lp": EntityType.LEARNING_PATH,
        }

        entity_type = domain_to_entity.get(domain_str.lower())
        if entity_type is None:
            return None

        self.logger.debug(f"Simple domain search: {domain_str} → {entity_type}")
        start_time = datetime.now()

        # Use SearchRouter.search() which delegates to domain service
        result = await self.search(entity_type, request.query_text or "", request.limit)

        if result.is_error:
            self.logger.warning(f"Simple domain search failed: {result.error}")
            return None

        # Convert domain entities to dict format for SearchResponse
        results = [
            {
                "uid": getattr(entity, "uid", ""),
                "title": getattr(entity, "title", ""),
                "summary": getattr(entity, "summary", ""),
                "_domain": domain_str,
                "tags": getattr(entity, "tags", []),
            }
            for entity in result.value or []
        ]

        search_time = (datetime.now() - start_time).total_seconds() * 1000
        return Result.ok(
            SearchResponse(
                results=results,
                total=len(results),
                limit=request.limit,
                offset=request.offset,
                query_text=request.query_text,
                domain=domain_str,
                facet_counts={},
                applied_filters=request.to_neo4j_filters(),
                search_time_ms=search_time,
            )
        )

    async def _cross_domain_search(
        self,
        request: "SearchRequest",
    ) -> list[dict]:
        """Search across multiple domains and aggregate results."""
        # Search all searchable domains
        unified_result = await self.search_domains(
            list(self._SEARCHABLE_DOMAINS),
            request.query_text or "",
            limit_per_domain=max(5, request.limit // 6),
        )

        # Convert to flat list of dicts
        results: list[dict] = []
        for entity_type, items in unified_result.results_by_domain.items():
            results.extend(
                {
                    "uid": item.uid,
                    "title": item.title,
                    "_domain": entity_type.value,
                    "_score": item.combined_score,
                }
                for item in items
            )

        # Sort by score and limit
        results.sort(key=get_dict_score, reverse=True)
        return results[: request.limit]

    async def intelligent_search(
        self,
        query: str,
        user_context: "UserContext | None" = None,
        limit: int = 50,
    ) -> Result[UnifiedSearchResult]:
        """
        Intelligent cross-domain search with semantic filter extraction.

        Uses SearchQueryParser to extract semantic filters (priority, status, domain)
        from natural language queries, then routes to appropriate domains.

        Args:
            query: Natural language search query
            user_context: Optional user context for personalization
            limit: Maximum total results

        Returns:
            Result containing UnifiedSearchResult with parsed query info
        """
        from core.models.search.query_parser import SearchQueryParser

        try:
            # Parse query for semantic filters
            parser = SearchQueryParser()
            parsed = parser.parse(query)

            # Determine which domains to search
            target_domains = self._determine_target_domains(parsed)

            # Perform searches
            limit_per_domain = max(10, limit // len(target_domains)) if target_domains else limit
            results_by_domain: dict[EntityType | NonKuDomain, list[SearchResultItem]] = {}
            total_count = 0

            for entity_type in target_domains:
                result = await self.search(entity_type, parsed.text_query, limit_per_domain)
                if result.is_ok and result.value:
                    items = self._wrap_results(result.value, entity_type)

                    # Apply semantic filters
                    items = self._apply_semantic_filters(items, parsed)

                    # Score with unified framework if user_context available
                    if user_context:
                        items = self._score_results(items, user_context)

                    results_by_domain[entity_type] = items
                    total_count += len(items)

            return Result.ok(
                UnifiedSearchResult(
                    query=query,
                    parsed_query=parsed,
                    results_by_domain=results_by_domain,
                    total_count=total_count,
                )
            )

        except Exception as e:
            self.logger.error(f"Intelligent search failed: {e}")
            return Result.fail(Errors.database(operation="intelligent_search", message=str(e)))

    def _determine_target_domains(
        self,
        parsed: "ParsedSearchQuery",
    ) -> list[EntityType | NonKuDomain]:
        """
        Determine which domains to search based on parsed query.

        Uses extracted semantic filters to narrow down search scope.
        """
        # If domains explicitly mentioned, use those
        if parsed.domains:
            target_domains: list[EntityType | NonKuDomain] = []
            for domain in parsed.domains:
                # Map Domain enum to EntityType
                domain_to_entity = {
                    "tasks": EntityType.TASK,
                    "goals": EntityType.GOAL,
                    "habits": EntityType.HABIT,
                    "events": EntityType.EVENT,
                    "choices": EntityType.CHOICE,
                    "principles": EntityType.PRINCIPLE,
                    "health": EntityType.HABIT,  # Health often relates to habits
                    "tech": EntityType.TASK,  # Tech often relates to tasks
                }
                entity = domain_to_entity.get(domain.value)
                if entity and entity not in target_domains:
                    target_domains.append(entity)
            if target_domains:
                return list(target_domains)

        # Default: search all 6 activity domains
        return list(self._SEARCHABLE_DOMAINS)

    async def advanced_search(
        self,
        request: "SearchRequest",
        user_context: "UserContext | None" = None,
    ) -> Result[UnifiedSearchResult]:
        """
        Advanced unified search combining text, graph, and array filters.

        This is the flagship search method, combining all -3 capabilities:
        - Text search on configured fields
        - Graph-aware filtering (relationship traversal)
        - Tag/array filtering (AND/OR semantics)

        The method optimizes by choosing the right query strategy:
        1. If graph filter: Use search_connected_to() for each domain
        2. If tag filter only: Use search_by_tags() then text filter
        3. If text only: Use search() directly

        Args:
            request: SearchRequest with all search criteria (THE canonical model)
            user_context: Optional user context for scoring

        Returns:
            Result containing UnifiedSearchResult with matched entities

        Example:
            from core.models.search_request import SearchRequest

            request = SearchRequest(
                query_text="machine learning",
                entity_types=[EntityType.CURRICULUM],
                connected_to_uid="ku.python-basics",
                connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
                tags_contain=["python"],
            )
            result = await router.advanced_search(request, user_context)
        """
        try:
            # Determine target domains
            target_domains = (
                request.entity_types
                if request.has_entity_type_filter()
                else list(self._SEARCHABLE_DOMAINS)
            )

            results_by_domain: dict[EntityType | NonKuDomain, list[SearchResultItem]] = {}
            total_count = 0

            for entity_type in target_domains:
                if not self.supports_search(entity_type):
                    continue

                service = self.get_service(entity_type)
                if service is None:
                    continue

                # Get the search service
                search_service = self._get_search_service(service, entity_type)
                if search_service is None:
                    search_service = service

                # Choose search strategy based on filters
                items = await self._execute_advanced_search(
                    search_service=search_service,
                    entity_type=entity_type,
                    request=request,
                )

                if items:
                    # Apply scoring if user context available
                    if user_context:
                        items = self._score_results(items, user_context)

                    results_by_domain[entity_type] = items
                    total_count += len(items)

            return Result.ok(
                UnifiedSearchResult(
                    query=request.query_text or "",
                    results_by_domain=results_by_domain,
                    total_count=total_count,
                )
            )

        except Exception as e:
            self.logger.error(f"Advanced search failed: {e}")
            return Result.fail(Errors.database(operation="advanced_search", message=str(e)))

    async def _execute_advanced_search(
        self,
        search_service: Any,
        entity_type: EntityType | NonKuDomain,
        request: "SearchRequest",
    ) -> list[SearchResultItem]:
        """
        Execute the appropriate search strategy based on request filters.

        Strategy selection:
        0. Semantic/Learning-Aware: Use vector search with boosting
        1. Graph + Text: Use search_connected_to if available
        2. Tags + Text: Use search_by_tags, then filter by text
        3. Text only: Use search directly
        """
        items: list[SearchResultItem] = []

        # Calculate per-domain limit
        limit_per_domain = request.limit // max(len(request.entity_types), 1)
        limit_per_domain = max(limit_per_domain, 10)  # Minimum 10 per domain

        # Strategy 0: Semantic-enhanced or learning-aware search
        if request.has_semantic_boost() or request.has_learning_aware():
            items = await self._semantic_or_learning_search(
                entity_type=entity_type, request=request, limit=limit_per_domain
            )
            # If semantic/learning search succeeded, return those results
            if items:
                return items
            # Otherwise fall through to standard search

        # Strategy 1: Graph-aware search
        if request.has_graph_traversal_filter():
            if isinstance(search_service, SupportsGraphTraversalSearch):
                result = await search_service.search_connected_to(
                    query=request.query_text or "",
                    related_uid=request.connected_to_uid,
                    relationship_type=request.connected_relationship,
                    direction=request.connected_direction,
                    limit=limit_per_domain,
                )
                if result.is_ok and result.value:
                    items = self._wrap_results(result.value, entity_type)

                    # Apply tag filter on results if specified
                    if request.has_tag_filter():
                        items = self._filter_by_tags_from_request(items, request)
            else:
                # Fallback: text search then filter (less efficient)
                self.logger.debug(
                    f"Service {entity_type} doesn't support search_connected_to, using fallback"
                )
                items = await self._fallback_search(
                    search_service, entity_type, request, limit_per_domain
                )

        # Strategy 2: Tag search
        elif request.has_tag_filter():
            if isinstance(search_service, SupportsTagSearch):
                result = await search_service.search_by_tags(
                    tags=request.tags_contain,
                    match_all=request.tags_match_all,
                    limit=limit_per_domain * 2,  # Get more, then filter by text
                )
                if result.is_ok and result.value:
                    items = self._wrap_results(result.value, entity_type)

                    # Apply text filter on results
                    if request.query_text:
                        items = self._filter_by_text(items, request.query_text)
                        items = items[:limit_per_domain]
            else:
                # Fallback: text search (tags not supported)
                self.logger.debug(
                    f"Service {entity_type} doesn't support search_by_tags, using text search"
                )
                items = await self._fallback_search(
                    search_service, entity_type, request, limit_per_domain
                )

        # Strategy 3: Text search only
        else:
            result = await search_service.search(request.query_text or "", limit_per_domain)
            if result.is_ok and result.value:
                items = self._wrap_results(result.value, entity_type)

        return items

    async def _fallback_search(
        self,
        search_service: Any,
        entity_type: EntityType | NonKuDomain,
        request: "SearchRequest",
        limit_per_domain: int,
    ) -> list[SearchResultItem]:
        """
        Fallback search when advanced features not available.

        Uses basic text search and post-filters results.
        """
        result = await search_service.search(request.query_text or "", limit_per_domain * 2)
        if not result.is_ok or not result.value:
            return []

        items = self._wrap_results(result.value, entity_type)

        # Apply tag filter if specified
        if request.has_tag_filter():
            items = self._filter_by_tags_from_request(items, request)

        return items[:limit_per_domain]

    async def _semantic_or_learning_search(
        self,
        entity_type: EntityType | NonKuDomain,
        request: "SearchRequest",
        limit: int,
    ) -> list[SearchResultItem]:
        """
        Execute semantic-enhanced or learning-aware vector search.

        Uses Neo4jVectorSearchService to perform context-aware or personalized search.
        Falls back gracefully if vector search is unavailable.

        Args:
            entity_type: Target EntityType or NonKuDomain (currently only Ku supported for learning-aware)
            request: SearchRequest with semantic/learning-aware flags
            limit: Max results per domain

        Returns:
            List of SearchResultItem with semantic boost metadata
        """
        # Check if vector search service available
        if getattr(self.services, "vector_search_service", None) is None:
            self.logger.warning(
                "Vector search service not available, falling back to standard search"
            )
            return []

        vector_search = self.services.vector_search_service
        if vector_search is None:
            return []
        assert vector_search is not None  # mypy narrowing

        # Must have query text for vector search
        if not request.query_text:
            self.logger.debug("Vector search requires query_text, skipping")
            return []

        # Get label from entity type
        label = entity_type.value.capitalize()  # Task -> "Task", ku -> "Entity"

        try:
            # Choose search method based on flags
            if request.has_semantic_boost():
                # Semantic-enhanced search (context-aware)
                result = await vector_search.semantic_enhanced_search(
                    label=label,
                    text=request.query_text,
                    context_uids=request.context_uids,
                    limit=limit,
                )
            elif request.has_learning_aware():
                # Learning-aware search (personalized)
                # Requires user_uid
                if not request.user_uid:
                    self.logger.warning("Learning-aware search requires user_uid, skipping")
                    return []

                result = await vector_search.learning_aware_search(
                    label=label,
                    text=request.query_text,
                    user_uid=request.user_uid,
                    prefer_unmastered=request.prefer_unmastered,
                    limit=limit,
                )
            else:
                # Shouldn't reach here, but fall back to standard
                return []

            # Handle result
            if result.is_error:
                self.logger.warning(f"Vector search failed: {result.expect_error()}")
                return []

            if not result.value:
                return []

            # Wrap vector search results as SearchResultItems
            items = []
            for vec_result in result.value:
                node = vec_result["node"]
                score = vec_result["score"]

                # Create SearchResultItem with semantic metadata
                item = SearchResultItem(
                    entity=node,  # The node dict
                    entity_type=entity_type,
                    uid=node.get("uid", ""),
                    title=node.get("title", ""),
                    relevance_score=score,  # Use vector/semantic score as relevance
                    priority_score=node.get("priority_score", 0.0),
                    match_reason=self._create_match_reason(vec_result, request),
                )
                items.append(item)

            self.logger.info(
                f"Semantic/learning-aware search returned {len(items)} results for {entity_type}"
            )
            return items

        except Exception as e:
            self.logger.error(f"Semantic/learning-aware search failed: {e}")
            return []  # Graceful degradation

    def _create_match_reason(self, vec_result: dict, request: "SearchRequest") -> str:
        """
        Create human-readable match reason from vector search result.

        Args:
            vec_result: Vector search result dict
            request: Original search request

        Returns:
            Match reason string explaining why this result matched
        """
        reasons = []

        # Vector similarity
        vector_score = vec_result.get("vector_score")
        if vector_score:
            reasons.append(f"Text match: {vector_score:.0%}")

        # Semantic boost
        semantic_boost = vec_result.get("semantic_boost")
        if semantic_boost and semantic_boost > 0:
            reasons.append(f"Related to context: +{semantic_boost:.0%}")

        # Learning state
        learning_state = vec_result.get("learning_state")
        if learning_state:
            state_labels = {
                "mastered": "Already mastered",
                "in_progress": "Currently learning",
                "viewed": "Previously viewed",
                "none": "Not started",
            }
            label = state_labels.get(learning_state, learning_state)
            reasons.append(f"{label}")

        return ", ".join(reasons) if reasons else "Matched query"

    def _filter_by_tags_from_request(
        self,
        items: list[SearchResultItem],
        request: "SearchRequest",
    ) -> list[SearchResultItem]:
        """
        Post-filter results by tags.

        Used when graph search was performed but tag filter also specified.
        """
        if not request.tags_contain:
            return items

        filtered = []
        for item in items:
            entity_tags = getattr(item.entity, "tags", None)
            if entity_tags is None:
                continue

            # Normalize to list
            if isinstance(entity_tags, list | tuple):
                tags_list = [t.lower() for t in entity_tags]
            else:
                continue

            search_tags = [t.lower() for t in request.tags_contain]

            if request.tags_match_all:
                # AND: all tags must be present
                if all(any(st in tag for tag in tags_list) for st in search_tags):
                    filtered.append(item)
            else:
                # OR: any tag matches
                if any(any(st in tag for tag in tags_list) for st in search_tags):
                    filtered.append(item)

        return filtered

    def _filter_by_text(
        self,
        items: list[SearchResultItem],
        query: str,
    ) -> list[SearchResultItem]:
        """
        Post-filter results by text query.

        Used when tag search was performed but text filter also specified.
        """
        if not query:
            return items

        query_lower = query.lower()
        filtered = []

        for item in items:
            # Check title
            if query_lower in item.title.lower():
                filtered.append(item)
                continue

            # Check description if available
            description = getattr(item.entity, "description", "") or ""
            if query_lower in description.lower():
                filtered.append(item)
                continue

            # Check content if available (for KU)
            content = getattr(item.entity, "content", "") or ""
            if query_lower in content.lower():
                filtered.append(item)
                continue

        return filtered

    def _wrap_results(
        self,
        entities: list[Any],
        entity_type: EntityType | NonKuDomain,
    ) -> list[SearchResultItem]:
        """
        Wrap domain entities in SearchResultItem containers.
        """
        items = []
        for entity in entities:
            uid = getattr(entity, "uid", "") or ""
            title = getattr(entity, "title", "") or getattr(entity, "name", "") or str(entity)

            items.append(
                SearchResultItem(
                    entity=entity,
                    entity_type=entity_type,
                    uid=uid,
                    title=title,
                )
            )

        return items

    def _apply_semantic_filters(
        self,
        items: list[SearchResultItem],
        parsed: "ParsedSearchQuery",
    ) -> list[SearchResultItem]:
        """
        Filter results based on extracted semantic filters.

        Applies priority, status, and other filters from ParsedSearchQuery.
        """
        if not parsed.has_filters():
            return items

        filtered = []
        for item in items:
            entity = item.entity

            # Check priority filter
            if parsed.priorities:
                entity_priority = getattr(entity, "priority", None)
                if entity_priority:
                    from core.ports import get_enum_value

                    priority_value = get_enum_value(entity_priority)
                    if priority_value not in [p.value for p in parsed.priorities]:
                        continue

            # Check status filter
            if parsed.statuses:
                entity_status = getattr(entity, "status", None)
                if entity_status:
                    from core.ports import get_enum_value

                    status_value = get_enum_value(entity_status)
                    if status_value not in [s.value for s in parsed.statuses]:
                        continue

            filtered.append(item)

        return filtered

    def _score_results(
        self,
        items: list[SearchResultItem],
        user_context: "UserContext",
    ) -> list[SearchResultItem]:
        """
        Score results using unified scoring framework.
        """
        from core.models.search.scoring import (
            score_choice,
            score_event,
            score_goal,
            score_habit,
            score_principle,
            score_task,
        )

        scored_items = []
        for item in items:
            score = 0.0

            # Use appropriate scoring function based on entity type
            try:
                match item.entity_type:
                    case EntityType.TASK:
                        priority_score = score_task(item.entity, user_context)
                        score = priority_score.total
                    case EntityType.GOAL:
                        priority_score = score_goal(item.entity, user_context)
                        score = priority_score.total
                    case EntityType.HABIT:
                        priority_score = score_habit(item.entity, user_context)
                        score = priority_score.total
                    case EntityType.EVENT:
                        priority_score = score_event(item.entity, user_context)
                        score = priority_score.total
                    case EntityType.CHOICE:
                        priority_score = score_choice(item.entity, user_context)
                        score = priority_score.total
                    case EntityType.PRINCIPLE:
                        priority_score = score_principle(item.entity, user_context)
                        score = priority_score.total
            except Exception as e:
                self.logger.debug(f"Scoring failed for {item.uid}: {e}")

            # Create new item with score
            scored_items.append(
                SearchResultItem(
                    entity=item.entity,
                    entity_type=item.entity_type,
                    uid=item.uid,
                    title=item.title,
                    relevance_score=item.relevance_score,
                    priority_score=score,
                    match_reason=item.match_reason,
                )
            )

        # Sort by combined score
        return sorted(scored_items, key=get_combined_score, reverse=True)


# =============================================================================
# DOMAIN TYPE EXTENSIONS - Add search routing to EntityType/NonKuDomain
# =============================================================================


def get_search_service_attr(entity_type: EntityType | NonKuDomain) -> str | None:
    """
    Get the Services attribute name for a given EntityType/NonKuDomain's search service.

    This function provides the mapping between EntityType/NonKuDomain and the
    corresponding attribute name in the Services container.

    Args:
        entity_type: EntityType or NonKuDomain to look up

    Returns:
        Attribute name (e.g., "tasks" for EntityType.TASK) or None

    Example:
        attr = get_search_service_attr(EntityType.TASK)
        service = getattr(services, attr) # Gets TasksService
    """
    return SearchRouter._SERVICE_REGISTRY.get(entity_type)


def is_searchable_domain(entity_type: EntityType | NonKuDomain) -> bool:
    """
    Check if a EntityType or NonKuDomain represents a searchable domain.

    Searchable domains implement the DomainSearchOperations[T] protocol
    and have dedicated search services.

    Args:
        entity_type: EntityType or NonKuDomain to check

    Returns:
        True if the domain supports search operations
    """
    return entity_type in SearchRouter._SEARCHABLE_DOMAINS
