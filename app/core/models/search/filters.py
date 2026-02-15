"""
Search Filter Dataclasses - Base Types Only
============================================

*Last updated: 2026-01-04*

Base filter types for search operations. Domain-specific filters should be
defined locally within their service modules (see MocSearchFilters pattern).

One Path Forward (January 2026):
    The Activity Domain filter classes (TaskSearchFilters, GoalSearchFilters, etc.)
    were removed as they were never integrated. SearchRequest (Pydantic model in
    core/models/search_request.py) is THE canonical search request type.

    For domain-specific search with typed filters:
    1. Use SearchRequest for UI/API searches (rich feature set, graph patterns)
    2. Define local filter classes within services when needed (see MocSearchFilters)
    3. BaseSearchFilters provides the common base for local filter classes

Architecture (One Path Forward, January 2026):
    SearchRequest (Pydantic)     → UI/API entry point
        ↓
    SearchRouter.faceted_search  → THE search orchestrator
        ↓
    Domain SearchServices        → graph_aware_faceted_search() or search()

    DomainService.search_filtered(filters: LocalFilters)
        → Domain-specific filtered search (e.g., MocSearchService)

Version: 2.0.0
Date: 2026-01-04
Changes:
    - v2.0.0: Removed unused Activity Domain filter classes per One Path Forward
    - v1.0.0: Initial filter types (2025-11-29)
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from core.models.enums import Domain, KuStatus
from core.models.relationship_names import RelationshipName
from core.services.protocols.base_protocols import Direction

# =============================================================================
# DATE RANGE FILTERS - Temporal query support
# =============================================================================


@dataclass(frozen=True)
class DateRangeFilters:
    """
    Filters for time-based queries.

    Can be composed with domain-specific filters for temporal filtering.

    Usage:
        date_filter = DateRangeFilters(days_ahead=7)
        start, end = date_filter.get_date_range()
    """

    days_ahead: int | None = None
    days_back: int | None = None
    start_date: date | None = None
    end_date: date | None = None

    def get_date_range(self) -> tuple[date | None, date | None]:
        """
        Calculate effective date range from days_ahead/days_back or explicit dates.

        Returns:
            Tuple of (start_date, end_date) - either may be None
        """
        from datetime import timedelta

        effective_start = self.start_date
        effective_end = self.end_date

        if self.days_back is not None and effective_start is None:
            effective_start = date.today() - timedelta(days=self.days_back)

        if self.days_ahead is not None and effective_end is None:
            effective_end = date.today() + timedelta(days=self.days_ahead)

        return effective_start, effective_end


# =============================================================================
# BASE FILTERS - Common across all domains
# =============================================================================


@dataclass(frozen=True)
class BaseSearchFilters:
    """
    Common filters across all domains.

    Domain-specific filter classes should inherit from this base.
    See MocSearchFilters in core/services/moc/moc_search_service.py for example.

    Note: For most search operations, use SearchRequest (Pydantic model) instead.
    BaseSearchFilters is primarily for internal service implementations that need
    type-safe frozen filter objects.

    Usage:
        @dataclass(frozen=True)
        class MocSearchFilters(BaseSearchFilters):
            is_template: bool | None = None
            visibility: str | None = None

        filters = MocSearchFilters(query="python", domain=Domain.TECH)
        result = await moc_service.search_filtered(filters)
    """

    # Text search
    query: str | None = None
    limit: int = 50
    offset: int = 0

    # Status filters (enum for type safety)
    status: KuStatus | None = None
    domain: Domain | None = None

    # Relationship filters
    related_uid: str | None = None
    relationship_type: RelationshipName | None = None
    relationship_direction: Direction = "outgoing"

    # User context
    user_uid: str | None = None

    # Sorting
    sort_order: str | None = None  # SearchSortOrder value

    def to_query_params(self) -> dict[str, Any]:
        """
        Convert filters to backend query parameters.

        Returns:
            Dict suitable for UniversalBackend.find_by()
        """
        params: dict[str, Any] = {}

        if self.status is not None:
            params["status"] = self.status.value

        if self.domain is not None:
            params["domain"] = self.domain.value

        if self.user_uid is not None:
            params["user_uid"] = self.user_uid

        if self.limit:
            params["limit"] = self.limit

        return params

    def has_text_query(self) -> bool:
        """Check if this filter includes a text search query."""
        return self.query is not None and len(self.query.strip()) > 0

    def has_relationship_filter(self) -> bool:
        """Check if this filter includes relationship-based filtering."""
        return self.related_uid is not None and self.relationship_type is not None


__all__ = [
    "BaseSearchFilters",
    "DateRangeFilters",
]
