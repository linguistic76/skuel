"""
GoalTemplate Request Models — API Validation (Tier 1, External)
================================================================

Pydantic models at the API boundary for GoalTemplate create/update endpoints.

Phase 5 — V1 of authoring API. ``milestones`` (tuple[Milestone, ...] on the
core model) require FormGenerator nested-dataclass support; the schema accepts
them as ``list[dict]`` for forward-compat, and the converter coerces values
into ``Milestone`` instances when shape matches. Empty list/None is the
default and works fine for plain-text goals.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from core.models.enums import EntityStatus
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.request_base import CreateRequestBase, UpdateRequestBase
from core.models.templates.relative_offset_dto import RelativeOffsetDTO


class GoalTemplateCreateRequest(CreateRequestBase):
    """External API request for creating a GoalTemplate."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)

    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    measurement_type: MeasurementType | None = None

    target_value: float | None = None
    unit_of_measurement: str | None = None

    start_offset: RelativeOffsetDTO | None = None
    target_offset: RelativeOffsetDTO | None = None

    milestones: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Authored milestone structure (cloned to instance)",
    )

    vision_statement: str | None = None
    why_important: str | None = None
    success_criteria: str | None = None
    potential_obstacles: list[str] = Field(default_factory=list)
    strategies: list[str] = Field(default_factory=list)

    fulfills_goal_template_uid: str | None = None
    inspired_by_choice_template_uid: str | None = None
    selected_choice_option_template_uid: str | None = None

    target_identity: str | None = None
    identity_evidence_required: int = Field(0, ge=0)


class GoalTemplateUpdateRequest(UpdateRequestBase):
    """External API request for updating a GoalTemplate."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: EntityStatus | None = None
    tags: list[str] | None = None

    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    measurement_type: MeasurementType | None = None

    target_value: float | None = None
    unit_of_measurement: str | None = None

    start_offset: RelativeOffsetDTO | None = None
    target_offset: RelativeOffsetDTO | None = None

    milestones: list[dict[str, Any]] | None = None

    vision_statement: str | None = None
    why_important: str | None = None
    success_criteria: str | None = None
    potential_obstacles: list[str] | None = None
    strategies: list[str] | None = None

    fulfills_goal_template_uid: str | None = None
    inspired_by_choice_template_uid: str | None = None
    selected_choice_option_template_uid: str | None = None

    target_identity: str | None = None
    identity_evidence_required: int | None = Field(None, ge=0)
