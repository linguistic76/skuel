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
