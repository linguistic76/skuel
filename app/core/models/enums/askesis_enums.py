"""Askesis-specific enums for pedagogical companion interactions."""

from enum import StrEnum


class QueryComplexity(StrEnum):
    """Complexity levels of user queries."""

    SIMPLE = "simple"  # Single domain, straightforward
    MODERATE = "moderate"  # 2-3 domains, some complexity
    COMPLEX = "complex"  # Multiple domains, interconnected
    SYSTEMIC = "systemic"  # Life-wide implications, many domains


class IntegrationSuccess(StrEnum):
    """Success levels of domain integration."""

    EXCELLENT = "excellent"  # Perfect synthesis, high user value
    GOOD = "good"  # Effective integration, clear benefit
    ACCEPTABLE = "acceptable"  # Basic integration, some value
    POOR = "poor"  # Weak integration, limited value
    FAILED = "failed"  # No meaningful integration achieved


class AggregationPeriod(StrEnum):
    """Server-resolved time periods for Askesis aggregation query tools.

    The tool-selection args models express relative time ONLY through this enum
    — the model never emits dates, so it can never volunteer a stale or
    hallucinated "today". Resolution to concrete bounds happens server-side
    (``core.services.askesis.query_tools.resolve_period``) against the server's
    date. Every member is a CLOSED calendar range (weeks start Monday), so an
    answer can always state the exact bounds it filtered on.
    """

    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_QUARTER = "this_quarter"
    LAST_QUARTER = "last_quarter"
    THIS_YEAR = "this_year"
    LAST_YEAR = "last_year"
