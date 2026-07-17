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
    faceted_search_raw). Do not add members without wiring them through;
    unimplemented options were deleted in July 2026 (One Path Forward).
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
