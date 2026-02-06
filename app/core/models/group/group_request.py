"""
Group Request Models (Tier 1 - External)
=========================================

Pydantic models for group API validation and serialization.
Handles input validation at the API boundary.
"""

from pydantic import BaseModel, Field


class GroupCreateRequest(BaseModel):
    """Request to create a new group."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Group display name (e.g., 'Physics 101 - Spring 2026')",
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional group description",
    )

    max_members: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Optional maximum number of members",
    )


class GroupUpdateRequest(BaseModel):
    """Request to update an existing group."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="New group name",
    )

    description: str | None = Field(
        default=None,
        max_length=2000,
        description="New description",
    )

    max_members: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="New member cap",
    )

    is_active: bool | None = Field(
        default=None,
        description="Active status",
    )


class GroupMemberRequest(BaseModel):
    """Request to add or remove a member from a group."""

    user_uid: str = Field(
        ...,
        description="UID of user to add/remove",
    )

    role: str = Field(
        default="student",
        description="Member role (e.g., 'student', 'ta')",
    )
