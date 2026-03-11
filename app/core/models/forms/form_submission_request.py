"""
FormSubmission Request Models - API Validation (Tier 1 - External)
==================================================================

Pydantic models for FormSubmission API validation.
"""

from typing import Any

from pydantic import BaseModel, Field


class FormSubmissionCreateRequest(BaseModel):
    """Pydantic request model for submitting a form response."""

    form_template_uid: str = Field(..., description="UID of the FormTemplate being responded to")
    form_data: dict[str, Any] = Field(..., description="Form field values keyed by field name")
    title: str | None = Field(None, max_length=200, description="Optional title")
    # Sharing controls at submit time
    group_uid: str | None = Field(None, description="Share with this group on submit")
    recipient_uids: list[str] | None = Field(None, description="Share with these users on submit")
    share_with_admin: bool = Field(False, description="Send to admin on submit")


class FormSubmissionShareRequest(BaseModel):
    """Request to share an existing form submission."""

    uid: str = Field(..., description="FormSubmission UID to share")
    group_uid: str | None = Field(None, description="Share with this group")
    recipient_uids: list[str] | None = Field(None, description="Share with these users")
    share_with_admin: bool = Field(False, description="Share with admin")
