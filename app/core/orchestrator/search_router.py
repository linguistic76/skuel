"""
EntityType-Driven Search Router
================================

Application orchestrator for cross-domain search — THE single path for all
external search access (SEARCH_ARCHITECTURE).

Design Philosophy:
- EntityType/NonKuDomain is the single source of truth for domain classification
- Router maps EntityType/NonKuDomain → SearchService automatically
- Eliminates manual dispatch logic scattered across codebase
- Provides unified entry point for cross-domain search

Architecture:
    EntityType/NonKuDomain (enum) → SearchRouter → DomainSearchService
                                      ↓
                                PriorityScore (unified scoring)

Dependencies are explicit constructor parameters (one per routed domain, plus
user/vector-search/event-bus infrastructure). Every parameter name matches the
``Services`` container field the composition root reads it from — guarded by
``tests/unit/models/test_search_router_registry.py``. All are optional and the
router fails soft per domain: a missing service contributes no results rather
than failing the search (CORE tier has no vector service; finance/calendar may
be absent).

One Path Forward (January 2026):
    SearchRequest is THE canonical search request model. UnifiedSearchRequest
    was merged into SearchRequest. All advanced_search calls use SearchRequest.

Usage:
    from core.orchestrator.search_router import SearchRouter
    from core.models.search_request import SearchRequest

    # Initialize router with the domain services it should route across
    router = SearchRouter(tasks=tasks_service, ku=ku_service, event_bus=bus)

    # Route by EntityType
    result = await router.search(EntityType.TASK, "urgent deadline")

    # Search across multiple domains
    results = await router.search_domains(
        [EntityType.TASK, EntityType.GOAL, EntityType.HABIT],
        "health fitness"
    )

    # Natural-language cross-domain search (semantic filter extraction)
    results = await router.intelligent_search("urgent health tasks")

    # Advanced search with graph and tag filters
    request = SearchRequest(
        query_text="machine learning",
        entity_types=[EntityType.PATH_STEP],
        connected_to_uid="ku.python-basics",
        connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
        tags_contain=["python"],
    )
    result = await router.advanced_search(request)
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import TYPE_CHECKING, Any, ClassVar

from core.models.enums import SearchVisibility
from core.models.enums.entity_enums import Domain, EntityType, NonKuDomain
from core.models.enums.neo_labels import NeoLabel
from core.models.search.filter_enums import SearchSortOrder
from core.models.type_hints import UserUID
from core.ports.search_protocols import (
    SupportsGraphAwareSearch,
    SupportsGraphTraversalSearch,
    SupportsTagSearch,
    SupportsTextSearch,
    SupportsVisibilityDeclaration,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_combined_score, get_dict_score

if TYPE_CHECKING:
    from core.models.search.query_parser import ParsedSearchQuery
    from core.models.search_request import SearchRequest, SearchResponse
    from core.ports import (
        CalendarServiceOperations,
        EventBusOperations,
        ExerciseOperations,
        LifePathOperations,
        RevisedExerciseOperations,
    )
    from core.ports.query_types import (
        CapacityWarnings,
        NousSubtopicPair,
        SemanticSearchChunkResult,
        TagFrequency,
    )
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.finance_service import FinanceService
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.ku_service import KuService
    from core.services.lp_service import LpService
    from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
    from core.services.principles_service import PrinciplesService
    from core.services.ps_service import PsService
    from core.services.tasks_service import TasksService
    from core.services.user import UserContext
    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_service import UserService

    # The union of every service the registry can route to. Heterogeneous by
    # design (concrete facades for facade-tier domains, ISP protocols for thin
    # ones — mirroring the Services container's own field types); capability
    # protocols (SupportsTextSearch / SupportsGraphAwareSearch / ...) do the
    # per-call narrowing.
    type DomainService = (
        TasksService
        | GoalsService
        | HabitsService
        | EventsService
        | ChoicesService
        | PrinciplesService
        | FinanceService
        | KuService
        | PsService
        | LpService
        | ExerciseOperations
        | RevisedExerciseOperations
        | UserEntryService
        | LifePathOperations
        | CalendarServiceOperations
    )

logger = get_logger(__name__)


def _sweep_sort_key(sort_field: str) -> "Callable[[dict[str, Any]], str]":
    """Sort-key factory for cross-domain merges on a shared entity field.

    Per-domain result sets arrive Cypher-sorted; the merged list re-sorts on
    the same field in Python. Neo4j temporal values stringify to ISO-8601
    (lexicographic order == chronological order), titles compare
    case-insensitively, and missing values collapse to "" (last on DESC).
    """

    def sort_key(record: dict[str, Any]) -> str:
        value = record.get(sort_field)
        if value is None:
            return ""
        text = str(value)
        return text.lower() if sort_field == "title" else text

    return sort_key


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "uid": self.uid,
            "title": self.title,
            "entity_type": self.entity_type.value,
            "relevance_score": self.relevance_score,
            "priority_score": self.priority_score,
            "combined_score": self.combined_score,
            "match_reason": self.match_reason,
        }


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
# SEARCH ROUTER - EntityType/NonKuDomain-driven dispatch
# =============================================================================


class SearchRouter:
    """
    Routes search requests to appropriate domain services based on EntityType/NonKuDomain.

    Provides a unified entry point for searching across SKUEL's 12 searchable domains,
    with automatic service discovery and result aggregation.

    The router uses EntityType/NonKuDomain enums for type-safe dispatch, eliminating
    stringly-typed domain checks scattered across the codebase.

    Example:
        router = SearchRouter(tasks=tasks_service, goals=goals_service)

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

    # Mapping of EntityType/NonKuDomain to its domain string — simultaneously
    # the router's constructor parameter name, the Services field name compose
    # reads the dependency from, and the wire vocabulary (`SearchResponse.domain`,
    # `_GRAPH_AWARE_DOMAINS` membership). Kept in lock-step with the
    # constructor-built `_domain_services` dict by
    # tests/unit/models/test_search_router_registry.py.
    # Note: Attribute names follow consistent plural pattern for activity domains
    _SERVICE_REGISTRY: ClassVar[dict[EntityType | NonKuDomain, str]] = {
        # Activity Domains (6) - have dedicated search services (all plural)
        EntityType.TASK: "tasks",
        EntityType.GOAL: "goals",
        EntityType.HABIT: "habits",
        EntityType.EVENT: "events",
        EntityType.CHOICE: "choices",
        EntityType.PRINCIPLE: "principles",
        # Finance (singular - standalone domain group)
        NonKuDomain.FINANCE: "finance",
        # Curriculum Domains (3) - ku, ps, lp form the knowledge foundation
        EntityType.KU: "ku",
        EntityType.PATH_STEP: "ps",
        EntityType.LEARNING_PATH: "lp",
        # Learning Loop (3) - Exercise -> UserEntry -> RevisedExercise
        EntityType.EXERCISE: "exercises",
        EntityType.REVISED_EXERCISE: "revised_exercises",
        EntityType.USER_ENTRY: "user_entry",
        # The Destination - LifePath
        # "Everything flows toward the life path"
        EntityType.LIFE_PATH: "lifepath",
        # Cross-cutting Systems (not domains)
        NonKuDomain.CALENDAR: "calendar",  # Aggregation: Tasks + Events + Habits + Goals
    }

    # EntityTypes that support DomainSearchOperations[T] protocol.
    # Every member MUST resolve through _SERVICE_REGISTRY to a live Services
    # field — guarded by tests/unit/models/test_search_router_registry.py.
    _SEARCHABLE_DOMAINS: frozenset[EntityType] = frozenset(
        {
            # Activity Domains (6)
            EntityType.TASK,
            EntityType.GOAL,
            EntityType.HABIT,
            EntityType.EVENT,
            EntityType.CHOICE,
            EntityType.PRINCIPLE,
            # Curriculum Domains (3) - Ku, PS, LP
            EntityType.KU,
            EntityType.PATH_STEP,
            EntityType.LEARNING_PATH,
            # Learning Loop (3) - Exercise, UserEntry, RevisedExercise
            EntityType.EXERCISE,
            EntityType.REVISED_EXERCISE,
            EntityType.USER_ENTRY,
        }
    )

    # Reverse of _SERVICE_REGISTRY: domain string → enum, for the paths that
    # receive the wire vocabulary (request.domain / _GRAPH_AWARE_DOMAINS).
    _DOMAIN_STR_TO_ENTITY: ClassVar[dict[str, EntityType | NonKuDomain]] = {
        attr: entity for entity, attr in _SERVICE_REGISTRY.items()
    }

    def __init__(
        self,
        *,
        tasks: "TasksService | None" = None,
        goals: "GoalsService | None" = None,
        habits: "HabitsService | None" = None,
        events: "EventsService | None" = None,
        choices: "ChoicesService | None" = None,
        principles: "PrinciplesService | None" = None,
        finance: "FinanceService | None" = None,
        ku: "KuService | None" = None,
        ps: "PsService | None" = None,
        lp: "LpService | None" = None,
        exercises: "ExerciseOperations | None" = None,
        revised_exercises: "RevisedExerciseOperations | None" = None,
        user_entry: "UserEntryService | None" = None,
        lifepath: "LifePathOperations | None" = None,
        calendar: "CalendarServiceOperations | None" = None,
        user: "UserService | None" = None,
        vector_search_service: "Neo4jVectorSearchService | None" = None,
        event_bus: "EventBusOperations | None" = None,
    ) -> None:
        """
        Initialize router with explicit dependencies.

        Each parameter name matches both its `_SERVICE_REGISTRY` domain string
        and the Services container field the composition root reads it from.
        Every dependency is optional — the router fails soft per domain
        (a missing service contributes no results rather than failing search).

        Args:
            tasks..calendar: The 15 routed domain services (types mirror the
                Services container's field declarations).
            user: Capacity-warning source (`peek_cached_context` — cache-hit-only).
            vector_search_service: Digital-layer semantic search (None on CORE tier).
            event_bus: `search.executed` discovery-analytics publishing.
        """
        self._ku = ku
        self._ps = ps
        self._habits = habits
        self._user = user
        self._vector_search = vector_search_service
        self._event_bus = event_bus
        # Keys are exactly _SERVICE_REGISTRY's keys (guarded by
        # test_search_router_registry) so enum-driven dispatch cannot dangle.
        self._domain_services: "dict[EntityType | NonKuDomain, DomainService | None]" = {
            EntityType.TASK: tasks,
            EntityType.GOAL: goals,
            EntityType.HABIT: habits,
            EntityType.EVENT: events,
            EntityType.CHOICE: choices,
            EntityType.PRINCIPLE: principles,
            NonKuDomain.FINANCE: finance,
            EntityType.KU: ku,
            EntityType.PATH_STEP: ps,
            EntityType.LEARNING_PATH: lp,
            EntityType.EXERCISE: exercises,
            EntityType.REVISED_EXERCISE: revised_exercises,
            EntityType.USER_ENTRY: user_entry,
            EntityType.LIFE_PATH: lifepath,
            NonKuDomain.CALENDAR: calendar,
        }
        self.logger = get_logger(__name__)

    def get_service(self, entity_type: EntityType | NonKuDomain) -> "DomainService | None":
        """
        Get the appropriate service for a EntityType or NonKuDomain.

        Args:
            entity_type: The domain to get service for

        Returns:
            Service instance or None if not found/not initialized
        """
        if entity_type not in self._domain_services:
            self.logger.warning(f"No service registered for domain: {entity_type}")
            return None

        service = self._domain_services[entity_type]
        if service is None:
            self.logger.debug(f"Service not initialized for {entity_type}")

        return service

    async def _nous_subtopic_pairs(self) -> "list[NousSubtopicPair]":
        """Gather (nous, nous_subtopic) co-occurrence pairs across curriculum domains.

        The cross-domain aggregation point (SearchRouter is THE cross-domain
        search service): each curriculum domain backend contributes pairs scoped
        to its OWN label (`KuBackend`/`PsBackend.nous_subtopic_pairs`) — the merge
        lives here in the service layer, never in a single-domain backend. Both
        Ku and PathStep author `nous_subtopic` independently, so a PathStep can
        contribute a pair no Ku carries; folding both keeps the facet complete.

        Fails soft per domain: a missing service or an errored call contributes
        nothing rather than failing the whole vocabulary.
        """
        pairs: "list[NousSubtopicPair]" = []
        for entity_type, service in (
            (EntityType.KU, self._ku),
            (EntityType.PATH_STEP, self._ps),
        ):
            if service is None:
                continue
            result = await service.nous_subtopic_pairs()
            if result.is_error:
                self.logger.warning(f"nous_subtopic_pairs failed for {entity_type}: {result.error}")
                continue
            pairs.extend(result.value or [])
        return pairs

    async def nous_subtopic_map(self) -> Result[dict[str, list[str]]]:
        """Map each NOUS topic to the sub-topics authored alongside it.

        Powers the dependent /search dropdown (pick a NOUS topic → its sub-topics).
        Derived from the graph across `:Ku` + `:PathStep` (never hardcoded — the
        taxonomy stays in the vault, content boundary). Sub-topics per topic are
        deduped + sorted. Fail-soft/empty until `nous_subtopic:` data is authored.
        """
        mapping: dict[str, set[str]] = {}
        for pair in await self._nous_subtopic_pairs():
            mapping.setdefault(pair["nous"], set()).add(pair["subtopic"])
        return Result.ok({nous: sorted(subs) for nous, subs in mapping.items()})

    async def tag_frequencies(self) -> Result["list[TagFrequency]"]:
        """Tag vocabulary across the shared curriculum catalog, most-used first.

        Powers the frequency-ranked /explore/library tag chips. Same
        cross-domain aggregation point as the NOUS vocabulary: each domain's
        search sub-service counts its OWN tags (``tag_frequencies`` →
        ``distinct_values_raw("tags")``), the merge — summing counts for tags
        both domains carry — lives here. Ordered by count descending, ties
        alphabetical; fails soft per domain (a missing service or an errored
        call contributes nothing rather than failing the vocabulary).
        """
        counts: dict[str, int] = {}
        for entity_type, service in (
            (EntityType.KU, self._ku),
            (EntityType.PATH_STEP, self._ps),
        ):
            if service is None:
                continue
            result = await service.search.tag_frequencies()
            if result.is_error:
                self.logger.warning(f"tag_frequencies failed for {entity_type}: {result.error}")
                continue
            for tag, count in (result.value or {}).items():
                counts[tag] = counts.get(tag, 0) + count

        def most_used_first(item: tuple[str, int]) -> tuple[int, str]:
            return (-item[1], item[0])

        ordered: "list[TagFrequency]" = [
            {"tag": tag, "count": count}
            for tag, count in sorted(counts.items(), key=most_used_first)
        ]
        return Result.ok(ordered)

    async def list_tags(self) -> Result[list[str]]:
        """Flat alphabetical tag vocabulary — the /search tags-filter shape.

        Derived from ``tag_frequencies`` (one aggregation path); dropdowns
        scan alphabetically, so the counts are dropped and the order re-sorted.
        """
        result = await self.tag_frequencies()
        if result.is_error:
            return Result.fail(result)
        return Result.ok(sorted(item["tag"] for item in result.value))

    async def list_nous_subtopics(self) -> Result[list[str]]:
        """Flat NOUS sub-topic vocabulary — every distinct sub-topic, deduped + sorted.

        Same `:Ku` + `:PathStep` source as `nous_subtopic_map`, flattened. Sharing
        the source keeps the flat list (which gates whether the /search sub-topic
        column renders) a superset of every scoped map, so the column — and its
        dependent HTMX target — renders whenever the map has any entry, even in a
        corpus whose sub-topics live only on PathSteps. Fail-soft/empty.
        """
        subtopics = {pair["subtopic"] for pair in await self._nous_subtopic_pairs()}
        return Result.ok(sorted(subtopics))

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
        user_uid: UserUID | None = None,
    ) -> Result[list[Any]]:
        """
        Search within a single domain.

        Routes the search to the appropriate domain service based on EntityType/NonKuDomain.

        Args:
            entity_type: Domain to search in
            query: Search query string
            limit: Maximum results to return
            user_uid: Optional owner scope, applied by the domain service.
                REQUIRED for USER_ENTRY — entries are private user content
                (journal periodic notes live in this store), so an unscoped
                entry search is refused rather than leaking across users.

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

        # Privacy line: never run an unscoped UserEntry search
        if entity_type == EntityType.USER_ENTRY and user_uid is None:
            return Result.fail(
                Errors.validation(
                    field="user_uid",
                    message="user_entry search requires a user scope",
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
            search_service = self._get_search_service(service)
            if search_service is None and isinstance(service, SupportsTextSearch):
                search_service = service
            if search_service is None:
                return Result.fail(
                    Errors.database(
                        operation="search",
                        message=f"{entity_type.value} service does not support text search",
                    )
                )

            # Forward the owner scope unconditionally — the domain's
            # search_visibility declaration (DomainConfig) decides what the
            # uid means: OWNER_ONLY property-scopes, PUBLIC ignores it,
            # SCOPE_AWARE (Exercise) resolves curriculum/ownership/sharing.
            return await search_service.search(query, limit, user_uid=user_uid)

        except (AttributeError, TypeError, ValueError) as e:
            self.logger.error(f"Search failed for {entity_type.value}: {e}")
            return Result.fail(Errors.database(operation="search", message=str(e)))
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Search failed for {entity_type.value} (unexpected): {e}")
            return Result.fail(Errors.database(operation="search", message=str(e)))

    def _get_search_service(self, service: "DomainService") -> SupportsTextSearch | None:
        """
        Get the search sub-service from a domain service.

        Activity Domain services have a .search property that returns
        the SearchService (e.g., TasksService.search → TasksSearchService).

        Args:
            service: Domain service instance

        Returns:
            Search service or None

        Note:
            This method is only called after supports_search() validation.
            Activity Domain services expose search via a .search property.
            The callable() check is load-bearing and cannot be replaced by
            isinstance alone — a runtime_checkable protocol cannot distinguish
            ".search is the sub-service" from ".search is a method"; the
            isinstance narrows the sub-service to the text-search capability.
        """
        # Activity Domain pattern: .search is a property returning SearchService
        # Access directly - supports_search() already validated this is a searchable domain
        search_attr = getattr(service, "search", None)

        # If .search is a property (not a method), it returns the search sub-service
        if (
            search_attr is not None
            and not callable(search_attr)
            and isinstance(search_attr, SupportsTextSearch)
        ):
            return search_attr

        # Fall back to the service itself (service implements search directly)
        return None

    async def search_domains(
        self,
        entity_types: list[EntityType | NonKuDomain],
        query: str,
        limit_per_domain: int = 20,
        user_uid: UserUID | None = None,
    ) -> UnifiedSearchResult:
        """
        Search across multiple domains.

        Performs parallel searches across specified domains and aggregates results.

        Args:
            entity_types: List of domains to search
            query: Search query string
            limit_per_domain: Max results per domain
            user_uid: Optional owner scope forwarded to each domain search.
                Without it, USER_ENTRY is refused by search() (privacy line)
                and simply yields no results here.

        Returns:
            UnifiedSearchResult with results grouped by domain
        """
        results_by_domain: dict[EntityType | NonKuDomain, list[SearchResultItem]] = {}
        total_count = 0

        for entity_type in entity_types:
            if not self.supports_search(entity_type):
                continue

            result = await self.search(entity_type, query, limit_per_domain, user_uid=user_uid)
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

    async def _publish_search_event(
        self,
        query_text: str | None,
        *,
        user_uid: UserUID | None,
        entry_point: str,
        result_count: int,
        domains: tuple[str, ...] = (),
        semantic_boost: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> None:
        """Publish search.executed for one EXTERNAL search — discovery-analytics log.

        One event per external entry point call (faceted/intelligent/advanced).
        Internal fan-out never
        publishes — intelligent_search suppresses its per-domain faceted calls
        via log_event=False. Empty/whitespace queries are skipped (filter-only
        searches carry no gap signal). Fail-soft: never raises, a logging
        failure must never break search.

        Subscriber: SearchEventRecorder → SearchEventBackend (:SearchEvent).
        """
        stripped = (query_text or "").strip()
        if not stripped:
            return

        import json

        from core.events import SearchExecuted, publish_event

        try:
            event = SearchExecuted(
                query_text=stripped,
                user_uid=user_uid,
                entry_point=entry_point,
                result_count=result_count,
                zero_results=result_count == 0,
                semantic_boost=semantic_boost,
                domains=domains,
                filters_json=json.dumps(filters or {}, default=str),
            )
            await publish_event(self._event_bus, event, self.logger)
        except Exception as e:  # safety-net: search logging must never break search
            self.logger.warning(f"search.executed not published: {e}")

    async def faceted_search(
        self,
        request: "SearchRequest",
        user_uid: UserUID | None = None,
        *,
        log_event: bool = True,
        entry_point: str = "faceted",
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

        from core.models.search_request import SearchResponse, build_facet_counts

        start_time = datetime.now()

        try:
            # Route 1: Single domain specified — either request.domain or a
            # single entity-type filter (the /search dropdown path)
            domain_str = self._resolve_single_domain(request)
            response: Result["SearchResponse"] | None = None
            if domain_str:
                # Privacy line: refuse loudly rather than fall through to the
                # sweep and return an empty success for a misprogrammed caller
                if domain_str == "user_entry" and user_uid is None:
                    return Result.fail(
                        Errors.validation(
                            field="user_uid",
                            message="user_entry search requires a user scope",
                        )
                    )

                # Graph-aware domains → graph_aware_faceted_search. Anonymous
                # callers are allowed through — the per-domain visibility gate
                # inside _graph_aware_domain_search admits PUBLIC domains
                # (Ku/PS/LP catalog browse) and bounces everything else to the
                # fallback below (July 2026, /explore/library consolidation).
                if domain_str in self._GRAPH_AWARE_DOMAINS:
                    response = await self._graph_aware_domain_search(request, user_uid, domain_str)

                # Curriculum or other domains → simple text search
                if response is None:
                    response = await self._simple_domain_search(request, domain_str)

            # Route 2: Cross-domain search (no single domain resolvable)
            if response is None:
                cross_results = await self._cross_domain_search(request, user_uid)
                search_time = (datetime.now() - start_time).total_seconds() * 1000
                response = Result.ok(
                    SearchResponse(
                        results=cross_results,
                        total=len(cross_results),
                        limit=request.limit,
                        offset=request.offset,
                        query_text=request.query_text,
                        domain=None,
                        facet_counts={},
                        applied_filters=request.to_property_filters(),
                        search_time_ms=search_time,
                    )
                )

            # Digital-layer enhancement (ADR-043): when the semantic-boost
            # toggle is on, fold lesson-BODY hits (Ku/PS :ContentChunk) into the
            # results so body prose surfaces its parent card. Fails soft — the
            # frontmatter/graph results above stand alone on the CORE tier.
            # Gate on the raw flag, not has_semantic_boost() — the latter also
            # requires context_uids (the advanced_search relationship-boost
            # path), which the /search UI never supplies. The checkbox alone
            # makes /search body-aware.
            if response.is_ok and request.enable_semantic_boost:
                augmented = await self._augment_with_body_chunks(
                    request, domain_str, response.value
                )
                response = Result.ok(augmented)

            # Response enrichment (July 2026 — the formerly writer-less
            # fields): facet counts derive from the returned window, and
            # capacity warnings come from the WARM UserContext cache only —
            # neither adds a query to the keystroke-driven /search path.
            if response.is_ok:
                if request.include_facet_counts and response.value.results:
                    response.value.facet_counts = build_facet_counts(response.value.results)
                if user_uid is not None:
                    response.value.capacity_warnings = self._peek_capacity_warnings(user_uid)

            if log_event and response.is_ok:
                await self._publish_search_event(
                    request.query_text,
                    user_uid=user_uid,
                    entry_point=entry_point,
                    result_count=response.value.total,
                    domains=(domain_str,) if domain_str else (),
                    semantic_boost=request.enable_semantic_boost,
                    filters=request.to_property_filters(),
                )
            return response

        except (AttributeError, TypeError, ValueError, KeyError) as e:
            self.logger.error(f"Faceted search failed: {e}")
            return Result.fail(Errors.database(operation="faceted_search", message=str(e)))
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Faceted search failed (unexpected): {e}")
            return Result.fail(Errors.database(operation="faceted_search", message=str(e)))

    def _peek_capacity_warnings(self, user_uid: UserUID) -> "CapacityWarnings":
        """Capacity warnings from the WARM UserContext cache — never builds.

        Cache-hit-only by design: search must not pay MEGA-QUERY latency
        (SEARCH_ARCHITECTURE § Personalization). A cold cache yields no
        warnings; surfaces that build the rich context (profile, personal
        header) warm it, and domain events keep it honest via invalidation.
        """
        if self._user is None:
            return {}
        context = self._user.peek_cached_context(user_uid)
        if context is None:
            return {}
        return context.get_capacity_warnings()

    async def retrieve_scoped_chunks(
        self,
        request: "SearchRequest",
        *,
        chunk_types: list[str] | None = None,
        min_score: float | None = None,
        user_uid: UserUID | None = None,
    ) -> Result[list["SemanticSearchChunkResult"]]:
        """Retrieve lesson-BODY passages (:ContentChunk) scoped to the request's facets.

        The chunk-level (RAG) counterpart to ``faceted_search``: where that method
        returns entity cards, this returns the passages that ground an answer.
        Both take the SAME SearchRequest, so Ask (Askesis) and Find (/search) share
        ONE facet→scope path — a ``nous`` topic on the request narrows the retrieved
        passages to that topic's owning Ku/PS entities (via
        ``request.to_property_filters()``), exactly as it narrows the entity results.

        Returns an ``unavailable`` error on the CORE tier (no vector search), so the
        caller can fail soft rather than crash — the Digital layer is optional.

        Backend: Neo4jVectorSearchService.find_similar_chunks_by_text →
        VectorSearchBackend.semantic_search_chunks.
        """
        # Reserved: future owner-scoped chunk VISIBILITY (parity with
        # faceted_search — curriculum chunks visible to all + the user's own).
        # Deliberately NOT wired to semantic_search_chunks(owner_uid=...): that
        # parameter is the canon-P3 vault scope (OWNS-only + private-excluded),
        # which would EXCLUDE ownerless curriculum chunks and break Askesis.
        # Different feature, different clause.
        del user_uid

        vector_search = self._vector_search
        if vector_search is None:
            return Result.fail(
                Errors.unavailable(
                    feature="scoped_chunk_search",
                    reason="vector search unavailable (CORE tier)",
                    operation="retrieve_scoped_chunks",
                )
            )

        return await vector_search.find_similar_chunks_by_text(
            text=request.query_text or "",
            chunk_types=chunk_types,
            limit=request.limit,
            min_score=min_score,
            parent_filters=request.to_property_filters(),
        )

    # Domains that support graph_aware_faceted_search (January 2026 - Unified Search)
    # Includes Activity Domains (6) + Curriculum Domains (3) + Learning Loop (3)
    # One Path Forward: All domains use the same search pattern
    _GRAPH_AWARE_DOMAINS: frozenset[str] = frozenset(
        {
            "tasks",
            "goals",
            "habits",
            "events",
            "choices",
            "principles",
            "ku",
            "ps",
            "lp",
            "exercises",
            "revised_exercises",
            "user_entry",
        }
    )

    # Curriculum EntityType values whose lesson BODIES are chunked + embedded
    # (the `chunks_body_content` ingestion configs, #535). Body prose lives on
    # :ContentChunk nodes, invisible to frontmatter text search — the body-chunk
    # augmentation is the only /search path that reaches it. Mapped by Services
    # attr name (domain_str) → the parent EntityType value stamped as `_domain`.
    _BODY_CHUNK_DOMAIN_VALUE: ClassVar[dict[str, str]] = {
        "ku": EntityType.KU.value,  # "ku"
        "ps": EntityType.PATH_STEP.value,  # "path_step"
    }

    # Curriculum EntityType values eligible for the hybrid fulltext+vector text
    # rung (D2 ruling 2026-08-16: PUBLIC-visibility domains only — Exercise is
    # SCOPE_AWARE and deferred to the D1(b) domain-level follow-on). The belt
    # half of the rung's belt-and-braces eligibility; the braces half is the
    # live search_visibility read in _hybrid_curriculum_search.
    _HYBRID_TEXT_DOMAIN_VALUES: ClassVar[frozenset[str]] = frozenset(
        {
            EntityType.KU.value,
            EntityType.PATH_STEP.value,
            EntityType.LEARNING_PATH.value,
        }
    )

    async def _augment_with_body_chunks(
        self,
        request: "SearchRequest",
        domain_str: str | None,
        response: "SearchResponse",
    ) -> "SearchResponse":
        """Fold lesson-BODY semantic hits (Ku/PS :ContentChunk) into results.

        Digital-layer enhancement (ADR-043). Embeds the query, finds similar
        content chunks SCOPED to the active facets (nous/level/... via
        ``request.to_property_filters()``, so a filtered /search never leaks
        bodies from other topics), maps each to its owning Ku/PS Entity, dedupes
        to the best-scoring chunk per parent, and appends the PARENT as a normal
        result card (never a raw chunk) — deduped against parents already present.

        Fails SOFT and NEVER raises: no vector service (CORE tier), no query, or
        a search error all return ``response`` unchanged so /search stays fully
        functional without the Digital layer.

        Backend: VectorSearchBackend.semantic_search_chunks (via
        Neo4jVectorSearchService.find_similar_chunks_by_text).
        """
        # Scope: single Ku/PS domain → that type only; cross-domain → both.
        if domain_str is None:
            target_values = frozenset(self._BODY_CHUNK_DOMAIN_VALUE.values())
        elif domain_str in self._BODY_CHUNK_DOMAIN_VALUE:
            target_values = frozenset({self._BODY_CHUNK_DOMAIN_VALUE[domain_str]})
        else:
            return response  # non-curriculum single domain — no bodies to add

        if not request.query_text:
            return response

        vector_search = self._vector_search
        if vector_search is None:
            self.logger.debug("Body-chunk search skipped: vector search unavailable (CORE tier)")
            return response

        try:
            chunk_result = await vector_search.find_similar_chunks_by_text(
                text=request.query_text,
                limit=request.limit,
                min_score=vector_search.config.body_chunk_search_min_score,
                # Scope body hits to the active facets (nous/level/...) so a
                # filtered /search doesn't leak lesson bodies from other topics —
                # matches how the frontmatter results above are already scoped.
                parent_filters=request.to_property_filters(),
            )
        except (AttributeError, TypeError, ValueError, KeyError) as e:
            self.logger.warning(f"Body-chunk search errored, returning base results: {e}")
            return response
        except Exception as e:  # safety-net: body chunks must never break search
            self.logger.warning(f"Body-chunk search errored (unexpected): {e}")
            return response

        if chunk_result.is_error:
            self.logger.warning(f"Body-chunk search failed: {chunk_result.expect_error()}")
            return response

        existing_uids = {str(r.get("uid", "")) for r in response.results}
        body_results = self._aggregate_body_chunk_parents(
            list(chunk_result.value), target_values, existing_uids
        )
        if not body_results:
            return response

        merged = list(response.results) + body_results
        self.logger.info(
            f"Body-chunk augmentation added {len(body_results)} Ku/PS lesson-body result(s)"
        )
        return response.model_copy(update={"results": merged, "total": len(merged)})

    @staticmethod
    def _aggregate_body_chunk_parents(
        hits: list["SemanticSearchChunkResult"],
        target_values: frozenset[str],
        existing_uids: set[str],
    ) -> list[dict[str, Any]]:
        """Dedupe body-chunk hits to one best-scoring parent card each.

        Pure / DB-free. Groups hits by ``parent_uid``, keeps the MAX
        ``similarity_score`` per parent (a lesson is as relevant as its single
        most on-point passage), drops parents already in the base results or
        outside the in-scope curriculum ``target_values``, and returns parent
        result dicts ranked by best-chunk score (descending).
        """

        def _score(hit: "SemanticSearchChunkResult") -> float:
            return hit.get("similarity_score", 0.0)

        best_by_parent: dict[str, SemanticSearchChunkResult] = {}
        for hit in hits:
            parent_uid = hit.get("parent_uid", "")
            if hit.get("parent_entity_type", "") not in target_values or not parent_uid:
                continue
            if parent_uid in existing_uids:
                continue
            current = best_by_parent.get(parent_uid)
            if current is None or _score(hit) > _score(current):
                best_by_parent[parent_uid] = hit

        ranked = sorted(best_by_parent.values(), key=_score, reverse=True)
        return [SearchRouter._chunk_hit_to_result(hit) for hit in ranked]

    @staticmethod
    def _chunk_hit_to_result(hit: "SemanticSearchChunkResult") -> dict[str, Any]:
        """Build a parent-entity result card dict from a body-chunk hit.

        The matched passage becomes the card ``description`` so the learner sees
        WHY the lesson surfaced; ``_domain`` is the parent's EntityType value
        (single vocabulary, #537) so the card links via entity_detail_href.
        """
        return {
            "uid": hit.get("parent_uid", ""),
            "title": hit.get("parent_title") or "Untitled",
            "description": hit.get("text", "") or "",
            "_domain": hit.get("parent_entity_type", ""),
            "_score": hit.get("similarity_score", 0.0),
            "_match_reason": "Matched lesson body",
        }

    @staticmethod
    def _parse_entity_type(raw: object) -> EntityType | NonKuDomain | None:
        """Normalize a request entity-type entry to its enum.

        ``use_enum_values=True`` on SearchRequest means ``entity_types`` holds
        raw value strings after validation — enum identity checks
        (``isinstance``, ``.value``, ``is_user_owned()``) need the member back.
        """
        if isinstance(raw, EntityType | NonKuDomain):
            return raw
        return EntityType.from_string(str(raw)) or NonKuDomain.from_string(str(raw))

    def _resolve_single_domain(self, request: "SearchRequest") -> str | None:
        """Resolve the request to a single domain string, if one is targeted.

        Two sources, in precedence order:
        1. ``request.domain`` — Domain enum value (intelligent_search path).
        2. A single SEARCHABLE ``entity_types`` filter — the /search dropdown
           path. Maps through _SERVICE_REGISTRY so filtered searches take the
           same single-domain (ownership-aware) route as domain searches.
           Non-searchable types (e.g. LIFE_PATH, which is registered for
           ``get_service`` but excluded from ``_SEARCHABLE_DOMAINS``) fall
           through to the cross-domain sweep, keeping this path consistent
           with ``search()``'s supports_search() gate.
        """
        if request.domain:
            return request.domain if isinstance(request.domain, str) else request.domain.value
        if len(request.entity_types) == 1:
            entity_type = self._parse_entity_type(request.entity_types[0])
            if entity_type is not None and self.supports_search(entity_type):
                return self._SERVICE_REGISTRY.get(entity_type)
        return None

    # User-owned Activity EntityTypes → Domain enum for faceted_search routing.
    # Curriculum and other shared domains are absent — no ownership filter needed there.
    _ENTITY_TO_DOMAIN: ClassVar[dict[EntityType | NonKuDomain, Domain]] = {
        EntityType.TASK: Domain.TASKS,
        EntityType.GOAL: Domain.GOALS,
        EntityType.HABIT: Domain.HABITS,
        EntityType.EVENT: Domain.EVENTS,
        EntityType.CHOICE: Domain.CHOICES,
        EntityType.PRINCIPLE: Domain.PRINCIPLES,
    }

    # Default search scope for intelligent_search when no domain is inferred from the query.
    # Covers the 6 user-owned Activity domains (routed through faceted_search with user_uid)
    # and 3 shared Curriculum domains (no ownership filter required).
    # Excluded intentionally:
    #   Exercise / RevisedExercise / UserEntry — user-owned, no Domain enum mapping for routing.
    _INTELLIGENT_SEARCH_DOMAINS: ClassVar[frozenset[EntityType]] = frozenset(
        {
            EntityType.TASK,
            EntityType.GOAL,
            EntityType.HABIT,
            EntityType.EVENT,
            EntityType.CHOICE,
            EntityType.PRINCIPLE,
            EntityType.KU,
            EntityType.PATH_STEP,
            EntityType.LEARNING_PATH,
        }
    )

    def _resolve_graph_aware_service(self, domain_str: str) -> "SupportsGraphAwareSearch | None":
        """Resolve a domain string to its graph-aware search service, if any.

        Domain strings in _GRAPH_AWARE_DOMAINS are _SERVICE_REGISTRY values
        (the wire vocabulary). Facade domains expose the capability on their
        ``.search`` sub-service; thin services (Exercise, UserEntry, etc.)
        implement it directly.
        """
        entity_type = self._DOMAIN_STR_TO_ENTITY.get(domain_str)
        if entity_type is None:
            return None
        domain_service = self._domain_services.get(entity_type)
        if domain_service is None:
            return None

        search_service = getattr(domain_service, "search", None)
        if search_service is not None and not callable(search_service):
            # Facade pattern: .search property returns sub-service
            if isinstance(search_service, SupportsGraphAwareSearch):
                return search_service
            return None
        if isinstance(domain_service, SupportsGraphAwareSearch):
            return domain_service
        return None

    async def _graph_aware_domain_search(
        self,
        request: "SearchRequest",
        user_uid: UserUID | None,
        domain_str: str,
    ) -> Result["SearchResponse"] | None:
        """
        Graph-aware search for domains that support graph_aware_faceted_search.

        Works for both Activity Domains (Tasks, Goals, etc.) and Curriculum Domains (KU).

        January 2026: Unified search architecture - One Path Forward.
        Anonymous callers (user_uid=None) are admitted only for PUBLIC-visibility
        domains; others fall back to the caller's next strategy (None return).
        """
        from datetime import datetime

        from core.models.search_request import SearchResponse

        search_service = self._resolve_graph_aware_service(domain_str)
        if search_service is None:
            return None
        if user_uid is None and search_service.search_visibility is not SearchVisibility.PUBLIC:
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
                applied_filters=request.to_property_filters(),
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

        # Map domain string to EntityType. "knowledge" → KU matches the
        # platform-wide alias (EntityType.from_string, Domain.KNOWLEDGE alias
        # tuple) — the old PATH_STEP routing was an exclusion-era workaround
        # (Kody, #536).
        domain_to_entity = {
            "knowledge": EntityType.KU,
            "ku": EntityType.KU,
            "lesson": EntityType.PATH_STEP,
            "ps": EntityType.PATH_STEP,
            "lp": EntityType.LEARNING_PATH,
            "exercises": EntityType.EXERCISE,
            "exercise": EntityType.EXERCISE,
            "revised_exercises": EntityType.REVISED_EXERCISE,
            "user_entry": EntityType.USER_ENTRY,
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
                # Stamp the EntityType value (the single _domain vocabulary),
                # not the Services attr name in domain_str.
                "_domain": entity_type.value,
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
                applied_filters=request.to_property_filters(),
                search_time_ms=search_time,
            )
        )

    async def _cross_domain_search(
        self,
        request: "SearchRequest",
        user_uid: UserUID | None = None,
    ) -> list[dict]:
        """Search across multiple domains and aggregate results.

        An explicit ``entity_types`` filter narrows the sweep (e.g.
        ``[USER_ENTRY, TASK]``); otherwise all searchable domains EXCEPT
        UserEntry are swept — entries are private user content and appear in
        aggregations only when the caller explicitly asks for them AND the
        search is user-scoped (search() refuses unscoped UserEntry queries).
        ``user_uid`` scopes user-owned domains; shared domains ignore it.
        """
        sweep_domains: list[EntityType | NonKuDomain]
        if request.entity_types:
            sweep_domains = [
                et for et in map(self._parse_entity_type, request.entity_types) if et is not None
            ]
        else:
            sweep_domains = [et for et in self._SEARCHABLE_DOMAINS if et != EntityType.USER_ENTRY]

        # Property facets (nous, sel_category, ...) AND relationship/pedagogical
        # flags (ready_to_learn, not_yet_viewed, ...) can't ride the plain text
        # sweep — search_domains() drops both. Route through per-domain
        # graph-aware faceted search instead, so a facet like "NOUS topic = body"
        # or "ready to learn" with Type = All actually filters (they become
        # WHERE clauses in each domain's query). Without the relationship check a
        # relationship-only, empty-query request would silently fall through to
        # the unfiltered text sweep and drop the filter (Codex, PR #549).
        # Tag facets, EMPTY-QUERY browse, and EXPLICIT SORT (July 2026,
        # /explore/library consolidation) route the same way: the text sweep
        # can express none of them — search() hard-rejects an empty query,
        # drops tag/property filters, caps at limit//6 per domain, and ranks
        # by score only (so a requested created/title order would be ignored
        # and the library's All-Types text search starved to ≤10 minimal
        # records — Codex, PR #669). Only a RELEVANCE-sorted pure text query
        # belongs on the scored sweep. No user_uid gate here — _faceted_sweep
        # admits anonymous callers per-domain (PUBLIC visibility only).
        wants_faceted = (
            request.to_property_filters()
            or request.has_relationship_filters()
            or request.has_tag_filter()
            or not request.query_text
            or request.get_sort_order() is not SearchSortOrder.RELEVANCE
        )
        if wants_faceted:
            return await self._faceted_sweep(request, user_uid, sweep_domains)

        unified_result = await self.search_domains(
            sweep_domains,
            request.query_text or "",
            limit_per_domain=max(5, request.limit // 6),
            user_uid=user_uid,
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

    async def _faceted_sweep(
        self,
        request: "SearchRequest",
        user_uid: UserUID | None,
        sweep_domains: list[EntityType | NonKuDomain],
    ) -> list[dict]:
        """Cross-domain sweep with property facets applied in-query.

        Each sweep domain that supports graph_aware_faceted_search runs it —
        the request's property filters become WHERE clauses. Domains without
        graph-aware support are SKIPPED, not text-searched: a filtered sweep
        must never mix unfiltered results into a facet the user narrowed.
        Anonymous callers sweep PUBLIC-visibility domains only (Ku/PS/LP
        catalog browse); user-owned domains are skipped fail-closed.

        Results are FULL node-property dicts (same shape as the single-domain
        graph-aware route) so consumers like /explore/library can render rich
        cards from either path.

        Merging: with an explicit sort the per-domain (already sorted) result
        sets are merged on the shared sort key. RELEVANCE results carry no
        cross-domain score, so they keep the round-robin interleave — iteration
        order must not let an early domain consume the whole budget and starve
        later ones (Kody, PR #534).

        Pagination is global-window: each domain over-fetches offset+limit
        rows from 0, then the merged list is sliced — a per-domain SKIP would
        drop rows that belong in the merged page. Window is capped by the
        SearchRequest limit ceiling, bounding All-types page depth.
        """
        sort = request.get_sort_order()
        # Over-fetch window so the merged slice is correct across domains.
        window = min(request.offset + request.limit, 200)
        window_request = request.model_copy(update={"limit": window, "offset": 0})

        per_domain: list[list[dict]] = []
        for entity_type in sweep_domains:
            domain_str = self._SERVICE_REGISTRY.get(entity_type)
            if domain_str is None or domain_str not in self._GRAPH_AWARE_DOMAINS:
                continue
            search_service = self._resolve_graph_aware_service(domain_str)
            if search_service is None:
                continue
            if user_uid is None and search_service.search_visibility is not SearchVisibility.PUBLIC:
                continue

            result = await search_service.graph_aware_faceted_search(
                request=window_request,
                user_uid=user_uid,
            )
            if result.is_error:
                self.logger.warning(f"Faceted sweep failed for {domain_str}: {result.error}")
                continue

            domain_results = []
            for record in result.value or []:
                # Full node-property dict; ensure the _domain stamp (already
                # set by graph_aware_faceted_search) uses the EntityType-value
                # vocabulary, never the Services attr name in domain_str.
                item = dict(record)
                item.setdefault("_domain", entity_type.value)
                item.setdefault("_score", 0.0)
                domain_results.append(item)
            if domain_results:
                per_domain.append(domain_results)

        merged: list[dict] = []
        if sort is SearchSortOrder.RELEVANCE:
            for tier in zip_longest(*per_domain):
                merged.extend(item for item in tier if item is not None)
        else:
            sort_field = sort.get_sort_field() or "updated_at"
            for domain_results in per_domain:
                merged.extend(domain_results)
            merged.sort(key=_sweep_sort_key(sort_field), reverse=sort.is_descending())
        return merged[request.offset : request.offset + request.limit]

    async def intelligent_search(
        self,
        query: str,
        user_uid: UserUID | None = None,
        user_context: "UserContext | None" = None,
        limit: int = 50,
    ) -> Result[UnifiedSearchResult]:
        """
        Intelligent cross-domain search with semantic filter extraction.

        Parses the natural language query for semantic signals (priority, status,
        domain), then routes each target domain through faceted_search so that
        user-owned Activity domains apply the ownership filter in the database
        query rather than post-hoc.  Curriculum/shared domains (KU, PS, LP) fall
        back to the bare text-search path — they have no ownership filter.

        Args:
            query: Natural language search query
            user_uid: Caller's user UID for ownership-scoped Activity domain queries
            user_context: Optional rich user context for personalized scoring
            limit: Maximum total results

        Returns:
            Result containing UnifiedSearchResult with parsed query info
        """
        from core.models.search.query_parser import SearchQueryParser
        from core.models.search_request import SearchRequest

        try:
            parser = SearchQueryParser()
            parsed = parser.parse(query)
            target_domains = self._determine_target_domains(parsed)
            limit_per_domain = max(10, limit // len(target_domains)) if target_domains else limit

            # user_uid can come from either the direct arg or the richer user_context
            effective_uid = user_uid or (user_context.user_uid if user_context else None)

            results_by_domain: dict[EntityType | NonKuDomain, list[SearchResultItem]] = {}
            total_count = 0

            for entity_type in target_domains:
                mapped_domain = self._ENTITY_TO_DOMAIN.get(entity_type)
                items: list[SearchResultItem]

                if mapped_domain is not None and effective_uid:
                    # User-owned Activity domain: route through faceted_search so the
                    # ownership WHERE clause is enforced at the database level.
                    request = SearchRequest(
                        query_text=parsed.text_query or None,
                        domain=mapped_domain,
                        priority=parsed.get_highest_priority(),
                        status=parsed.statuses[0] if parsed.statuses else None,
                        limit=limit_per_domain,
                    )
                    # log_event=False: this is internal fan-out — intelligent_search
                    # publishes exactly ONE search.executed itself below.
                    facet_result = await self.faceted_search(
                        request, effective_uid, log_event=False
                    )
                    if facet_result.is_error:
                        self.logger.warning(
                            f"intelligent_search faceted_search failed for "
                            f"{entity_type.value}: {facet_result.error}"
                        )
                        continue
                    items = [
                        SearchResultItem(
                            entity=d,
                            entity_type=entity_type,
                            uid=str(d.get("uid", "")),
                            title=str(d.get("title", "")),
                        )
                        for d in facet_result.value.results
                        if d.get("uid") and d.get("title")
                    ]
                else:
                    # Shared/curriculum domain: bare text search (no ownership needed).
                    bare_result = await self.search(
                        entity_type, parsed.text_query or "", limit_per_domain
                    )
                    if not (bare_result.is_ok and bare_result.value):
                        continue
                    items = self._wrap_results(bare_result.value, entity_type)
                    items = self._apply_semantic_filters(items, parsed)

                if user_context:
                    items = await self._score_results(items, user_context)

                results_by_domain[entity_type] = items
                total_count += len(items)

            await self._publish_search_event(
                query,
                user_uid=effective_uid,
                entry_point="intelligent",
                result_count=total_count,
                domains=tuple(d.value for d in target_domains),
            )

            return Result.ok(
                UnifiedSearchResult(
                    query=query,
                    parsed_query=parsed,
                    results_by_domain=results_by_domain,
                    total_count=total_count,
                )
            )

        except (AttributeError, TypeError, ValueError, KeyError) as e:
            self.logger.error(f"Intelligent search failed: {e}")
            return Result.fail(Errors.database(operation="intelligent_search", message=str(e)))
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Intelligent search failed (unexpected): {e}")
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

        # Default: Activity domains (ownership-scoped via faceted_search) + Curriculum
        return list(self._INTELLIGENT_SEARCH_DOMAINS)

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
                entity_types=[EntityType.PATH_STEP],
                connected_to_uid="ku.python-basics",
                connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
                tags_contain=["python"],
            )
            result = await router.advanced_search(request, user_context)
        """
        try:
            # Determine target domains. Normalize filter entries back to enum
            # members — use_enum_values=True on SearchRequest means
            # entity_types holds raw strings after validation, and a raw
            # string in SearchResultItem.entity_type crashes serialization.
            target_domains: list[EntityType | NonKuDomain]
            if request.has_entity_type_filter():
                target_domains = [
                    parsed
                    for raw in request.entity_types
                    if (parsed := self._parse_entity_type(raw)) is not None
                ]
            else:
                target_domains = list(self._SEARCHABLE_DOMAINS)

            results_by_domain: dict[EntityType | NonKuDomain, list[SearchResultItem]] = {}
            total_count = 0

            # Filter skips up-front so the per-domain limit budget divides
            # by the domains that actually run (Kody, PR #513) — a mixed
            # [TASK, EXERCISE] request without a user must give EXERCISE
            # the full budget, not half of it:
            # - UserEntry: excluded from cross-domain aggregation — private
            #   user content with its own scoped surfaces (faceted_search
            #   with the entity-type filter, or search(..., user_uid=...)).
            # - Fail-closed: without a requesting user, user-owned domains
            #   return nothing (shared content is the unscoped floor).
            #   Authenticated routes always pass request.user_uid; an
            #   internal caller without one gets shared-only results.
            eligible_domains = [
                entity_type
                for entity_type in target_domains
                if self.supports_search(entity_type)
                and entity_type != EntityType.USER_ENTRY
                and not (
                    request.user_uid is None
                    and isinstance(entity_type, EntityType)
                    and entity_type.is_user_owned()
                )
            ]

            # The budget divisor derives from the REQUESTED filter: only an
            # explicit entity_types filter splits request.limit. The default
            # sweep keeps full limit per domain (divisor 1 — pre-existing
            # contract; dividing by ~10 sweep domains would starve them all).
            limit_per_domain = (
                request.limit // max(len(eligible_domains), 1)
                if request.has_entity_type_filter()
                else request.limit
            )
            limit_per_domain = max(limit_per_domain, 10)  # Minimum 10 per domain

            for entity_type in eligible_domains:
                service = self.get_service(entity_type)
                if service is None:
                    continue

                # Get the search service
                search_service = self._get_search_service(service)
                if search_service is None:
                    if not isinstance(service, SupportsTextSearch):
                        continue
                    search_service = service

                # Choose search strategy based on filters
                items = await self._execute_advanced_search(
                    search_service=search_service,
                    entity_type=entity_type,
                    request=request,
                    limit_per_domain=limit_per_domain,
                )

                if items:
                    # Apply scoring if user context available
                    if user_context:
                        items = await self._score_results(items, user_context)

                    results_by_domain[entity_type] = items
                    total_count += len(items)

            await self._publish_search_event(
                request.query_text,
                user_uid=request.user_uid or (user_context.user_uid if user_context else None),
                entry_point="advanced",
                result_count=total_count,
                domains=(
                    tuple(et.value for et in eligible_domains)
                    if request.has_entity_type_filter()
                    else ()
                ),
                semantic_boost=request.enable_semantic_boost,
                filters=request.to_property_filters(),
            )

            return Result.ok(
                UnifiedSearchResult(
                    query=request.query_text or "",
                    results_by_domain=results_by_domain,
                    total_count=total_count,
                )
            )

        except (AttributeError, TypeError, ValueError, KeyError) as e:
            self.logger.error(f"Advanced search failed: {e}")
            return Result.fail(Errors.database(operation="advanced_search", message=str(e)))
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Advanced search failed (unexpected): {e}")
            return Result.fail(Errors.database(operation="advanced_search", message=str(e)))

    async def _execute_advanced_search(
        self,
        search_service: SupportsTextSearch,
        entity_type: EntityType | NonKuDomain,
        request: "SearchRequest",
        limit_per_domain: int,
    ) -> list[SearchResultItem]:
        """
        Execute the appropriate search strategy based on request filters.

        Strategy selection:
        0. Semantic/Learning-Aware: Use vector search with boosting
        1. Graph + Text: Use search_connected_to if available
        2. Tags + Text: Use search_by_tags, then filter by text
        3. Text only: hybrid fulltext+vector rung for eligible PUBLIC
           curriculum domains (FULL tier), falling through to the domain's
           CONTAINS search when ineligible, empty, or failed

        ``limit_per_domain`` is computed by ``advanced_search`` from the
        ELIGIBLE domain count (skips already applied), not the raw request
        filter — otherwise skipped domains eat the budget of running ones.
        """
        items: list[SearchResultItem] = []

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
            # has_graph_traversal_filter() guarantees both are non-None; bind
            # locals so the type-checker can see the narrowing.
            related_uid = request.connected_to_uid
            relationship_type = request.connected_relationship
            if (
                isinstance(search_service, SupportsGraphTraversalSearch)
                and related_uid is not None
                and relationship_type is not None
            ):
                result = await search_service.search_connected_to(
                    query=request.query_text or "",
                    related_uid=related_uid,
                    relationship_type=relationship_type,
                    direction=request.connected_direction,
                    limit=limit_per_domain,
                    user_uid=request.user_uid,
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
            tags = request.tags_contain
            if isinstance(search_service, SupportsTagSearch) and tags is not None:
                result = await search_service.search_by_tags(
                    tags=tags,
                    match_all=request.tags_match_all,
                    limit=limit_per_domain * 2,  # Get more, then filter by text
                    user_uid=request.user_uid,
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

        # Strategy 3: Text search only — hybrid rung first, CONTAINS fallback
        else:
            items = await self._hybrid_curriculum_search(
                search_service=search_service,
                entity_type=entity_type,
                request=request,
                limit=limit_per_domain,
            )
            if items:
                return items

            result = await search_service.search(
                request.query_text or "", limit_per_domain, user_uid=request.user_uid
            )
            if result.is_ok and result.value:
                items = self._wrap_results(result.value, entity_type)

        return items

    async def _fallback_search(
        self,
        search_service: SupportsTextSearch,
        entity_type: EntityType | NonKuDomain,
        request: "SearchRequest",
        limit_per_domain: int,
    ) -> list[SearchResultItem]:
        """
        Fallback search when advanced features not available.

        Uses basic text search and post-filters results.
        """
        result = await search_service.search(
            request.query_text or "", limit_per_domain * 2, user_uid=request.user_uid
        )
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
        vector_search = self._vector_search
        if vector_search is None:
            self.logger.warning(
                "Vector search service not available, falling back to standard search"
            )
            return []

        # Must have query text for vector search
        if not request.query_text:
            self.logger.debug("Vector search requires query_text, skipping")
            return []

        # Get label from entity type. .capitalize() flattened multi-word
        # values ("path_step" → "Path_step"), missing those domains' vector
        # indexes entirely — the enum mapping is the one label source.
        neo_label = NeoLabel.from_domain(entity_type)
        if neo_label is None:
            self.logger.debug(f"No Neo4j label for {entity_type.value}, skipping vector search")
            return []
        label = neo_label.value

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
                    match_reason=self._create_match_reason(vec_result),
                )
                items.append(item)

            self.logger.info(
                f"Semantic/learning-aware search returned {len(items)} results for {entity_type}"
            )
            return items

        except (AttributeError, TypeError, ValueError, KeyError) as e:
            self.logger.error(f"Semantic/learning-aware search failed: {e}")
            return []  # Graceful degradation
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Semantic/learning-aware search failed (unexpected): {e}")
            return []  # Graceful degradation

    async def _hybrid_curriculum_search(
        self,
        search_service: SupportsTextSearch,
        entity_type: EntityType | NonKuDomain,
        request: "SearchRequest",
        limit: int,
    ) -> list[SearchResultItem]:
        """
        Hybrid fulltext+vector text search for PUBLIC curriculum domains.

        The relevance-ranked text rung (rulings D1(c)/D2(i), 2026-08-16):
        RRF-merges Lucene fulltext with vector similarity via
        ``Neo4jVectorSearchService.hybrid_search_with_metrics``. Eligibility is
        belt-and-braces — the explicit curriculum allowlist AND a live PUBLIC
        ``search_visibility`` read — because the hybrid path is label-wide
        (no user_uid scoping): an OWNER_ONLY domain must never reach it.

        Returns [] when ineligible, empty, or failed — the caller falls
        through to the domain's CONTAINS search unchanged.
        """
        if not isinstance(entity_type, EntityType):
            return []
        if entity_type.value not in self._HYBRID_TEXT_DOMAIN_VALUES:
            return []
        if not (
            isinstance(search_service, SupportsVisibilityDeclaration)
            and search_service.search_visibility is SearchVisibility.PUBLIC
        ):
            return []
        vector_search = self._vector_search
        if vector_search is None:
            # CORE tier (D3): no embeddings, no hybrid — CONTAINS unchanged
            return []
        if not request.query_text:
            return []

        label = NeoLabel.from_entity_type(entity_type).value

        try:
            result, _metrics = await vector_search.hybrid_search_with_metrics(
                label=label, query_text=request.query_text, limit=limit
            )

            if result.is_error:
                self.logger.warning(
                    f"Hybrid search failed for {entity_type.value}: "
                    f"{result.error} — falling back to CONTAINS"
                )
                return []
            if not result.value:
                return []

            # RRF scores live on a 0.001-0.05 scale while every other rung
            # emits ~0-1 relevance, and UnifiedSearchResult.get_top_results
            # compares combined scores ACROSS domains — normalize by the batch
            # max so hybrid-ranked domains don't sink below CONTAINS domains.
            max_score = max(item["score"] for item in result.value)
            items: list[SearchResultItem] = []
            for vec_result in result.value:
                node = vec_result["node"]
                score = vec_result["score"] / max_score if max_score > 0 else 0.0
                items.append(
                    SearchResultItem(
                        entity=node,  # The node dict
                        entity_type=entity_type,
                        uid=node.get("uid", ""),
                        title=node.get("title", ""),
                        relevance_score=score,
                        priority_score=node.get("priority_score", 0.0),
                        # RRF output carries no vector_score/semantic_boost
                        # keys, so _create_match_reason would mislabel it
                        match_reason="Keyword + semantic match",
                    )
                )

            self.logger.info(f"Hybrid search returned {len(items)} results for {entity_type.value}")
            return items

        except (AttributeError, TypeError, ValueError, KeyError) as e:
            self.logger.error(f"Hybrid search failed for {entity_type.value}: {e}")
            return []  # Fall through to CONTAINS
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.error(f"Hybrid search failed for {entity_type.value} (unexpected): {e}")
            return []  # Fall through to CONTAINS

    def _create_match_reason(self, vec_result: dict) -> str:
        """
        Create human-readable match reason from vector search result.

        Args:
            vec_result: Vector search result dict

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
                    from core.utils.type_converters import get_enum_value

                    priority_value = get_enum_value(entity_priority)
                    if priority_value not in [p.value for p in parsed.priorities]:
                        continue

            # Check status filter
            if parsed.statuses:
                entity_status = getattr(entity, "status", None)
                if entity_status:
                    from core.utils.type_converters import get_enum_value

                    status_value = get_enum_value(entity_status)
                    if status_value not in [s.value for s in parsed.statuses]:
                        continue

            filtered.append(item)

        return filtered

    async def _score_results(
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

        # Enrich habits with SUPPORTS_GOAL edge before scoring so ACTIVE_GOAL_SUPPORT
        # uses the real graph edge rather than scoring 0.0 for every habit.
        enriched_habits: dict[str, Any] = {}
        habit_items = [item for item in items if item.entity_type == EntityType.HABIT]
        if habit_items and self._habits is not None:
            enriched = await self._habits.search.enrich_with_goal_links(
                [item.entity for item in habit_items], user_context.active_goal_uids
            )
            enriched_habits = {h.uid: h for h in enriched}

        scored_items = []
        for item in items:
            score = 0.0
            entity = item.entity

            # Use appropriate scoring function based on entity type
            try:
                match item.entity_type:
                    case EntityType.TASK:
                        priority_score = score_task(entity, user_context)
                        score = priority_score.total
                    case EntityType.GOAL:
                        priority_score = score_goal(entity, user_context)
                        score = priority_score.total
                    case EntityType.HABIT:
                        entity = enriched_habits.get(item.uid, item.entity)
                        priority_score = score_habit(entity, user_context)
                        score = priority_score.total
                    case EntityType.EVENT:
                        priority_score = score_event(entity, user_context)
                        score = priority_score.total
                    case EntityType.CHOICE:
                        priority_score = score_choice(entity, user_context)
                        score = priority_score.total
                    case EntityType.PRINCIPLE:
                        priority_score = score_principle(entity, user_context)
                        score = priority_score.total
            except (ValueError, TypeError, AttributeError, KeyError, ZeroDivisionError) as e:
                self.logger.debug(f"Scoring failed for {item.uid}: {e}")

            # Create new item with score
            scored_items.append(
                SearchResultItem(
                    entity=entity,
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
