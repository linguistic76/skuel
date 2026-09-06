"""GoalTemplateDTO — Transfer tier for GoalTemplate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enum_field_registry import enum_fields_for
from core.models.enums.entity_enums import EntityType
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.templates.offset_helpers import (
    TEMPLATE_OFFSET_FIELDS,
    jsonable_to_offset,
    offset_to_jsonable,
)
from core.models.templates.relative_offset import RelativeOffset

_OFFSET_FIELDS: tuple[str, ...] = TEMPLATE_OFFSET_FIELDS[EntityType.GOAL_TEMPLATE]


@dataclass
class GoalTemplateDTO(EntityDTO):
    """Mutable DTO for GoalTemplate entities."""

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.GOAL_TEMPLATE, kw_only=True)

    # Classification
    goal_type: GoalType | None = None
    timeframe: GoalTimeframe | None = None
    measurement_type: MeasurementType | None = None

    # Measurement
    target_value: float | None = None
    unit_of_measurement: str | None = None

    # Timeline (engagement-relative)
    start_offset: RelativeOffset | None = None
    target_offset: RelativeOffset | None = None

    # Authored milestones — same shape as Goal.milestones (list of dicts at DTO layer)
    milestones: list[dict[str, Any]] = field(default_factory=list)

    # Motivation
    vision_statement: str | None = None
    why_important: str | None = None
    success_criteria: str | None = None
    potential_obstacles: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)

    # Cross-template refs
    fulfills_goal_template_uid: str | None = None
    inspired_by_choice_template_uid: str | None = None
    selected_choice_option_template_uid: str | None = None

    # Identity
    target_identity: str | None = None
    identity_evidence_required: int = 0

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        from core.models.dto_helpers import dto_to_dict

        data = dto_to_dict(
            self,
            enum_fields=[
                "entity_type",
                "status",
                "domain",
                "goal_type",
                "timeframe",
                "measurement_type",
            ],
            datetime_fields=["created_at", "updated_at"],
        )
        for name in _OFFSET_FIELDS:
            offset_value = getattr(self, name)
            data[name] = (
                json.dumps(offset_to_jsonable(offset_value)) if offset_value is not None else None
            )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoalTemplateDTO:
        from core.models.dto_helpers import dto_from_dict

        for name in _OFFSET_FIELDS:
            if name in data:
                data[name] = jsonable_to_offset(data[name])
        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "goal_type",
                "timeframe",
                "measurement_type",
            ),
            datetime_fields=["created_at", "updated_at"],
            list_fields=[
                "tags",
                "milestones",
                "potential_obstacles",
                "strategies",
            ],
            dict_fields=["metadata"],
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        from core.models.dto_helpers import update_from_dict

        coerced: dict[str, Any] = dict(updates)
        for name in _OFFSET_FIELDS:
            if name in coerced and not isinstance(coerced[name], RelativeOffset):
                coerced[name] = jsonable_to_offset(coerced[name])

        update_from_dict(
            self,
            coerced,
            allowed_fields={
                "title",
                "content",
                "summary",
                "description",
                "word_count",
                "domain",
                "status",
                "tags",
                "metadata",
                # GoalTemplate-specific
                "goal_type",
                "timeframe",
                "measurement_type",
                "target_value",
                "unit_of_measurement",
                "start_offset",
                "target_offset",
                "milestones",
                "vision_statement",
                "why_important",
                "success_criteria",
                "potential_obstacles",
                "strategies",
                "fulfills_goal_template_uid",
                "inspired_by_choice_template_uid",
                "selected_choice_option_template_uid",
                "target_identity",
                "identity_evidence_required",
            },
            enum_mappings=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "goal_type",
                "timeframe",
                "measurement_type",
            ),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GoalTemplateDTO):
            return False
        return self.uid == other.uid
