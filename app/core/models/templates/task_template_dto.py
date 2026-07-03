"""
TaskTemplateDTO — Transfer Tier for TaskTemplate
================================================

Mutable dataclass DTO mirroring :class:`TaskTemplate`. RelativeOffset values
are stored as the value type itself in-memory; serialization to Neo4j-friendly
JSON is delegated to ``to_dict``/``from_dict`` so each ``_offset`` field
round-trips through a single JSON column per offset.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.templates.relative_offset import RelativeOffset

# Names of fields that hold a RelativeOffset value. Centralised so adding a
# new offset later is a single-line change.
_OFFSET_FIELDS: tuple[str, ...] = (
    "due_offset",
    "scheduled_offset",
    "recurrence_end_offset",
)


def _offset_to_jsonable(offset: RelativeOffset | None) -> dict[str, int] | None:
    """Render a RelativeOffset as a JSON-friendly dict (or None)."""
    if offset is None:
        return None
    return {"days": offset.days, "hours": offset.hours, "minutes": offset.minutes}


def _jsonable_to_offset(raw: object) -> RelativeOffset | None:
    """Inverse of :func:`_offset_to_jsonable` — accepts dict, JSON string, or None."""
    if raw is None:
        return None
    if isinstance(raw, RelativeOffset):
        return raw
    data: object = raw
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError, TypeError:
            return None
    if not isinstance(data, dict):
        return None
    return RelativeOffset(
        days=int(data.get("days", 0) or 0),
        hours=int(data.get("hours", 0) or 0),
        minutes=int(data.get("minutes", 0) or 0),
    )


@dataclass
class TaskTemplateDTO(EntityDTO):
    """Mutable DTO for TaskTemplate entities."""

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.TASK_TEMPLATE, kw_only=True)

    # Scheduling
    due_offset: RelativeOffset | None = None
    scheduled_offset: RelativeOffset | None = None
    duration_minutes: int | None = None

    # Recurrence
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_offset: RelativeOffset | None = None

    # Hierarchy
    parent_template_uid: str | None = None
    project: str | None = None

    # Cross-template refs
    fulfills_goal_template_uid: str | None = None
    reinforces_habit_template_uid: str | None = None
    scheduled_event_template_uid: str | None = None

    # Progress impact
    goal_progress_contribution: float = 0.0
    knowledge_mastery_check: bool = False
    habit_streak_maintainer: bool = False
    completion_updates_goal: bool = False

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        from core.models.dto_helpers import dto_to_dict

        data = dto_to_dict(
            self,
            enum_fields=["entity_type", "status", "domain", "recurrence_pattern"],
            datetime_fields=["created_at", "updated_at"],
        )
        for name in _OFFSET_FIELDS:
            offset_value = getattr(self, name)
            data[name] = (
                json.dumps(_offset_to_jsonable(offset_value)) if offset_value is not None else None
            )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskTemplateDTO:
        from core.models.dto_helpers import dto_from_dict

        # Pre-parse RelativeOffset fields so dto_from_dict's generic path
        # receives a value of the declared type.
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
                "recurrence_pattern": RecurrencePattern,
            },
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags"],
            dict_fields=["metadata"],
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        from core.models.dto_helpers import update_from_dict

        # Coerce any RelativeOffset payloads coming in as dicts/JSON before
        # the generic updater applies them.
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
                # TaskTemplate-specific
                "due_offset",
                "scheduled_offset",
                "duration_minutes",
                "recurrence_pattern",
                "recurrence_end_offset",
                "parent_template_uid",
                "project",
                "fulfills_goal_template_uid",
                "reinforces_habit_template_uid",
                "scheduled_event_template_uid",
                "goal_progress_contribution",
                "knowledge_mastery_check",
                "habit_streak_maintainer",
                "completion_updates_goal",
            },
            enum_mappings={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
            },
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TaskTemplateDTO):
            return False
        return self.uid == other.uid
