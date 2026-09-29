"""
EventTemplate Request Models — API Validation (Tier 1, External)
=================================================================

Pydantic models at the API boundary for EventTemplate create/update endpoints.

``start_time`` / ``end_time`` are time-of-day (datetime.time); the date
component becomes engagement-relative via ``event_offset``.
"""

from __future__ import annotations

from datetime import (
    time,
)
from typing import Self

from pydantic import Field, model_validator

from core.models.enums import EntityStatus, EventType
from core.models.request_base import UpdateRequestBase
from core.models.templates._template_request_base import TemplateCreateRequest
from core.models.templates.relative_offset_dto import RelativeOffsetDTO
from core.models.validation_rules import validate_url_when_online


class EventTemplateCreateRequest(TemplateCreateRequest):
    """External API request for creating an EventTemplate."""

    description: str | None = None
    tags: list[str] = Field(default_factory=list)

    event_offset: RelativeOffsetDTO | None = None
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=1)

    event_type: EventType | None = None
    location: str | None = None
    is_online: bool = False
    meeting_url: str | None = None

    recurrence_pattern: str | None = None
    recurrence_end_offset: RelativeOffsetDTO | None = None

    reminder_minutes: int | None = Field(default=None, ge=0)
    max_attendees: int | None = Field(default=None, ge=1)

    reinforces_habit_template_uid: str | None = None
    milestone_celebration_for_goal_template_uid: str | None = None

    is_milestone_event: bool = False
    milestone_type: str | None = None
    curriculum_week: int | None = Field(default=None, ge=0)

    knowledge_retention_check: bool = False
    recurrence_maintains_habit: bool = False
    skip_breaks_habit_streak: bool = False

    @model_validator(mode="after")
    def _require_url_when_online(self) -> Self:
        """An online template needs a meeting URL: spawning copies both fields onto
        every learner's Event, so a URL-less online template multiplies the gap."""
        return validate_url_when_online("meeting_url", "is_online")(self)


class EventTemplateUpdateRequest(UpdateRequestBase):
    """External API request for updating an EventTemplate."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: EntityStatus | None = None
    tags: list[str] | None = None

    event_offset: RelativeOffsetDTO | None = None
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=1)

    event_type: EventType | None = None
    location: str | None = None
    is_online: bool | None = None
    meeting_url: str | None = None

    recurrence_pattern: str | None = None
    recurrence_end_offset: RelativeOffsetDTO | None = None

    reminder_minutes: int | None = Field(default=None, ge=0)
    max_attendees: int | None = Field(default=None, ge=1)

    reinforces_habit_template_uid: str | None = None
    milestone_celebration_for_goal_template_uid: str | None = None

    is_milestone_event: bool | None = None
    milestone_type: str | None = None
    curriculum_week: int | None = Field(default=None, ge=0)

    knowledge_retention_check: bool | None = None
    recurrence_maintains_habit: bool | None = None
    skip_breaks_habit_streak: bool | None = None
