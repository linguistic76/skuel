"""
HabitTemplate Request Models — API Validation (Tier 1, External)
=================================================================

Pydantic models at the API boundary for HabitTemplate create/update endpoints.
HabitTemplate is Layer-0 in the spawn order — no cross-template references.
"""

from __future__ import annotations

from pydantic import Field

from core.models.enums import EntityStatus
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.enums.scheduling_enums import TimeOfDay
from core.models.request_base import UpdateRequestBase
from core.models.templates._template_request_base import TemplateCreateRequest
from core.models.templates.relative_offset_dto import RelativeOffsetDTO


class HabitTemplateCreateRequest(TemplateCreateRequest):
    """External API request for creating a HabitTemplate."""

    description: str | None = None
    tags: list[str] = Field(default_factory=list)

    polarity: HabitPolarity | None = None
    habit_category: HabitCategory | None = None
    habit_difficulty: HabitDifficulty | None = None

    cue: str | None = None
    routine: str | None = None
    reward: str | None = None

    reinforces_identity: str | None = None
    is_identity_habit: bool = False
    target_identity: str | None = None
    identity_evidence_required: int = Field(default=0, ge=0)

    duration_minutes: int | None = Field(default=None, ge=1)
    recurrence_pattern: str | None = None
    recurrence_end_offset: RelativeOffsetDTO | None = None
    target_days_per_week: int | None = Field(default=None, ge=1, le=7)
    preferred_time: TimeOfDay | None = None

    reminder_time: str | None = None
    reminder_days: list[str] = Field(default_factory=list)
    reminder_enabled: bool = False


class HabitTemplateUpdateRequest(UpdateRequestBase):
    """External API request for updating a HabitTemplate."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: EntityStatus | None = None
    tags: list[str] | None = None

    polarity: HabitPolarity | None = None
    habit_category: HabitCategory | None = None
    habit_difficulty: HabitDifficulty | None = None

    cue: str | None = None
    routine: str | None = None
    reward: str | None = None

    reinforces_identity: str | None = None
    is_identity_habit: bool | None = None
    target_identity: str | None = None
    identity_evidence_required: int | None = Field(default=None, ge=0)

    duration_minutes: int | None = Field(default=None, ge=1)
    recurrence_pattern: str | None = None
    recurrence_end_offset: RelativeOffsetDTO | None = None
    target_days_per_week: int | None = Field(default=None, ge=1, le=7)
    preferred_time: TimeOfDay | None = None

    reminder_time: str | None = None
    reminder_days: list[str] | None = None
    reminder_enabled: bool | None = None
