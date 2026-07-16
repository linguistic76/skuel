"""
RelativeOffset JSON Serialization Helpers
=========================================

Shared by every template DTO with ``*_offset`` fields (Task, Goal, Habit,
Event, Choice). Each offset round-trips through a single JSON column:
``offset_to_jsonable`` renders the storage shape, ``jsonable_to_offset``
accepts whatever the storage layer hands back (dict, JSON string, or None).
"""

from __future__ import annotations

import json

from core.models.templates.relative_offset import RelativeOffset


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
