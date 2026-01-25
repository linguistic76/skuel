"""
Learning Request Models (Tier 1 - API Boundary)
===============================================

Pydantic models for API validation and serialization.

Uses shared validators from validation_rules.py for DRY compliance.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.models.shared_enums import Domain
from core.models.validation_rules import validate_required_string


class LearningStepCreateRequest(BaseModel):
    """Request model for creating a learning step."""

    knowledge_uid: str = Field(..., description="Reference to Knowledge model")
    sequence: int = Field(..., ge=0, description="Order in the path")
    mastery_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    estimated_hours: float = Field(default=1.0, gt=0.0)
    notes: str | None = None
    prerequisites: list[str] = Field(default_factory=list)

    # Shared validators
    _validate_knowledge_uid = validate_required_string("knowledge_uid")


class LearningStepUpdateRequest(BaseModel):
    """Request model for updating a learning step."""

    sequence: int | None = Field(None, ge=0)
    mastery_threshold: float | None = Field(None, ge=0.0, le=1.0)
    estimated_hours: float | None = Field(None, gt=0.0)
    current_mastery: float | None = Field(None, ge=0.0, le=1.0)
    completed: bool | None = None
    completed_at: datetime | None = None
    notes: str | None = None
    prerequisites: list[str] | None = None


class LpCreateRequest(BaseModel):
    """Request model for creating a learning path."""

    name: str = Field(..., min_length=1, max_length=200)
    goal: str = Field(..., min_length=1, description="What the learner will achieve")
    domain: Domain
    path_type: str = Field(default="structured")
    difficulty: str = Field(default="intermediate")
    prerequisites: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    estimated_hours: float | None = Field(None, gt=0.0)
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        # Pydantic V2 serializes enums automatically
    )

    # Shared validators
    _validate_required_strings = validate_required_string("name", "goal")

    @field_validator("path_type")
    @classmethod
    def validate_path_type(cls, v: str) -> str:
        valid_types = ["structured", "adaptive", "exploratory", "remedial", "accelerated"]
        if v.lower() not in valid_types:
            raise ValueError(f"Path type must be one of: {', '.join(valid_types)}")
        return v.lower()

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        valid_levels = ["beginner", "intermediate", "advanced", "expert"]
        if v.lower() not in valid_levels:
            raise ValueError(f"Difficulty must be one of: {', '.join(valid_levels)}")
        return v.lower()


class LpUpdateRequest(BaseModel):
    """Request model for updating a learning path."""

    name: str | None = Field(None, min_length=1, max_length=200)
    goal: str | None = Field(None, min_length=1)
    domain: Domain | None = None
    path_type: str | None = None
    difficulty: str | None = None
    prerequisites: list[str] | None = None
    outcomes: list[str] | None = None  # type: ignore[assignment]
    estimated_hours: float | None = Field(None, gt=0.0)
    tags: list[str] | None = None

    model_config = ConfigDict(
        # Pydantic V2 serializes enums automatically
    )

    @field_validator("path_type")
    @classmethod
    def validate_path_type(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid_types = ["structured", "adaptive", "exploratory", "remedial", "accelerated"]
        if v.lower() not in valid_types:
            raise ValueError(f"Path type must be one of: {', '.join(valid_types)}")
        return v.lower()

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str | None) -> str | None:
        if v is None:
            return None
        valid_levels = ["beginner", "intermediate", "advanced", "expert"]
        if v.lower() not in valid_levels:
            raise ValueError(f"Difficulty must be one of: {', '.join(valid_levels)}")
        return v.lower()


class LpProgressRequest(BaseModel):
    """Request model for updating learning progress."""

    step_uid: str = Field(..., description="Step to update progress for")
    mastery_level: float = Field(..., ge=0.0, le=1.0)
    completed: bool | None = None
    notes: str | None = None


class LpFilterRequest(BaseModel):
    """Request model for filtering learning paths."""

    difficulty: str | None = Field(None, description="Filter by difficulty level")
    domain: str | None = Field(None, description="Filter by domain")
    duration: str | None = Field(None, description="Filter by time commitment")

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty_filter(cls, v: str | None) -> str | None:
        if v is None or v == "all":
            return None
        valid_levels = ["beginner", "intermediate", "advanced", "expert"]
        if v.lower() not in valid_levels:
            raise ValueError(f"Difficulty must be one of: {', '.join(valid_levels)} or 'all'")
        return v.lower()

    @field_validator("domain")
    @classmethod
    def validate_domain_filter(cls, v: str | None) -> str | None:
        if v is None or v == "all":
            return None
        valid_domains = ["programming", "data_science", "web_dev", "cloud", "machine_learning"]
        if v.lower() not in valid_domains:
            raise ValueError(f"Domain must be one of: {', '.join(valid_domains)} or 'all'")
        return v.lower()

    @field_validator("duration")
    @classmethod
    def validate_duration_filter(cls, v: str | None) -> str | None:
        if v is None or v == "all":
            return None
        valid_durations = ["short", "medium", "long"]
        if v.lower() not in valid_durations:
            raise ValueError(f"Duration must be one of: {', '.join(valid_durations)} or 'all'")
        return v.lower()


class LpResponse(BaseModel):
    """Response model for learning path with progress."""

    uid: str
    name: str
    goal: str
    domain: Domain
    path_type: str
    difficulty: str
    steps_count: int
    completed_steps: int
    overall_progress: float
    overall_mastery: float
    estimated_hours: float
    remaining_hours: float
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        # Pydantic V2 serializes enums and datetimes automatically
    )
