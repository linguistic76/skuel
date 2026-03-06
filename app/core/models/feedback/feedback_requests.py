"""
SubmissionFeedback Domain Request Models
================================

Pydantic models for teacher/AI feedback on student submissions.

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from typing import Any

from pydantic import BaseModel, Field

from core.models.request_base import CreateRequestBase


class FeedbackCreateRequest(CreateRequestBase):
    """Create teacher feedback on an assignment (FEEDBACK_REPORT type)."""

    title: str = Field(min_length=1, max_length=200, description="Feedback title")
    parent_entity_uid: str = Field(description="Assignment Ku being reviewed")
    subject_uid: str | None = Field(None, description="Student UID the feedback is about")

    # Content
    feedback: str = Field(min_length=1, description="Feedback text")
    content: str | None = Field(None, description="Additional content")


class AssessmentCreateRequest(BaseModel):
    """Request model for creating a teacher assessment (SUBMISSION_FEEDBACK entity)."""

    subject_uid: str = Field(..., description="Student being assessed")
    title: str = Field(..., min_length=1, max_length=500, description="Assessment title")
    content: str = Field(..., min_length=1, description="Assessment content (markdown)")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")
