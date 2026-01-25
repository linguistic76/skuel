"""
Knowledge Request Models (Tier 1 - External)
============================================

Pydantic models for API boundaries - validation and serialization.
These handle external input/output with proper validation.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from core.models.shared_enums import Domain

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO


class KuCreateRequest(BaseModel):
    """External API request for creating knowledge."""

    title: str = Field(min_length=1, max_length=200, description="Title of the knowledge unit")
    content: str = Field(min_length=1, description="Main content/body")
    domain: Domain = Field(description="Knowledge domain")

    # Optional fields
    tags: list[str] = Field(
        default_factory=list, description="Associated tags for categorization and search"
    )
    prerequisites: list[str] = Field(
        default_factory=list,
        description="List of prerequisite KnowledgeUnit UIDs that should be learned first",
    )
    complexity: str | None = Field(
        default="medium",
        pattern="^(basic|medium|advanced)$",
        description="Difficulty level: 'basic', 'medium', or 'advanced' (NOT 'beginner'!)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Introduction to Python",
                "content": "Python is a high-level programming language...",
                "domain": "TECH",
                "tags": ["python", "programming"],
                "complexity": "basic",
            }
        }
    )


class KuUpdateRequest(BaseModel):
    """External API request for updating knowledge."""

    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = Field(None, min_length=1)
    tags: list[str] | None = None
    prerequisites: list[str] | None = None
    complexity: str | None = Field(None, pattern="^(basic|medium|advanced)$")

    model_config = ConfigDict(
        json_schema_extra={"example": {"title": "Updated Title", "tags": ["python", "advanced"]}}
    )


class KuResponse(BaseModel):
    """External API response for knowledge."""

    uid: str
    title: str
    content: str
    domain: Domain

    # Semantic fields
    quality_score: float = Field(ge=0.0, le=1.0)
    complexity: str
    semantic_links: list[str]

    # Metadata
    created_at: datetime
    updated_at: datetime
    tags: list[str]

    # Relationships
    prerequisites: list[str]
    enables: list[str]

    # Computed fields
    word_count: int
    estimated_reading_time: int

    model_config = ConfigDict(
        # Pydantic V2 serializes enums and datetimes automatically
    )

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "KuResponse":
        """
        Create response from DTO.

        GRAPH-NATIVE: Relationship fields (prerequisites, enables) set to empty lists.
        Service layer must populate via graph queries:
        - prerequisites: backend.get_related_uids(uid, "REQUIRES_KNOWLEDGE", "outgoing")
        - enables: backend.get_related_uids(uid, "ENABLES", "outgoing")
        """

        # Calculate computed fields
        word_count = len(dto.content.split())
        estimated_reading_time = max(1, word_count // 200)

        return cls(
            uid=dto.uid,
            title=dto.title,
            content=dto.content,
            domain=dto.domain,
            quality_score=dto.quality_score,
            complexity=dto.complexity,
            semantic_links=dto.semantic_links,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            tags=dto.tags,
            prerequisites=[],  # GRAPH QUERY: backend.get_related_uids(uid, "REQUIRES_KNOWLEDGE", "outgoing")
            enables=[],  # GRAPH QUERY: backend.get_related_uids(uid, "ENABLES", "outgoing")
            word_count=word_count,
            estimated_reading_time=estimated_reading_time,
        )


class KuListResponse(BaseModel):
    """Response for listing multiple knowledge items."""

    items: list[KuResponse]
    total: int
    page: int = 1
    page_size: int = 20

    model_config = ConfigDict(
        json_schema_extra={"example": {"items": [], "total": 100, "page": 1, "page_size": 20}}
    )
