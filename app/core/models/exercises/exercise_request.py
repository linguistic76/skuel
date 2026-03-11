"""
Exercise Request Models (Tier 1 - External)
=============================================

Pydantic models for Exercise API validation and serialization.
Handles input validation at the API boundary.

Pipeline role: EXERCISE stage (Exercise → Submit → Analyze → Review)

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ExerciseCreateRequest(BaseModel):
    """Request to create a new Exercise (instruction template)."""

    user_uid: str = Field(..., description="User UID who owns this exercise")

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Display name for the exercise (e.g., 'Daily Reflection')",
    )

    instructions: str = Field(
        ..., min_length=1, description="Plain text instructions for LLM feedback generation"
    )

    model: str = Field(
        default="claude-sonnet-4-6",
        description="LLM model to use (e.g., 'claude-sonnet-4-6', 'gpt-4o-mini')",
    )

    context_notes: list[str] | None = Field(
        default=None, description="Optional reference materials or context notes"
    )

    domain: str | None = Field(default=None, description="Optional domain categorization")

    # Exercise fields (ADR-040)
    scope: str = Field(
        default="personal",
        description="Exercise scope: 'personal' (default) or 'assigned' (teacher exercise)",
    )

    due_date: date | None = Field(
        default=None,
        description="Due date for assigned exercises",
    )

    processor_type: str = Field(
        default="llm",
        description="Processor type: 'llm' (default), 'human', or 'hybrid'",
    )

    group_uid: str | None = Field(
        default=None,
        description="Target group UID (required for scope=assigned)",
    )

    form_schema: list[dict[str, Any]] | None = Field(
        default=None,
        description="Inline form definition: list of field specs with name, type, label",
    )

    @field_validator("form_schema")
    @classmethod
    def validate_form_schema(cls, v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Validate each form field spec has required keys and valid type."""
        if v is None:
            return None
        valid_types = {"text", "textarea", "select", "checkbox", "number", "date"}
        for i, field_spec in enumerate(v):
            if "name" not in field_spec:
                msg = f"form_schema[{i}] missing required key 'name'"
                raise ValueError(msg)
            if "type" not in field_spec:
                msg = f"form_schema[{i}] missing required key 'type'"
                raise ValueError(msg)
            if "label" not in field_spec:
                msg = f"form_schema[{i}] missing required key 'label'"
                raise ValueError(msg)
            if field_spec["type"] not in valid_types:
                msg = f"form_schema[{i}] invalid type '{field_spec['type']}', must be one of {valid_types}"
                raise ValueError(msg)
            if field_spec["type"] == "select" and "options" not in field_spec:
                msg = f"form_schema[{i}] type 'select' requires 'options' list"
                raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_exercise_fields(self) -> "ExerciseCreateRequest":
        """If scope=assigned, group_uid is required."""
        if self.scope == "assigned" and not self.group_uid:
            msg = "group_uid is required when scope is 'assigned'"
            raise ValueError(msg)
        return self


class ExerciseUpdateRequest(BaseModel):
    """Request to update an existing Exercise."""

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

    form_schema: list[dict[str, Any]] | None = Field(
        default=None,
        description="Inline form definition (replaces existing). Pass empty list to clear.",
    )

    @field_validator("form_schema")
    @classmethod
    def validate_form_schema(cls, v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Reuse same validation as create."""
        return ExerciseCreateRequest.validate_form_schema(v)


class FeedbackGenerateRequest(BaseModel):
    """Request to generate AI feedback for a submission using an Exercise.

    Always creates a SUBMISSION_REPORT entity (processor_type=LLM) in Neo4j.
    """

    entry_uid: str = Field(..., description="UID of the submission to analyze")

    project_uid: str = Field(..., description="UID of the Exercise with instructions")

    temperature: float | None = Field(
        default=0.7, ge=0.0, le=1.0, description="Sampling temperature for LLM (0-1)"
    )

    max_tokens: int | None = Field(
        default=4000, ge=100, le=8000, description="Maximum tokens to generate"
    )


class ExerciseKnowledgeRequest(BaseModel):
    """Request to link/unlink an exercise to a curriculum KU via REQUIRES_KNOWLEDGE."""

    exercise_uid: str = Field(..., description="Exercise UID")
    curriculum_uid: str = Field(..., description="Curriculum KU UID")
