"""
Report Project Request Models (Tier 1 - External)
===================================================

Pydantic models for report project API validation and serialization.
Handles input validation at the API boundary.
"""

from datetime import date

from pydantic import BaseModel, Field, model_validator


class ReportProjectCreateRequest(BaseModel):
    """Request to create a new report project."""

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

    # Assignment fields (ADR-040)
    scope: str = Field(
        default="personal",
        description="Project scope: 'personal' (default) or 'assigned' (teacher assignment)",
    )

    due_date: date | None = Field(
        default=None,
        description="Due date for assigned projects",
    )

    processor_type: str = Field(
        default="llm",
        description="Processor type: 'llm' (default), 'human', or 'hybrid'",
    )

    group_uid: str | None = Field(
        default=None,
        description="Target group UID (required for scope=assigned)",
    )

    @model_validator(mode="after")
    def validate_assignment_fields(self) -> "ReportProjectCreateRequest":
        """If scope=assigned, group_uid is required."""
        if self.scope == "assigned" and not self.group_uid:
            msg = "group_uid is required when scope is 'assigned'"
            raise ValueError(msg)
        return self


class ReportProjectUpdateRequest(BaseModel):
    """Request to update an existing report project."""

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


class ReportFeedbackRequest(BaseModel):
    """Request to generate feedback for a report entry using a project."""

    entry_uid: str = Field(..., description="UID of the report entry to analyze")

    project_uid: str = Field(..., description="UID of the report project with instructions")

    temperature: float | None = Field(
        default=0.7, ge=0.0, le=1.0, description="Sampling temperature for LLM (0-1)"
    )

    max_tokens: int | None = Field(
        default=4000, ge=100, le=8000, description="Maximum tokens to generate"
    )

    save_feedback: bool = Field(
        default=True, description="Whether to save feedback to the report entry"
    )
