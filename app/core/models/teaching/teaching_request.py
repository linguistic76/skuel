"""Teaching domain request models.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

from pydantic import BaseModel, Field


class RequestRevisionRequest(BaseModel):
    """Request to ask a student to revise their work with structured feedback."""

    instructions: str = Field(..., min_length=1, description="Revision instructions")
    # Optional: absent/empty ⇒ report-only revision (e.g. reviewing an entry with
    # no exercise context). Present ⇒ atomic EntryReport + RevisedExercise.
    exercise_uid: str | None = Field(default=None, description="Original exercise UID")
    revision_rationale: str | None = Field(default=None, description="Why this revision")
    fp_count: int = Field(default=0, ge=0, le=20, description="Number of feedback points")
