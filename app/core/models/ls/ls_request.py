"""
LearningStep Request Models (Tier 1 - External)
===============================================

Pydantic models for API validation and serialization.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from core.models.enums import Domain, Priority

from .ls import StepDifficulty, StepStatus


class LearningStepCreateRequest(BaseModel):
    """
    Request model for creating a learning step.

    Validates incoming API data before conversion to DTO.
    """

    # Required fields
    title: str = Field(..., min_length=1, max_length=200, description="Step title")
    intent: str = Field(..., min_length=1, description="Learning objective")

    # Optional identity
    uid: str | None = Field(None, description="Custom UID (auto-generated if not provided)")
    description: str | None = Field(None, description="Detailed description")

    # Knowledge Content
    primary_knowledge_uids: list[str] = Field(
        default_factory=list, description="Main knowledge units"
    )
    supporting_knowledge_uids: list[str] = Field(
        default_factory=list, description="Supporting knowledge"
    )

    # Path Integration
    learning_path_uid: str | None = Field(None, description="Parent learning path UID")
    sequence: int | None = Field(None, ge=1, description="Order in learning path")

    # Prerequisites & Dependencies
    prerequisite_step_uids: list[str] = Field(
        default_factory=list, description="Required prerequisite steps"
    )
    prerequisite_knowledge_uids: list[str] = Field(
        default_factory=list, description="Assumed prerequisite knowledge"
    )

    # Learning Guidance
    principle_uids: list[str] = Field(default_factory=list, description="Guiding principles")
    choice_uids: list[str] = Field(default_factory=list, description="Choices/decisions offered")

    # Practice Integration
    habit_uids: list[str] = Field(default_factory=list, description="Habits to build")
    task_uids: list[str] = Field(default_factory=list, description="Tasks to complete")
    event_template_uids: list[str] = Field(default_factory=list, description="Calendar templates")

    # Mastery & Progress
    mastery_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Required mastery level"
    )
    estimated_hours: float = Field(default=1.0, gt=0, description="Estimated time to complete")
    difficulty: StepDifficulty = Field(
        default=StepDifficulty.MODERATE, description="Difficulty level"
    )

    # Domain & Priority
    domain: Domain = Field(default=Domain.PERSONAL, description="Domain classification")
    priority: Priority = Field(default=Priority.MEDIUM, description="Priority level")

    # Metadata
    notes: str | None = Field(None, description="Additional notes")
    tags: list[str] = Field(default_factory=list, description="Tags for organization")

    model_config = ConfigDict(use_enum_values=True)


class LearningStepUpdateRequest(BaseModel):
    """
    Request model for updating a learning step.

    All fields are optional for partial updates.
    """

    title: str | None = Field(None, min_length=1, max_length=200)
    intent: str | None = Field(None, min_length=1)
    description: str | None = None

    # Knowledge Content
    primary_knowledge_uids: list[str] | None = None
    supporting_knowledge_uids: list[str] | None = None

    # Path Integration
    learning_path_uid: str | None = None
    sequence: int | None = Field(None, ge=1)

    # Prerequisites & Dependencies
    prerequisite_step_uids: list[str] | None = None
    prerequisite_knowledge_uids: list[str] | None = None

    # Learning Guidance
    principle_uids: list[str] | None = None
    choice_uids: list[str] | None = None

    # Practice Integration
    habit_uids: list[str] | None = None
    task_uids: list[str] | None = None
    event_template_uids: list[str] | None = None

    # Mastery & Progress
    mastery_threshold: float | None = Field(None, ge=0.0, le=1.0)
    current_mastery: float | None = Field(None, ge=0.0, le=1.0)
    estimated_hours: float | None = Field(None, gt=0)
    difficulty: StepDifficulty | None = None

    # Status
    status: StepStatus | None = None
    completed: bool | None = None

    # Domain & Priority
    domain: Domain | None = None
    priority: Priority | None = None

    # Metadata
    notes: str | None = None
    tags: list[str] | None = None

    model_config = ConfigDict(use_enum_values=True)


class LearningStepResponse(BaseModel):
    """
    Response model for learning step data.

    Used for API responses.
    """

    # Identity
    uid: str
    title: str
    intent: str
    description: str | None = None

    # Knowledge Content
    primary_knowledge_uids: list[str]
    supporting_knowledge_uids: list[str]

    # Path Integration
    learning_path_uid: str | None = None
    sequence: int | None = None

    # Prerequisites & Dependencies
    prerequisite_step_uids: list[str]
    prerequisite_knowledge_uids: list[str]

    # Learning Guidance
    principle_uids: list[str]
    choice_uids: list[str]

    # Practice Integration
    habit_uids: list[str]
    task_uids: list[str]
    event_template_uids: list[str]

    # Mastery & Progress
    mastery_threshold: float
    current_mastery: float
    estimated_hours: float
    difficulty: StepDifficulty

    # Status
    status: StepStatus
    completed: bool
    completed_at: datetime | None = None

    # Domain & Priority
    domain: Domain
    priority: Priority

    # Metadata
    created_at: datetime
    updated_at: datetime
    notes: str | None = None
    tags: list[str]

    # Computed fields
    progress_percentage: float
    is_ready: bool
    is_mastered: bool

    model_config = ConfigDict(use_enum_values=True, from_attributes=True)
