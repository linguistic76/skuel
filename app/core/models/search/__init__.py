"""
Search Module - Type-Safe Search Infrastructure
=================================================

Provides type-safe search MODELS for SKUEL's domains:
1. SearchRequest - THE canonical search request model (Pydantic)
2. Query Parser - Natural language to semantic filters
3. Scoring Framework - Unified priority scoring with component breakdown
4. Base Filters - For domain-specific local filter classes

The cross-domain search ORCHESTRATOR lives in
``core/orchestrator/search_router.py`` (SearchRouter + its result containers) —
this package holds the data shapes and pure scoring it routes with.

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
    )
    from core.models.search_request import SearchRequest  # THE canonical model

    # Natural language parsing
    parsed = parse_search_query("urgent health tasks")
    # → priorities: [CRITICAL, HIGH], domains: [HEALTH]

    # Unified scoring
    score = score_task(task, user_context)
    print(score.explain())  # Component breakdown

See Also:
    - core/models/search_request.py - SearchRequest (THE canonical model)
    - core/orchestrator/search_router.py - SearchRouter (cross-domain routing)
    - DomainSearchOperations protocol for search interface
    - RelationshipName enum for relationship-based filtering
    - EntityType/NonKuDomain enums for domain classification
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
    "SearchSortOrder",
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
