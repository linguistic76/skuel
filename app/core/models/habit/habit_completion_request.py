"""
Habit Completion Request Models (Tier 1 - External)
====================================================

Pydantic models for external API requests related to habit completions.
Handles validation and serialization at system boundaries.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HabitCompletionCreateRequest(BaseModel):
    """
    External request for recording a habit completion.
    Validates input from API/UI layer.
    """

    # Required field
    habit_uid: str = Field(..., min_length=1, description="UID of the habit being completed")

    # Optional with defaults
    completed_at: datetime | None = Field(
        default_factory=datetime.now, description="When the habit was completed"
    )
    notes: str | None = Field(None, max_length=500, description="Completion notes")
    quality: int | None = Field(None, ge=1, le=5, description="Quality rating 1-5")
    duration_actual: int | None = Field(None, ge=0, description="Actual duration in minutes")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "habit_uid": "habit_001",
                "notes": "Felt great today, extended session",
                "quality": 5,
                "duration_actual": 30,
            }
        }
    )


class HabitCompletionUpdateRequest(BaseModel):
    """
    External request for updating a habit completion.
    """

    notes: str | None = Field(None, max_length=500, description="Updated completion notes")
    quality: int | None = Field(None, ge=1, le=5, description="Updated quality rating 1-5")
    duration_actual: int | None = Field(
        None, ge=0, description="Updated actual duration in minutes"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "notes": "Updated reflection on the session",
                "quality": 4,
                "duration_actual": 25,
            }
        }
    )


class HabitCompletionFilterRequest(BaseModel):
    """
    Request for filtering habit completions.
    """

    habit_uid: str | None = Field(None, description="Filter by specific habit")
    start_date: datetime | None = Field(None, description="Filter from this date")
    end_date: datetime | None = Field(None, description="Filter to this date")
    min_quality: int | None = Field(None, ge=1, le=5, description="Minimum quality rating")
    max_quality: int | None = Field(None, ge=1, le=5, description="Maximum quality rating")
    limit: int = Field(50, ge=1, le=1000, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "habit_uid": "habit_001",
                "start_date": "2025-09-01T00:00:00Z",
                "end_date": "2025-09-30T23:59:59Z",
                "min_quality": 3,
                "limit": 20,
            }
        }
    )
