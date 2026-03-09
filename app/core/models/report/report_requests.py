"""
SubmissionReport Domain Request Models
=======================================

Pydantic models for teacher/AI reports on student submissions.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from typing import Any

from pydantic import BaseModel, Field

from core.models.request_base import CreateRequestBase


class ReportCreateRequest(CreateRequestBase):
    """Create a submission report (SUBMISSION_REPORT type)."""

    title: str = Field(min_length=1, max_length=200, description="Report title")
    parent_entity_uid: str = Field(description="Assignment Ku being reviewed")
    subject_uid: str | None = Field(None, description="Student UID the report is about")

    # Content
    report_content: str = Field(min_length=1, description="Report text")
    content: str | None = Field(None, description="Additional content")


class AssessmentCreateRequest(BaseModel):
    """Request model for creating a teacher assessment (SUBMISSION_REPORT entity)."""

    subject_uid: str = Field(..., description="Student being assessed")
    title: str = Field(..., min_length=1, max_length=500, description="Assessment title")
    content: str = Field(..., min_length=1, description="Assessment content (markdown)")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")
