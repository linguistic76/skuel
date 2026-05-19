"""Pathways domain request models — Path Steps, Learning Paths.

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from pydantic import BaseModel, Field

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.enums import (
    Confidence,
    Domain,
    KuComplexity,
    LearningLevel,
    Priority,
    SELCategory,
)
from core.models.enums.curriculum_enums import LpType, StepDifficulty
from core.models.request_base import CreateRequestBase


class PathStepCreateRequest(CreateRequestBase):
    """Create a PATH_STEP entity (curriculum content unit). Admin-only, shared.

    PathStep is THE curriculum content entity — it directly composes KUs via
    USES_KU relationships.
    """

    title: str = Field(min_length=1, max_length=200, description="Step title")
    intent: str = Field(default="", description="Step intent/purpose")
    description: str | None = Field(None, max_length=2000, description="Step description")

    # Content
    content: str | None = Field(None, description="Body text / markdown content")
    summary: str | None = Field(None, max_length=500, description="Brief summary")

    # Curriculum placement
    learning_path_uid: str | None = Field(None, description="Parent LP UID")
    sequence: int | None = Field(None, ge=1, description="Order in learning path")

    # Learning parameters
    mastery_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Mastery threshold")
    estimated_hours: float = Field(default=1.0, gt=0, description="Estimated hours")
    difficulty: StepDifficulty = Field(
        default=StepDifficulty.MODERATE, description="Step difficulty"
    )
    complexity: KuComplexity = Field(default=KuComplexity.MEDIUM, description="Difficulty level")
    sel_category: SELCategory | None = Field(None, description="SEL category lens")
    learning_level: LearningLevel = Field(
        default=LearningLevel.BEGINNER, description="Target learning level"
    )
    estimated_time_minutes: int | None = Field(None, ge=1, description="Estimated completion time")
    difficulty_rating: float = Field(default=0.5, ge=0.0, le=1.0, description="Difficulty 0.0-1.0")
    learning_objectives: list[str] = Field(default_factory=list, description="Learning objectives")

    # Organization
    domain: Domain = Field(default=Domain.PERSONAL, description="Domain")
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority")
    notes: str | None = Field(None, description="Additional notes")
    tags: list[str] = Field(default_factory=list, description="Tags")
    confidence: Confidence | None = Field(
        None, description="Admin-assessed certainty about this path step"
    )

    # Knowledge relationships
    knowledge_uids: list[str] = Field(default_factory=list, description="KU UIDs")
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


class PathStepPathRequest(BaseModel):
    """Request to attach/detach a path step to/from a learning path."""

    path_uid: str = Field(..., description="Learning path UID")
    sequence: int | None = Field(None, ge=0, description="Position in path (for attach)")


# =============================================================================
# PATH STEP DOMAIN-SPECIFIC REQUEST MODELS
# =============================================================================


class StepRelationshipCreateRequest(BaseModel):
    """Request to create a semantic relationship between path steps."""

    target_uid: str = Field(..., description="Target path step UID")
    type: SemanticRelationshipType = Field(
        default=SemanticRelationshipType.RELATED_TO, description="Relationship type"
    )
    strength: float = Field(default=1.0, ge=0.0, le=1.0, description="Relationship strength")
    description: str = Field(default="", max_length=500, description="Relationship description")


class StepContentUpdateRequest(BaseModel):
    """Request to update path step content body."""

    content: str = Field(..., min_length=1, description="Path step content")
    title: str | None = Field(
        None, min_length=1, max_length=200, description="Optional title update"
    )


class StepOrganizeRequest(BaseModel):
    """Request to organize a path step under another (create ORGANIZES relationship)."""

    parent_uid: str = Field(..., description="Parent path step UID")
    child_uid: str = Field(..., description="Child path step UID")
    order: int = Field(default=0, ge=0, description="Sort order within parent")


class StepReorderRequest(BaseModel):
    """Request to change the order of a child path step within its parent."""

    parent_uid: str = Field(..., description="Parent path step UID")
    child_uid: str = Field(..., description="Child path step UID")
    new_order: int = Field(..., ge=0, description="New sort order")
