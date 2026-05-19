"""
TaskTemplate Request Models — API Validation (Tier 1, External)
================================================================

Pydantic models at the API boundary for TaskTemplate create/update endpoints.

Engagement-relative timing is exposed via :class:`RelativeOffsetDTO` (Pydantic
mirror of :class:`RelativeOffset`), converted to the immutable core type by
``ConversionServiceV2.tasktemplate_create_to_pure``.

Phase 5 — API + persistence only. Nested authoring fields that require
FormGenerator nested-dataclass support (none on TaskTemplate today) are out
of scope; UI work tracks them separately.
"""

from __future__ import annotations

from pydantic import Field

from core.models.enums import EntityStatus, RecurrencePattern
from core.models.request_base import UpdateRequestBase
from core.models.templates._template_request_base import TemplateCreateRequest
from core.models.templates.relative_offset_dto import RelativeOffsetDTO


class TaskTemplateCreateRequest(TemplateCreateRequest):
    """External API request for creating a TaskTemplate."""

    description: str | None = Field(default=None, description="Detailed description")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")

    # Scheduling (engagement-relative)
    due_offset: RelativeOffsetDTO | None = Field(
        default=None, description="Days/hours/minutes from engagement until due"
    )
    scheduled_offset: RelativeOffsetDTO | None = Field(
        default=None, description="Days/hours/minutes from engagement until scheduled"
    )
    duration_minutes: int | None = Field(default=None, ge=1, description="Estimated duration")

    # Recurrence
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_offset: RelativeOffsetDTO | None = None

    # Hierarchy / project context
    parent_template_uid: str | None = Field(default=None, description="Parent task template UID")
    project: str | None = Field(default=None, description="Associated project")

    # Cross-template references (resolved at spawn)
    fulfills_goal_template_uid: str | None = None
    reinforces_habit_template_uid: str | None = None
    scheduled_event_template_uid: str | None = None

    # Progress impact (copied to spawned Task)
    goal_progress_contribution: float = Field(default=0.0, ge=0.0, le=1.0)
    knowledge_mastery_check: bool = False
    habit_streak_maintainer: bool = False
    completion_updates_goal: bool = False


class TaskTemplateUpdateRequest(UpdateRequestBase):
    """External API request for updating a TaskTemplate."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: EntityStatus | None = None
    tags: list[str] | None = None

    due_offset: RelativeOffsetDTO | None = None
    scheduled_offset: RelativeOffsetDTO | None = None
    duration_minutes: int | None = Field(default=None, ge=1)

    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_offset: RelativeOffsetDTO | None = None

    parent_template_uid: str | None = None
    project: str | None = None

    fulfills_goal_template_uid: str | None = None
    reinforces_habit_template_uid: str | None = None
    scheduled_event_template_uid: str | None = None

    goal_progress_contribution: float | None = Field(default=None, ge=0.0, le=1.0)
    knowledge_mastery_check: bool | None = None
    habit_streak_maintainer: bool | None = None
    completion_updates_goal: bool | None = None
