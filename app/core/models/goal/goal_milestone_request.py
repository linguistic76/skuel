"""
Milestone Request Models (Tier 1 - External)
=============================================

Pydantic models for external API requests related to standalone milestones.
Handles validation and serialization at system boundaries.

Note: This is for standalone milestone management. For milestones within goals,
see goal_request.py which contains MilestoneCreateRequest for goal-embedded milestones.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class StandaloneMilestoneCreateRequest(BaseModel):
    """
    External request for creating a standalone milestone.
    Validates input from API/UI layer.
    """

    # Required fields
    goal_uid: str = Field(
        ..., min_length=1, description="UID of the goal this milestone belongs to"
    )
    title: str = Field(..., min_length=1, max_length=200, description="Milestone title")

    # Optional with defaults
    description: str | None = Field(None, max_length=1000, description="Detailed description")
    target_date: date | None = Field(None, description="Target completion date")
    order: int = Field(0, ge=0, description="Display order (0-based)")

    @field_validator("target_date")
    @classmethod
    def validate_target_date(cls, v) -> Any:
        """Ensure target date is not in the past (if provided)."""
        if v is not None and v < date.today():
            raise ValueError("Target date cannot be in the past")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "goal_uid": "goal_learn_python",
                "title": "Complete Python Basics Course",
                "description": "Finish all modules of the Python fundamentals course",
                "target_date": "2025-12-31",
                "order": 1,
            }
        }
    )


class StandaloneMilestoneUpdateRequest(BaseModel):
    """
    External request for updating a standalone milestone.
    """

    title: str | None = Field(None, min_length=1, max_length=200, description="Updated title")
    description: str | None = Field(None, max_length=1000, description="Updated description")
    target_date: date | None = Field(None, description="Updated target date")
    order: int | None = Field(None, ge=0, description="Updated display order")

    @field_validator("target_date")
    @classmethod
    def validate_target_date(cls, v) -> Any:
        """Ensure target date is not in the past (if provided)."""
        if v is not None and v < date.today():
            raise ValueError("Target date cannot be in the past")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Complete Advanced Python Course",
                "description": "Updated to include advanced topics",
                "target_date": "2026-06-30",
                "order": 2,
            }
        }
    )


class StandaloneMilestoneCompleteRequest(BaseModel):
    """
    Request to mark a standalone milestone as completed.
    """

    completed_date: datetime | None = Field(
        default_factory=datetime.now, description="Completion timestamp"
    )
    notes: str | None = Field(None, max_length=500, description="Completion notes")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"notes": "Completed ahead of schedule with excellent understanding"}
        }
    )


class StandaloneMilestoneFilterRequest(BaseModel):
    """
    Request for filtering standalone milestones.
    """

    goal_uid: str | None = Field(None, description="Filter by specific goal")
    is_completed: bool | None = Field(None, description="Filter by completion status")
    overdue_only: bool = Field(False, description="Show only overdue milestones")
    target_date_start: date | None = Field(None, description="Filter from this target date")
    target_date_end: date | None = Field(None, description="Filter to this target date")
    limit: int = Field(50, ge=1, le=1000, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")

    @field_validator("target_date_end")
    @classmethod
    def validate_date_range(cls, v, info: ValidationInfo) -> Any:
        """Ensure end date is after start date."""
        if (
            v is not None
            and info.data.get("target_date_start") is not None
            and v < info.data["target_date_start"]
        ):
            raise ValueError("End date must be after start date")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "goal_uid": "goal_learn_python",
                "is_completed": False,
                "overdue_only": True,
                "limit": 20,
            }
        }
    )
