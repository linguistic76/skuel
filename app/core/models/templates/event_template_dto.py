"""EventTemplateDTO — Transfer tier for EventTemplate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import (
    time,
)
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enum_field_registry import enum_fields_for
from core.models.enums.entity_enums import EntityType
from core.models.templates.offset_helpers import (
    TEMPLATE_OFFSET_FIELDS,
    jsonable_to_offset,
    offset_to_jsonable,
)
from core.models.templates.relative_offset import RelativeOffset

_OFFSET_FIELDS: tuple[str, ...] = TEMPLATE_OFFSET_FIELDS[EntityType.EVENT_TEMPLATE]


@dataclass
class EventTemplateDTO(EntityDTO):
    """Mutable DTO for EventTemplate entities."""

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.EVENT_TEMPLATE, kw_only=True)

    # Scheduling
    event_offset: RelativeOffset | None = None
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = None

    # Logistics
    event_type: str | None = None
    location: str | None = None
    is_online: bool = False
    meeting_url: str | None = None

    # Recurrence
    recurrence_pattern: str | None = None
    recurrence_end_offset: RelativeOffset | None = None

    # Reminders
    reminder_minutes: int | None = None

    # Attendees cap
    max_attendees: int | None = None

    # Cross-template refs
    reinforces_habit_template_uid: str | None = None
    milestone_celebration_for_goal_template_uid: str | None = None

    # Milestone/curriculum
    is_milestone_event: bool = False
    milestone_type: str | None = None
    curriculum_week: int | None = None

    # Quality tracking defaults
    knowledge_retention_check: bool = False
    recurrence_maintains_habit: bool = False
    skip_breaks_habit_streak: bool = False

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        from core.models.dto_helpers import dto_to_dict

        data = dto_to_dict(
            self,
            enum_fields=["entity_type", "status", "domain"],
            datetime_fields=["created_at", "updated_at"],
            time_fields=["start_time", "end_time"],
        )
        for name in _OFFSET_FIELDS:
            offset_value = getattr(self, name)
            data[name] = (
                json.dumps(offset_to_jsonable(offset_value)) if offset_value is not None else None
            )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventTemplateDTO:
        from core.models.dto_helpers import dto_from_dict

        for name in _OFFSET_FIELDS:
            if name in data:
                data[name] = jsonable_to_offset(data[name])
        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for("entity_type", "status", "domain"),
            datetime_fields=["created_at", "updated_at"],
            time_fields=["start_time", "end_time"],
            list_fields=["tags"],
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
                # EventTemplate-specific
                "event_offset",
                "start_time",
                "end_time",
                "duration_minutes",
                "event_type",
                "location",
                "is_online",
                "meeting_url",
                "recurrence_pattern",
                "recurrence_end_offset",
                "reminder_minutes",
                "max_attendees",
                "reinforces_habit_template_uid",
                "milestone_celebration_for_goal_template_uid",
                "is_milestone_event",
                "milestone_type",
                "curriculum_week",
                "knowledge_retention_check",
                "recurrence_maintains_habit",
                "skip_breaks_habit_streak",
            },
            enum_mappings=enum_fields_for("entity_type", "status", "domain"),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EventTemplateDTO):
            return False
        return self.uid == other.uid
