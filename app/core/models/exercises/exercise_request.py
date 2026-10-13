"""
Exercise Request Models (Tier 1 - External)
=============================================

Pydantic models for Exercise API validation at the boundary. An exercise is
authored only in the content vault (ADR-091 S4), so no request creates or edits
one: the one request is the learner's AI-report summons.

See: /docs/decisions/ADR-091-one-door-for-curriculum.md
"""

from pydantic import BaseModel, Field


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
