"""
Knowledge Request Models (Tier 1 - External)
============================================

Pydantic models for API boundaries - validation and serialization.
These handle external input/output with proper validation.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from core.models.enums import Domain, KuComplexity, LearningLevel, SELCategory

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
    complexity: KuComplexity = Field(
        default=KuComplexity.MEDIUM,
        description="Difficulty level: BASIC, MEDIUM, or ADVANCED",
    )

    # Learning metadata
    sel_category: SELCategory | None = Field(None, description="SEL category lens")
    learning_level: LearningLevel | None = Field(None, description="Target learning level")
    summary: str | None = Field(None, max_length=500, description="Brief summary")
    estimated_time_minutes: int | None = Field(None, ge=1, description="Estimated completion time")
    difficulty_rating: float | None = Field(None, ge=0.0, le=1.0, description="Difficulty 0.0-1.0")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Introduction to Python",
                "content": "Python is a high-level programming language...",
                "domain": "TECH",
                "tags": ["python", "programming"],
                "complexity": "BASIC",
                "sel_category": "self_awareness",
                "learning_level": "beginner",
            }
        }
    )


class KuUpdateRequest(BaseModel):
    """External API request for updating knowledge."""

    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = Field(None, min_length=1)
    tags: list[str] | None = None
    complexity: KuComplexity | None = None

    # Learning metadata
    sel_category: SELCategory | None = None
    learning_level: LearningLevel | None = None
    summary: str | None = Field(None, max_length=500)
    estimated_time_minutes: int | None = Field(None, ge=1)
    difficulty_rating: float | None = Field(None, ge=0.0, le=1.0)

    model_config = ConfigDict(
        json_schema_extra={"example": {"title": "Updated Title", "tags": ["python", "advanced"]}}
    )


class KuResponse(BaseModel):
    """External API response for knowledge."""

    uid: str
    title: str
    content: str | None = None  # Populated on detail view from Content node
    domain: Domain

    # Semantic fields
    quality_score: float = Field(ge=0.0, le=1.0)
    complexity: KuComplexity
    semantic_links: list[str]

    # Metadata
    created_at: datetime
    updated_at: datetime
    tags: list[str]

    # Learning metadata
    sel_category: SELCategory | None = None
    summary: str = ""
    learning_level: LearningLevel = LearningLevel.BEGINNER
    estimated_time_minutes: int = 15
    difficulty_rating: float = Field(default=0.5, ge=0.0, le=1.0)

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
        - prerequisites: backend.get_related_uids(uid, "REQUIRES_KNOWLEDGE", "incoming")
        - enables: backend.get_related_uids(uid, "ENABLES_KNOWLEDGE", "outgoing")
        """

        # Use stored word_count from DTO
        estimated_reading_time = max(1, dto.word_count // 200)

        return cls(
            uid=dto.uid,
            title=dto.title,
            content=None,  # Content lives on :Content node, populated separately on detail views
            domain=dto.domain,
            quality_score=dto.quality_score,
            complexity=dto.complexity,
            semantic_links=dto.semantic_links,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            tags=dto.tags,
            # Learning metadata
            sel_category=dto.sel_category,
            summary=dto.summary,
            learning_level=dto.learning_level,
            estimated_time_minutes=dto.estimated_time_minutes,
            difficulty_rating=dto.difficulty_rating,
            prerequisites=[],  # GRAPH-NATIVE: Query via backend.get_related_uids(uid, "REQUIRES_KNOWLEDGE", "incoming")
            enables=[],  # GRAPH-NATIVE: Query via backend.get_related_uids(uid, "ENABLES_KNOWLEDGE", "outgoing")
            word_count=dto.word_count,
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
