"""HabitTemplateDTO — Transfer tier for HabitTemplate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enum_field_registry import enum_fields_for
from core.models.enums.entity_enums import EntityType
from core.models.enums.habit_enums import HabitCategory, HabitDifficulty, HabitPolarity
from core.models.enums.scheduling_enums import TimeOfDay
from core.models.templates.offset_helpers import (
    TEMPLATE_OFFSET_FIELDS,
    jsonable_to_offset,
    offset_to_jsonable,
)
from core.models.templates.relative_offset import RelativeOffset

_OFFSET_FIELDS: tuple[str, ...] = TEMPLATE_OFFSET_FIELDS[EntityType.HABIT_TEMPLATE]


@dataclass
class HabitTemplateDTO(EntityDTO):
    """Mutable DTO for HabitTemplate entities."""

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.HABIT_TEMPLATE, kw_only=True)

    # Classification
    polarity: HabitPolarity | None = None
    habit_category: HabitCategory | None = None
    habit_difficulty: HabitDifficulty | None = None

    # Behavior design
    cue: str | None = None
    routine: str | None = None
    reward: str | None = None

    # Identity
    reinforces_identity: str | None = None
    is_identity_habit: bool = False
    target_identity: str | None = None
    identity_evidence_required: int = 0

    # Scheduling
    duration_minutes: int | None = None
    recurrence_pattern: str | None = None
    recurrence_end_offset: RelativeOffset | None = None
    target_days_per_week: int | None = None
    preferred_time: TimeOfDay | None = None

    # Reminders
    reminder_time: str | None = None
    reminder_days: list[str] = field(default_factory=list)
    reminder_enabled: bool = False

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
                "polarity",
                "habit_category",
                "habit_difficulty",
                "preferred_time",
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
    def from_dict(cls, data: dict[str, Any]) -> HabitTemplateDTO:
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
                "polarity",
                "habit_category",
                "habit_difficulty",
                "preferred_time",
            ),
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags", "reminder_days"],
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
                # HabitTemplate-specific
                "polarity",
                "habit_category",
                "habit_difficulty",
                "cue",
                "routine",
                "reward",
                "reinforces_identity",
                "is_identity_habit",
                "target_identity",
                "identity_evidence_required",
                "duration_minutes",
                "recurrence_pattern",
                "recurrence_end_offset",
                "target_days_per_week",
                "preferred_time",
                "reminder_time",
                "reminder_days",
                "reminder_enabled",
            },
            enum_mappings=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "polarity",
                "habit_category",
                "habit_difficulty",
                "preferred_time",
            ),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HabitTemplateDTO):
            return False
        return self.uid == other.uid
