"""
Search Module - Type-Safe Search Infrastructure
=================================================

*Last updated: 2026-01-04*

Provides type-safe search infrastructure for SKUEL's domains:
1. SearchRequest - THE canonical search request model (Pydantic)
2. Query Parser - Natural language to semantic filters
3. Scoring Framework - Unified priority scoring with component breakdown
4. Search Router - KuType-driven cross-domain search routing
5. Base Filters - For domain-specific local filter classes

One Path Forward (January 2026):
    SearchRequest is THE canonical search request type:
    - Domain-specific filter classes (TaskSearchFilters, etc.) were removed
    - UnifiedSearchRequest was merged INTO SearchRequest
    - For domain-specific filtering, define local filter classes within services
      (see MocSearchFilters pattern)

Usage:
    from core.models.search import (
        # Query parsing
        parse_search_query, ParsedSearchQuery,
        # Scoring
        score_task, score_goal, PriorityScore,
        # Routing
        SearchRouter, UnifiedSearchResult,
    )
    from core.models.search_request import SearchRequest  # THE canonical model

    # Natural language parsing
    parsed = parse_search_query("urgent health tasks")
    # → priorities: [CRITICAL, HIGH], domains: [HEALTH]

    # Unified scoring
    score = score_task(task, user_context)
    print(score.explain())  # Component breakdown

    # KuType-driven routing
    router = SearchRouter(services)
    result = await router.intelligent_search("urgent health tasks")

    # Advanced unified search (using SearchRequest, THE canonical model)
    request = SearchRequest(
        query_text="machine learning",
        entity_types=[KuType.CURRICULUM, KuType.TASK],
        connected_to_uid="ku.python-basics",
        connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
        tags_contain=["python"],
    )
    result = await router.advanced_search(request)

See Also:
    - core/models/search_request.py - SearchRequest (THE canonical model)
    - DomainSearchOperations protocol for search interface
    - RelationshipName enum for relationship-based filtering
    - KuType/NonKuDomain enums for domain classification

Version: 3.0.0
Date: 2026-01-04
Changes:
- v3.0.0: Merged UnifiedSearchRequest INTO SearchRequest (One Path Forward)
- v2.0.0: Removed unused Activity Domain filter classes per One Path Forward
- v1.3.0: Added UnifiedSearchRequest and advanced_search
- v1.2.0: Added SearchRouter for KuType-driven cross-domain search
- v1.1.0: Added unified scoring framework
- v1.0.0: Initial filter types and query parsing
"""

from core.models.search.filter_enums import (
    FilterOperator,
    SearchSortOrder,
)
from core.models.search.filters import (
    BaseSearchFilters,
    DateRangeFilters,
)
from core.models.search.query_parser import (
    ParsedSearchQuery,
    SearchQueryParser,
    parse_search_query,
)
from core.models.search.scoring import (
    ComponentScore,
    DomainScoringStrategy,
    PriorityScore,
    # Core types
    ScoringComponent,
    score_choice,
    # Utility functions
    score_deadline_proximity,
    score_event,
    score_goal,
    score_goal_alignment,
    score_habit,
    score_principle,
    score_priority_level,
    score_progress_momentum,
    score_streak_protection,
    # Domain-specific scoring
    score_task,
)
from core.models.search.search_router import (
    SearchableService,
    # Result types
    SearchResultItem,
    # Router
    SearchRouter,
    UnifiedSearchResult,
    # Utility functions
    get_search_service_attr,
    is_searchable_domain,
)

__all__ = [
    # Base filters (for domain-specific local filter classes)
    "BaseSearchFilters",
    "ComponentScore",
    "DateRangeFilters",
    "DomainScoringStrategy",
    # Enums
    "FilterOperator",
    # Query parsing
    "ParsedSearchQuery",
    "PriorityScore",
    # Scoring framework
    "ScoringComponent",
    "SearchQueryParser",
    "SearchResultItem",
    # Search router
    "SearchRouter",
    "SearchSortOrder",
    "SearchableService",
    # Result types (UnifiedSearchRequest merged into SearchRequest)
    "UnifiedSearchResult",
    "get_search_service_attr",
    "is_searchable_domain",
    "parse_search_query",
    "score_choice",
    # Scoring utilities
    "score_deadline_proximity",
    "score_event",
    "score_goal",
    "score_goal_alignment",
    "score_habit",
    "score_principle",
    "score_priority_level",
    "score_progress_momentum",
    "score_streak_protection",
    # Domain scoring functions
    "score_task",
]
