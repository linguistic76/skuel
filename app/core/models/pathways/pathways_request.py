"""Pathways domain request models — Path Steps, Learning Paths.

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from pydantic import BaseModel, Field


class LearningPathFilterRequest(BaseModel):
    """Filter request for learning path browsing UI.

    Used by FormGenerator for filter form generation.
    """

    difficulty: str | None = Field(default=None, description="Filter by difficulty level")
    domain: str | None = Field(default=None, description="Filter by domain")
    duration: str | None = Field(default=None, description="Filter by time commitment")


class LearningPathProgressRequest(BaseModel):
    """Request model for updating learning progress on a step."""

    step_uid: str = Field(..., description="Step to update progress for")
    mastery_level: float = Field(..., ge=0.0, le=1.0)
    completed: bool | None = None
    notes: str | None = None
