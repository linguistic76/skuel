"""
Revised Exercise Request Models (Tier 1 - External)
=====================================================

Pydantic models for RevisedExercise API validation and serialization.
Handles input validation at the API boundary.

Part of the five-phase learning loop:
Exercise → Submission → SubmissionReport → RevisedExercise → Submission v2 → ...
"""

from pydantic import BaseModel, Field


class RevisedExerciseCreateRequest(BaseModel):
    """Request to create a new RevisedExercise (targeted revision instructions)."""

    original_exercise_uid: str = Field(
        ..., description="UID of the original Exercise being revised"
    )

    report_uid: str = Field(..., description="UID of the SubmissionReport this addresses")

    student_uid: str = Field(..., description="UID of the student this revision targets")

    instructions: str = Field(..., min_length=1, description="Plain text revision instructions")

    title: str | None = Field(
        default=None,
        max_length=200,
        description="Display title (auto-generated if not provided)",
    )

    model: str = Field(
        default="claude-sonnet-4-6",
        description="LLM model to use for feedback on revised submission",
    )

    context_notes: list[str] | None = Field(
        default=None, description="Optional reference materials"
    )

    feedback_points_addressed: list[str] | None = Field(
        default=None, description="Specific feedback points this revision targets"
    )

    revision_rationale: str | None = Field(
        default=None, description="Why this revision was created"
    )


class RevisedExerciseUpdateRequest(BaseModel):
    """Request to update an existing RevisedExercise."""

    instructions: str | None = Field(
        default=None, min_length=1, description="Updated revision instructions"
    )

    title: str | None = Field(default=None, max_length=200, description="Updated display title")

    model: str | None = Field(default=None, description="Updated model selection")

    context_notes: list[str] | None = Field(
        default=None, description="Updated context notes (replaces existing)"
    )

    feedback_points_addressed: list[str] | None = Field(
        default=None, description="Updated feedback points (replaces existing)"
    )

    revision_rationale: str | None = Field(default=None, description="Updated revision rationale")
