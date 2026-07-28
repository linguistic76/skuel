"""
Exercise Request Models (Tier 1 - External)
=============================================

Pydantic models for Exercise API validation and serialization.
Handles input validation at the API boundary.

Pipeline role: EXERCISE stage (Exercise → Submit → Analyze → Review)

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from core.models.enums.entity_enums import Domain
from core.models.enums.learning_enums import MasteryImpact
from core.models.enums.user_entry_enums import ExerciseScope


def _validate_domain_value(value: str | None) -> str | None:
    """Reject domain strings that are not Domain enum values (422 at the boundary,
    not a 500 in conversion — conversion does ``Domain(schema.domain)``)."""
    if value is None:
        return None
    try:
        Domain(value)
    except ValueError:
        valid = ", ".join(member.value for member in Domain)
        msg = f"invalid domain '{value}'. Valid values: {valid}"
        raise ValueError(msg) from None
    return value


class ExerciseCreateRequest(BaseModel):
    """Request to create a new Exercise (instruction template).

    Carries no user_uid: ownership comes from the authenticated session —
    CRUDRouteFactory passes it to exercise_create_to_pure, which maps it to
    Exercise.owner_uid. A client-supplied owner would be untrusted anyway.
    """

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

    path_step_uid: str | None = Field(
        default=None,
        description="Optional PathStep anchor (mirrors HAS_EXERCISE edge when set)",
    )

    # Exercise fields (ADR-040)
    scope: ExerciseScope = Field(
        default=ExerciseScope.PERSONAL,
        description=(
            "Exercise scope: 'personal' (default), 'assigned' (teacher exercise), or "
            "'assessment'. 'curriculum' is vault-ingested only — rejected here."
        ),
    )

    due_date: date | None = Field(
        default=None,
        description="Due date for assigned exercises",
    )

    group_uid: str | None = Field(
        default=None,
        description="Target group UID (required for scope=assigned)",
    )

    form_schema: list[dict[str, Any]] | None = Field(
        default=None,
        description="Inline form definition: list of field specs with name, type, label",
    )

    mastery_impact: MasteryImpact | None = Field(
        default=None,
        description="How aggressively completing this exercise advances mastery (minor, moderate, major, certification)",
    )

    scoring_rubric: list[dict[str, Any]] | None = Field(
        default=None,
        description="Assessment rubric: list of criteria with name, weight, and description",
    )

    pass_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum score (0.0-1.0) to pass an assessment",
    )

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str | None) -> str | None:
        """Validate domain against the Domain enum."""
        return _validate_domain_value(v)

    @field_validator("scoring_rubric")
    @classmethod
    def validate_scoring_rubric(cls, v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Validate each rubric criterion has required keys and valid weight."""
        if v is None:
            return None
        if not v:
            msg = "scoring_rubric must contain at least one criterion"
            raise ValueError(msg)
        total_weight = 0.0
        for i, criterion in enumerate(v):
            if "name" not in criterion:
                msg = f"scoring_rubric[{i}] missing required key 'name'"
                raise ValueError(msg)
            if "weight" not in criterion:
                msg = f"scoring_rubric[{i}] missing required key 'weight'"
                raise ValueError(msg)
            weight = criterion["weight"]
            if not isinstance(weight, int | float) or weight <= 0:
                msg = f"scoring_rubric[{i}] weight must be a positive number"
                raise ValueError(msg)
            total_weight += weight
        if abs(total_weight - 1.0) > 0.01:
            msg = f"scoring_rubric weights must sum to 1.0, got {total_weight:.2f}"
            raise ValueError(msg)
        return v

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
        """Validate scope-specific requirements."""
        if self.scope == ExerciseScope.CURRICULUM:
            msg = (
                "scope 'curriculum' exercises are authored in the content vault "
                "and ingested, not created via the API"
            )
            raise ValueError(msg)
        if self.scope == ExerciseScope.ASSIGNED and not self.group_uid:
            msg = "group_uid is required when scope is 'assigned'"
            raise ValueError(msg)
        if self.scope == ExerciseScope.ASSESSMENT and not self.scoring_rubric:
            msg = "scoring_rubric is required when scope is 'assessment'"
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

    mastery_impact: MasteryImpact | None = Field(
        default=None,
        description="How aggressively completing this exercise advances mastery",
    )

    scoring_rubric: list[dict[str, Any]] | None = Field(
        default=None,
        description="Assessment rubric (replaces existing). Pass empty list to clear.",
    )

    pass_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum score (0.0-1.0) to pass an assessment",
    )

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str | None) -> str | None:
        """Validate domain against the Domain enum."""
        return _validate_domain_value(v)

    @field_validator("scoring_rubric")
    @classmethod
    def validate_scoring_rubric(cls, v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Reuse same validation as create."""
        return ExerciseCreateRequest.validate_scoring_rubric(v)

    @field_validator("form_schema")
    @classmethod
    def validate_form_schema(cls, v: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Reuse same validation as create."""
        return ExerciseCreateRequest.validate_form_schema(v)


class ReportGenerateRequest(BaseModel):
    """Request to generate AI report for a submission using an Exercise.

    Always creates an EntryReport entity (processor_type=LLM) in Neo4j.
    """

    submission_uid: str = Field(..., description="UID of the submission to analyze")

    exercise_uid: str = Field(..., description="UID of the Exercise with instructions")

    temperature: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Sampling temperature for LLM (0-1)"
    )

    max_tokens: int = Field(default=4000, ge=100, le=8000, description="Maximum tokens to generate")


class ExerciseKnowledgeRequest(BaseModel):
    """Request to link/unlink an exercise to a curriculum KU via REQUIRES_KNOWLEDGE."""

    exercise_uid: str = Field(..., description="Exercise UID")
    curriculum_uid: str = Field(..., description="Curriculum KU UID")
