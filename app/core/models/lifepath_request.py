"""
LifePath Request Models (Pydantic)
===================================

Pydantic models for LifePath API boundaries.
"""

from pydantic import BaseModel, Field


class CaptureVisionRequest(BaseModel):
    """Request to capture a vision statement."""

    vision_statement: str = Field(
        ..., min_length=10, description="Vision statement (at least 10 characters)"
    )


class DesignateLifePathRequest(BaseModel):
    """Request to designate a learning path as life path."""

    life_path_uid: str = Field(..., min_length=1, description="Learning path UID to designate")
