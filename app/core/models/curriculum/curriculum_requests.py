"""
Curriculum Domain Request Models
=================================

Pydantic models for the 3 Curriculum Domains:
KU (Curriculum), Learning Steps, Learning Paths.

Also includes MOC create request.

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from pydantic import BaseModel, Field

from core.models.enums import (
    Domain,
    KuComplexity,
    LearningLevel,
    Priority,
    SELCategory,
)
from core.models.enums.curriculum_enums import LpType, StepDifficulty
from core.models.request_base import CreateRequestBase

# =============================================================================
# CREATE REQUESTS — Content Processing (Curriculum)
# =============================================================================


class CurriculumCreateRequest(CreateRequestBase):
    """Create admin-authored curriculum knowledge (CURRICULUM type)."""

    title: str = Field(min_length=1, max_length=200, description="Title of the knowledge unit")
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


# =============================================================================
# CREATE REQUESTS — Shared/Curriculum (MOC, LS, LP)
# =============================================================================


class MocCreateRequest(CreateRequestBase):
    """Create an MOC entity (Map of Content — KU organizing KUs). Admin-only, shared."""

    title: str = Field(min_length=1, max_length=200, description="MOC title")
    content: str | None = Field(None, description="MOC content")
    summary: str | None = Field(None, max_length=500, description="Brief summary")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")
    tags: list[str] = Field(default_factory=list, description="Tags")


class LearningStepCreateRequest(CreateRequestBase):
    """Create a LEARNING_STEP entity (step in a learning path). Admin-only, shared."""

    title: str = Field(min_length=1, max_length=200, description="Step title")
    intent: str = Field(min_length=1, description="Step intent/purpose")
    description: str | None = Field(None, max_length=2000, description="Step description")

    # Curriculum placement
    learning_path_uid: str | None = Field(None, description="Parent LP UID")
    sequence: int | None = Field(None, ge=1, description="Order in learning path")

    # Learning parameters
    mastery_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Mastery threshold")
    estimated_hours: float = Field(default=1.0, gt=0, description="Estimated hours")
    difficulty: StepDifficulty = Field(
        default=StepDifficulty.MODERATE, description="Step difficulty"
    )

    # Organization
    domain: Domain = Field(default=Domain.PERSONAL, description="Domain")
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority")
    notes: str | None = Field(None, description="Additional notes")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Knowledge relationships
    primary_knowledge_uids: list[str] = Field(default_factory=list, description="Primary KU UIDs")
    supporting_knowledge_uids: list[str] = Field(
        default_factory=list, description="Supporting KU UIDs"
    )
    prerequisite_step_uids: list[str] = Field(
        default_factory=list, description="Prerequisite step UIDs"
    )
    prerequisite_knowledge_uids: list[str] = Field(
        default_factory=list, description="Prerequisite KU UIDs"
    )


class LearningPathCreateRequest(CreateRequestBase):
    """Create a LEARNING_PATH entity (ordered sequence of steps). Admin-only, shared."""

    title: str = Field(min_length=1, max_length=200, description="Learning path title")
    description: str | None = Field(None, max_length=2000, description="Path description")
    lp_goal: str = Field(min_length=1, description="Learning path goal statement")
    domain: Domain = Field(description="Knowledge domain")

    # Path characteristics
    lp_type: LpType = Field(default=LpType.STRUCTURED, description="Path type")
    difficulty_level: str = Field(default="intermediate", description="Difficulty level")
    estimated_hours: float | None = Field(None, gt=0.0, description="Total estimated hours")

    # Structure
    prerequisites: list[str] = Field(default_factory=list, description="Prerequisites")
    outcomes: list[str] = Field(default_factory=list, description="Expected outcomes")
    tags: list[str] = Field(default_factory=list, description="Tags")


# =============================================================================
# LEARNING PATH FILTER & PROGRESS
# =============================================================================


class LearningPathFilterRequest(BaseModel):
    """Filter request for learning path browsing UI.

    Used by FormGenerator for filter form generation.
    """

    difficulty: str | None = Field(None, description="Filter by difficulty level")
    domain: str | None = Field(None, description="Filter by domain")
    duration: str | None = Field(None, description="Filter by time commitment")


class LearningPathProgressRequest(BaseModel):
    """Request model for updating learning progress on a step."""

    step_uid: str = Field(..., description="Step to update progress for")
    mastery_level: float = Field(..., ge=0.0, le=1.0)
    completed: bool | None = None
    notes: str | None = None
