"""
Insight Request Models (Pydantic)
==================================

Pydantic models for Insights API boundaries.

Note: SmartDismissRequest lives in entity_requests.py (cross-domain model).
"""

from pydantic import BaseModel, Field


class BulkInsightUidsRequest(BaseModel):
    """Request for bulk insight operations (dismiss, action)."""

    uids: list[str] = Field(..., min_length=1, description="List of insight UIDs")


class SnoozeInsightRequest(BaseModel):
    """Request to snooze an insight for a number of days."""

    days: int = Field(default=1, ge=1, le=30, description="Days to snooze (1-30)")
