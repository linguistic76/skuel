"""
User Pins Request Models (Pydantic)
=====================================

Pydantic models for User Pins API boundaries.
"""

from pydantic import BaseModel, Field


class PinEntityRequest(BaseModel):
    """Request to pin an entity."""

    entity_uid: str = Field(..., min_length=1, description="UID of entity to pin")


class ReorderPinsRequest(BaseModel):
    """Request to reorder pinned entities."""

    ordered_entity_uids: list[str] = Field(
        ..., min_length=1, description="Entity UIDs in desired order"
    )
