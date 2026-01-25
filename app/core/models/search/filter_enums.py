"""
Search Filter Enums - Type-Safe Filter Operations
==================================================

Enums for search filtering operations and sorting.

Version: 1.0.0
Date: 2025-11-29
"""

from enum import Enum


class FilterOperator(str, Enum):
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


class SearchSortOrder(str, Enum):
    """
    Sort ordering for search results.

    Domains may support different sort orders based on their fields.
    """

    # Universal sort orders
    RELEVANCE = "relevance"  # Text search relevance score
    CREATED_DESC = "created_desc"  # Newest first
    CREATED_ASC = "created_asc"  # Oldest first
    UPDATED_DESC = "updated_desc"  # Recently modified first

    # Priority-based (Tasks, Goals, Events)
    PRIORITY_DESC = "priority_desc"  # Critical → Low
    PRIORITY_ASC = "priority_asc"  # Low → Critical

    # Time-based (Tasks, Goals, Events, Choices)
    DUE_DATE_ASC = "due_date_asc"  # Soonest deadline first
    DUE_DATE_DESC = "due_date_desc"  # Latest deadline first

    # Progress-based (Goals, Habits)
    PROGRESS_DESC = "progress_desc"  # Highest progress first
    PROGRESS_ASC = "progress_asc"  # Lowest progress first

    # Streak-based (Habits only)
    STREAK_DESC = "streak_desc"  # Longest streak first
    STREAK_ASC = "streak_asc"  # Shortest/broken streak first

    # Custom scoring (context-aware)
    CUSTOM_SCORE = "custom_score"  # UserContext-based scoring

    def get_sort_field(self) -> str | None:
        """
        Get the field name to sort by.

        Returns:
            Field name or None for custom scoring
        """
        field_map = {
            self.CREATED_DESC: "created_at",
            self.CREATED_ASC: "created_at",
            self.UPDATED_DESC: "updated_at",
            self.PRIORITY_DESC: "priority",
            self.PRIORITY_ASC: "priority",
            self.DUE_DATE_ASC: "due_date",
            self.DUE_DATE_DESC: "due_date",
            self.PROGRESS_DESC: "progress_percentage",
            self.PROGRESS_ASC: "progress_percentage",
            self.STREAK_DESC: "current_streak",
            self.STREAK_ASC: "current_streak",
        }
        return field_map.get(self)

    def is_descending(self) -> bool:
        """Check if this sort order is descending."""
        return self.value.endswith("_desc") or self == self.RELEVANCE
