"""
Analytics Report Request Models (Tier 1 - External)
====================================================

Pydantic models for analytics report API validation and serialization.
Handles input validation at the API boundary for analytics report generation.
"""

from pydantic import BaseModel, Field


class WeeklyPlanningRequest(BaseModel):
    """Request for weekly planning report."""

    user_uid: str = Field(..., description="User UID for report generation")

    week_start: str | None = Field(
        None, description="Week start date (YYYY-MM-DD). Defaults to current week if not provided."
    )


class WeeklyReviewRequest(BaseModel):
    """Request for weekly review report."""

    user_uid: str = Field(..., description="User UID for report generation")

    week_start: str | None = Field(
        None, description="Week start date (YYYY-MM-DD). Defaults to previous week if not provided."
    )


# Future report request models can be added here:
# - GoalProgressRequest
# - MonthlyReviewRequest
# - QuarterlyPlanningRequest
# etc.
