"""
Search Filter Enums - Type-Safe Filter Operations
==================================================

Enums for search filtering operations and sorting.

Version: 1.0.0
Date: 2025-11-29
"""

from enum import StrEnum


class FilterOperator(StrEnum):
    """
    Operators for numeric and date filtering.

    Used with field__operator syntax in UniversalBackend queries.

    Examples:
        # In filter dataclass
        target_date__lte = date.today()  # lte operator

        # Translates to backend query
        find_by(target_date__lte=date.today())
    """

    EQ = "eq"  # equals (default)
    NE = "ne"  # not equals
    GT = "gt"  # greater than
    GTE = "gte"  # greater than or equal
    LT = "lt"  # less than
    LTE = "lte"  # less than or equal
    IN = "in"  # in list
    CONTAINS = "contains"  # string contains
    BETWEEN = "between"  # between range (requires two values)

    def apply_to_field(self, field_name: str) -> str:
        """
        Generate field__operator syntax for backend queries.

        Args:
            field_name: Base field name

        Returns:
            Field name with operator suffix (e.g., "target_date__lte")

        Example:
            >>> FilterOperator.LTE.apply_to_field("target_date")
            "target_date__lte"
        """
        if self == FilterOperator.EQ:
            return field_name  # No suffix for equality
        return f"{field_name}__{self.value}"


class SearchSortOrder(StrEnum):
    """
    Sort ordering for faceted search results.

    THE implemented sort set — every member here is honored end-to-end
    (route → SearchRequest → graph_aware_faceted_search → ORDER BY in
    faceted_search_raw). Do not add members without wiring them through
    (One Path Forward).
    """

    # Text-search relevance / recency default. No explicit field: the
    # backend falls back to the domain's `DomainConfig.search_order_by`
    # (updated_at for curriculum domains), descending — today's behavior.
    RELEVANCE = "relevance"
    CREATED_DESC = "created_desc"  # Newest first
    CREATED_ASC = "created_asc"  # Oldest first
    UPDATED_DESC = "updated_desc"  # Recently modified first
    TITLE_ASC = "title_asc"  # Title A-Z

    def get_sort_field(self) -> str | None:
        """
        Get the field name to sort by.

        Returns:
            Field name, or None for RELEVANCE (caller falls back to the
            domain's configured ``search_order_by``).
        """
        field_map = {
            self.CREATED_DESC: "created_at",
            self.CREATED_ASC: "created_at",
            self.UPDATED_DESC: "updated_at",
            self.TITLE_ASC: "title",
        }
        return field_map.get(self)

    def is_descending(self) -> bool:
        """Check if this sort order is descending."""
        return self.value.endswith("_desc") or self == self.RELEVANCE

    @classmethod
    def from_string(cls, value: str | None) -> "SearchSortOrder":
        """Parse a form/query value; unknown or empty → RELEVANCE (fail-soft boundary)."""
        if not value:
            return cls.RELEVANCE
        try:
            return cls(value)
        except ValueError:
            return cls.RELEVANCE


class BodyFoldStatus(StrEnum):
    """Whether the lesson-BODY chunk fold ran on a `/search` response.

    The fold (`SearchRouter._augment_with_body_chunks`) is a Digital-layer
    enhancement that fails SOFT by design: on the CORE tier, on a vector-search
    error, or on a request that reaches neither body-chunk domain, `/search`
    still returns its frontmatter results. That is right for a user and opaque
    to every caller — a response with no body hits reads identically whether
    the fold searched and found nothing or never ran at all.

    This status is that distinction, made observable. It is a report ABOUT the
    fold, not a promise that any body hit survived into the results: a
    COMPLETED fold whose every parent was already present contributes zero
    cards (`parents_added = 0`) and is still the healthy case.

    Ruled 2026-08-30 (eval arc PR-2) after `body` — a real user query — was
    measured returning zero chunk candidates at the 0.68 floor, indistinguishable
    from a dead Digital layer without an out-of-band probe.
    """

    NOT_ATTEMPTED = "not_attempted"  # request reached no body-chunk domain, or no query text
    UNAVAILABLE = "unavailable"  # no vector search (CORE tier)
    FAILED = "failed"  # chunk search errored — fail-soft, results still stand
    COMPLETED = "completed"  # chunk search ran to completion

    def searched_bodies(self) -> bool:
        """True when lesson bodies were actually searched for this response.

        The predicate a caller wants before reading an empty body contribution
        as "the corpus has nothing" — only COMPLETED licenses that reading.
        """
        return self is BodyFoldStatus.COMPLETED

    def is_degraded(self) -> bool:
        """True when the fold was wanted but could not run.

        NOT_ATTEMPTED is not degraded: the request never asked for bodies.
        """
        return self in (BodyFoldStatus.UNAVAILABLE, BodyFoldStatus.FAILED)
