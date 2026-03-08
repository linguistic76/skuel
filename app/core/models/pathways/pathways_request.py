"""Pathways domain request models — Learning Steps, Learning Paths.

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from pydantic import BaseModel, Field

from core.models.enums import (
    Confidence,
    Domain,
    Priority,
)
from core.models.enums.curriculum_enums import LpType, StepDifficulty
from core.models.request_base import CreateRequestBase


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
    confidence: Confidence | None = Field(
        None, description="Admin-assessed certainty about this learning step"
    )

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
    confidence: Confidence | None = Field(
        None, description="Admin-assessed certainty about this learning path"
    )


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
