"""
Search Boundary Models
======================

Pydantic request models and DTOs for cross-domain search infrastructure.

Previously misplaced in core/models/transcription/ — relocated here
because these are generic search models used by QueryBuilder, Askesis,
and FacetedQueryBuilder with zero transcription coupling.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

# ============================================================================
# SEARCH REQUEST MODELS (Tier 1 - Pydantic)
# ============================================================================


class FacetSetRequest(BaseModel):
    """Request model for search facets."""

    domain: Literal["habits", "knowledge", "tasks", "finance", "transcription"] | None = None
    level: Literal["intro", "intermediate", "advanced"] | None = None
    intents: list[str] = Field(default_factory=list, description="Search intents")
    topics: list[str] = Field(default_factory=list, description="Normalized key terms/tags")
    filters: dict[str, Any] = Field(default_factory=dict, description="Extra filters")


class SearchQueryRequest(BaseModel):
    """Request model for complete search query."""

    text: str = Field(min_length=1, description="Search query text")
    user_uid: str = Field(description="User UID for personalization")
    facets: FacetSetRequest = Field(default_factory=FacetSetRequest)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    include_relationships: bool = Field(default=True)
    check_mastery: bool = Field(default=True)


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
