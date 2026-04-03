"""Teaching domain request models.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from pydantic import BaseModel, Field


class RequestRevisionRequest(BaseModel):
    """Request to ask a student to revise their work."""

    notes: str = Field(..., min_length=1, description="Revision notes")
