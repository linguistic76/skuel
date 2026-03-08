"""Article domain request models.

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from pydantic import Field

from core.models.enums import (
    Confidence,
    Domain,
    KuComplexity,
    LearningLevel,
    SELCategory,
)
from core.models.request_base import CreateRequestBase


class ArticleCreateRequest(CreateRequestBase):
    """Create admin-authored article (essay-like teaching composition)."""

    title: str = Field(min_length=1, max_length=200, description="Title of the article")
    domain: Domain = Field(description="Knowledge domain")

    # Content
    content: str | None = Field(None, description="Body text")
    summary: str | None = Field(None, max_length=500, description="Brief summary")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")

    # Learning metadata
    complexity: KuComplexity = Field(default=KuComplexity.MEDIUM, description="Difficulty level")
    sel_category: SELCategory | None = Field(None, description="SEL category lens")
    learning_level: LearningLevel = Field(
        default=LearningLevel.BEGINNER, description="Target learning level"
    )
    estimated_time_minutes: int = Field(default=15, ge=1, description="Estimated completion time")
    difficulty_rating: float = Field(default=0.5, ge=0.0, le=1.0, description="Difficulty 0.0-1.0")
    confidence: Confidence | None = Field(
        None, description="Admin-assessed certainty about this knowledge"
    )
