"""GoalTemplateDTO — Transfer tier for GoalTemplate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.goal_enums import GoalTimeframe, GoalType, MeasurementType
from core.models.templates.relative_offset import RelativeOffset

_OFFSET_FIELDS: tuple[str, ...] = ("start_offset", "target_offset")


def _offset_to_jsonable(offset: RelativeOffset | None) -> dict[str, int] | None:
    if offset is None:
        return None
    return {"days": offset.days, "hours": offset.hours, "minutes": offset.minutes}


def _jsonable_to_offset(raw: object) -> RelativeOffset | None:
    if raw is None:
        return None
    if isinstance(raw, RelativeOffset):
        return raw
    data: object = raw
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(data, dict):
        return None
    return RelativeOffset(
        days=int(data.get("days", 0) or 0),
        hours=int(data.get("hours", 0) or 0),
        minutes=int(data.get("minutes", 0) or 0),
    )


@dataclass
class GoalTemplateDTO(EntityDTO):
    """Mutable DTO for GoalTemplate entities."""

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
                json.dumps(_offset_to_jsonable(offset_value)) if offset_value is not None else None
            )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoalTemplateDTO:
        from core.models.dto_helpers import dto_from_dict

        for name in _OFFSET_FIELDS:
            if name in data:
                data[name] = _jsonable_to_offset(data[name])
        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "goal_type": GoalType,
                "timeframe": GoalTimeframe,
                "measurement_type": MeasurementType,
            },
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
                coerced[name] = _jsonable_to_offset(coerced[name])

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
            enum_mappings={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "goal_type": GoalType,
                "timeframe": GoalTimeframe,
                "measurement_type": MeasurementType,
            },
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GoalTemplateDTO):
            return False
        return self.uid == other.uid
