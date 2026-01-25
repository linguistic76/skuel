"""
Finance Category Types (Pattern 3C Migration)
==============================================

Frozen dataclasses for finance category lookup returns.
Replaces dict[str, Any] with strongly-typed, immutable structures.

Pattern 3C Phase 2: Internal Analytics Types
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CategorySuggestion:
    """Suggested expense category based on description matching."""

    code: str
    name: str
    parent: str | None
    confidence: str  # "high", "medium", "low"


@dataclass(frozen=True)
class CategoryInfo:
    """Detailed category information."""

    name: str
    code: str
    description: str
    tags: list[str]
    parent: str | None
    path: str
