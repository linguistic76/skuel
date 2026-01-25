"""
Journal Project Request Models (Tier 1 - External)
===================================================

Pydantic models for journal project API validation and serialization.
Handles input validation at the API boundary.
"""

from pydantic import BaseModel, Field


class JournalProjectCreateRequest(BaseModel):
    """Request to create a new journal project."""

    user_uid: str = Field(..., description="User UID who owns this project")

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Display name for the project (e.g., 'Daily Reflection')",
    )

    instructions: str = Field(
        ..., min_length=1, description="Plain text instructions for LLM feedback generation"
    )

    model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="LLM model to use (e.g., 'claude-3-5-sonnet-20241022', 'gpt-4o-mini')",
    )

    context_notes: list[str] | None = Field(
        default=None, description="Optional reference materials or context notes"
    )

    domain: str | None = Field(default=None, description="Optional domain categorization")


class JournalProjectUpdateRequest(BaseModel):
    """Request to update an existing journal project."""

    name: str | None = Field(
        default=None, min_length=1, max_length=200, description="New display name"
    )

    instructions: str | None = Field(default=None, min_length=1, description="New instructions")

    model: str | None = Field(default=None, description="New model selection")

    context_notes: list[str] | None = Field(
        default=None, description="New context notes (replaces existing)"
    )

    domain: str | None = Field(default=None, description="New domain categorization")

    is_active: bool | None = Field(default=None, description="Active status")


class JournalFeedbackRequest(BaseModel):
    """Request to generate feedback for a journal entry using a project."""

    entry_uid: str = Field(..., description="UID of the journal entry to analyze")

    project_uid: str = Field(..., description="UID of the journal project with instructions")

    temperature: float | None = Field(
        default=0.7, ge=0.0, le=1.0, description="Sampling temperature for LLM (0-1)"
    )

    max_tokens: int | None = Field(
        default=4000, ge=100, le=8000, description="Maximum tokens to generate"
    )

    save_feedback: bool = Field(
        default=True, description="Whether to save feedback to the journal entry"
    )
