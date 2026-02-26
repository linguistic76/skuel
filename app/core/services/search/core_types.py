"""
Search Core Types (Pure Dataclasses)
=====================================

*Last updated: 2026-01-04*

Pure, framework-agnostic dataclasses for search engine internals.
These types are used within the core search algorithms and remain
free of any Pydantic dependencies.

This follows the architectural principle: Pure domain inside.

Note (January 2026): Unused classes removed per "One Path Forward" principle.
Removed: QueryUnderstanding, SearchContext, RelatedContent, SearchResult, Level.
These were skeleton classes from an incomplete refactor.
"""

from __future__ import annotations

__version__ = "2.0"

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.enums import Domain


@dataclass(frozen=True)
class FacetSet:
    """
    Core facet representation for search execution.

    This is the internal representation that drives the actual
    search queries against Neo4j or other backends.

    Used by:
        - core/services/query/faceted_query_builder.py
        - core/services/query_builder.py
    """

    domain: Domain | None = None
    level: str | None = None  # "intro", "intermediate", "advanced"
    intents: list[str] | None = None
    topics: list[str] | None = None
    filters: dict[str, object] | None = None


__all__ = ["FacetSet"]
