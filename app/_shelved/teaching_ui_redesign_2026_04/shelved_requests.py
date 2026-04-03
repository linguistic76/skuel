"""Shelved teaching request models — removed 2026-04-03.

CreateTeachingExerciseRequest and UpdateTeachingExerciseRequest were removed
when exercise creation/editing was moved to ingestion-only workflow.
"""

from datetime import date

from pydantic import BaseModel, Field, model_validator

from core.models.enums.entity_enums import ProcessorType
from core.models.enums.submissions_enums import ExerciseScope


class CreateTeachingExerciseRequest(BaseModel):
    """Request to create an exercise owned by a teacher."""

    name: str = Field(..., min_length=1, description="Exercise name")
    instructions: str = Field(..., min_length=1, description="Exercise instructions")
    scope: ExerciseScope = ExerciseScope.PERSONAL
    group_uid: str | None = None
    due_date: date | None = None
    processor_type: ProcessorType = ProcessorType.LLM
    model: str = "claude-sonnet-4-6"
    context_notes: str | None = None

    @model_validator(mode="after")
    def assigned_scope_requires_group(self) -> "CreateTeachingExerciseRequest":
        if self.scope == ExerciseScope.ASSIGNED and not self.group_uid:
            msg = "group_uid is required for assigned exercises"
            raise ValueError(msg)
        return self

    @property
    def parsed_context_notes(self) -> list[str]:
        if not self.context_notes:
            return []
        return [n.strip() for n in self.context_notes.splitlines() if n.strip()]


class UpdateTeachingExerciseRequest(BaseModel):
    """Request to update an existing exercise (all fields optional)."""

    name: str | None = None
    instructions: str | None = None
    model: str | None = None
    context_notes: str | None = None

    @property
    def parsed_context_notes(self) -> list[str] | None:
        if self.context_notes is None:
            return None
        return [n.strip() for n in self.context_notes.splitlines() if n.strip()]
