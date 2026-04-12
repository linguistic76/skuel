"""
ExerciseReport Domain Request Models
=======================================

Pydantic models for teacher/AI reports on student submissions.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from typing import Any

from pydantic import BaseModel, Field


class AssessmentCreateRequest(BaseModel):
    """Request model for creating a teacher assessment (ExerciseReport entity)."""

    subject_uid: str = Field(..., description="Student being assessed")
    title: str = Field(..., min_length=1, max_length=500, description="Assessment title")
    content: str = Field(..., min_length=1, description="Assessment content (markdown)")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")
