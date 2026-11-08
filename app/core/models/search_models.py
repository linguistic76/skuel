"""
Search Boundary Models
======================

The cross-domain search result DTO. The search request a door binds is
``SearchRequest`` (core/models/search_request.py).
"""

from dataclasses import dataclass, field

# ============================================================================
# SEARCH RESULT DTO (Tier 2 - Data Transfer)
# ============================================================================


@dataclass
class SearchResultDTO:
    """DTO for cross-domain search results."""

    uid: str
    title: str
    domain: str
    snippet: str | None = None
    user_mastery_level: float | None = None
    is_accessible: bool = True
    mastery_warnings: list[str] = field(default_factory=list)
    score: float | None = None
    highlights: list[str] = field(default_factory=list)
