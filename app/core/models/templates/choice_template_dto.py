"""ChoiceTemplateDTO — Transfer tier for ChoiceTemplate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enums import Domain
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.templates.relative_offset import RelativeOffset

_OFFSET_FIELDS: tuple[str, ...] = ("decision_deadline_offset",)


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
class ChoiceTemplateDTO(EntityDTO):
    """Mutable DTO for ChoiceTemplate entities."""

    choice_type: ChoiceType | None = None
    options: list[dict[str, Any]] = field(default_factory=list)
    decision_rationale: str | None = None
    decision_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    stakeholders: list[str] = field(default_factory=list)

    # Timing
    decision_deadline_offset: RelativeOffset | None = None

    # Curriculum
    inspiration_type: str | None = None
    expands_possibilities: bool = False

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        from core.models.dto_helpers import dto_to_dict

        data = dto_to_dict(
            self,
            enum_fields=["entity_type", "status", "domain", "choice_type"],
            datetime_fields=["created_at", "updated_at"],
        )
        for name in _OFFSET_FIELDS:
            offset_value = getattr(self, name)
            data[name] = (
                json.dumps(_offset_to_jsonable(offset_value)) if offset_value is not None else None
            )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChoiceTemplateDTO:
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
                "choice_type": ChoiceType,
            },
            datetime_fields=["created_at", "updated_at"],
            list_fields=[
                "tags",
                "options",
                "decision_criteria",
                "constraints",
                "stakeholders",
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
                # ChoiceTemplate-specific
                "choice_type",
                "options",
                "decision_rationale",
                "decision_criteria",
                "constraints",
                "stakeholders",
                "decision_deadline_offset",
                "inspiration_type",
                "expands_possibilities",
            },
            enum_mappings={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "choice_type": ChoiceType,
            },
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChoiceTemplateDTO):
            return False
        return self.uid == other.uid
