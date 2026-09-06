"""
RelativeOffset JSON Serialization Helpers
=========================================

Shared by every template DTO with ``*_offset`` fields (Task, Goal, Habit,
Event, Choice). Each offset round-trips through a single JSON column:
``offset_to_jsonable`` renders the storage shape, ``jsonable_to_offset``
accepts whatever the storage layer hands back (dict, JSON string, or None).

``TEMPLATE_OFFSET_FIELDS`` names which fields those are, per EntityType — the
DTOs and the vault ingest door read it rather than each keeping its own list.
"""

from __future__ import annotations

import json

from core.models.enums.entity_enums import EntityType
from core.models.templates.relative_offset import RelativeOffset

# Which fields hold a RelativeOffset, per Activity Template type. THE list:
# each template DTO's ``_OFFSET_FIELDS`` reads its own row, and the vault
# ingest door walks the row for the type it is preparing. PrincipleTemplate
# has no scheduling, hence the empty tuple — an explicit row, so the map
# enumerates all six types and cannot silently omit one.
TEMPLATE_OFFSET_FIELDS: dict[EntityType, tuple[str, ...]] = {
    EntityType.TASK_TEMPLATE: ("due_offset", "scheduled_offset", "recurrence_end_offset"),
    EntityType.GOAL_TEMPLATE: ("start_offset", "target_offset"),
    EntityType.HABIT_TEMPLATE: ("recurrence_end_offset",),
    EntityType.EVENT_TEMPLATE: ("event_offset", "recurrence_end_offset"),
    EntityType.CHOICE_TEMPLATE: ("decision_deadline_offset",),
    EntityType.PRINCIPLE_TEMPLATE: (),
}

# The keys a RelativeOffset is built from. An authored mapping carrying
# anything else is a typo whose value would be silently dropped to zero.
OFFSET_KEYS: frozenset[str] = frozenset({"days", "hours", "minutes"})


def offset_to_jsonable(offset: RelativeOffset | None) -> dict[str, int] | None:
    """Render a RelativeOffset as a JSON-friendly dict (or None)."""
    if offset is None:
        return None
    return {"days": offset.days, "hours": offset.hours, "minutes": offset.minutes}


def jsonable_to_offset(raw: object) -> RelativeOffset | None:
    """Inverse of :func:`offset_to_jsonable` — accepts dict, JSON string, or None."""
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


def authored_offset_to_jsonable(raw: object) -> dict[str, int] | None:
    """The canonical storage dict for a vault-authored offset, or None if unauthorable.

    The vault door's read of an authored ``due_offset: {days: 7}``. Returns the
    same three-key dict the DTO write path stores, so both doors persist one
    shape; returns None for anything :func:`jsonable_to_offset` could not
    rebuild — an int, a list, an unparseable string — and for a mapping
    carrying keys outside :data:`OFFSET_KEYS` or non-integer values, which
    would otherwise round-trip to a silent zero.

    None means "not authorable", never "absent": the caller checks for absence
    before calling. Ingestion leaves an unauthorable value verbatim so
    ``validate_entity_data`` owns the rejection and the author gets one
    actionable per-file message.
    """
    data: object = raw
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError, TypeError:
            return None
    if not isinstance(data, dict):
        return None
    if not set(data).issubset(OFFSET_KEYS):
        return None
    parsed: dict[str, int] = {}
    for key in ("days", "hours", "minutes"):
        value = data.get(key, 0)
        if value is None:
            value = 0
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        parsed[key] = value
    return parsed
