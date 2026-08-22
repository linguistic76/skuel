"""
EventUpdateIntent — Typed contract for partial event updates.
============================================================

Frozen dataclass carrying exactly the fields an event update is allowed to change —
the node-property columns plus the two cross-domain edge UIDs the facade splits off.
The contract becomes visible in the type: a reader sees precisely what an update may
touch, and it cannot be silently widened to ``dict`` and back.

Update is *partial* and ``None`` is a meaningful value (clear a field), so every field
defaults to the shared ``UNSET`` sentinel. ``to_changes()`` returns only the set fields —
the patch to apply at the backend seam.

Like Tasks (and unlike Goals), Events carry **edge fields on the update path**:
``milestone_celebration_for_goal`` → ``(Event)-[:CELEBRATES_GOAL]->(Goal)`` and
``reinforces_habit_uid`` → ``(Event)-[:REINFORCES_HABIT]->(Habit)``. These are graph
edges, never node columns — ``EventsService.update_event`` splits them out (resetting them
to ``UNSET`` on the property sub-intent) before writing properties, then replaces the
edges. They live on this intent only so the facade can carry them; ``to_changes()`` would
write them as junk node properties if they ever reached the backend, which is exactly the
split the ADR-035/ADR-065 graph-native migration enforces.

Beyond the request-settable columns, this intent also models ``metadata`` for callers
that construct the intent directly with merged metadata updates.

Deliberately **absent**: ``practices_knowledge_uids`` / ``executes_tasks`` (on
``EventUpdateRequest`` but neither node columns nor handled edges on the update path — the
create path drops them too) and ``notes`` / ``quality_score`` (not Event columns).
Carrying them would write junk node properties. ``completed_at`` IS here — the canonical
Event completion stamp (completion-stamping arc, 2026-08-22), a real column on
``Event``/``EventDTO``.

See: ADR-066 (Typed Update Intents) — the write-path sibling of ADR-065's
``*InferenceResult``; ``docs/roadmap/done/update-intents.md`` for the phased migration.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any

from core.models.sentinels import UNSET, Unset

if TYPE_CHECKING:
    from datetime import date, datetime, time


@dataclass(frozen=True)
class EventUpdateIntent:
    """The fields an event update may change (ADR-066). ``UNSET`` = not in this update.

    Enum fields (event_type, visibility, priority, status) carry their lowered string
    value, matching what the persistence boundary stores.
    """

    # --- Identity / classification -------------------------------------------
    title: str | Unset | None = UNSET
    description: str | Unset | None = UNSET
    event_type: str | Unset | None = UNSET

    # --- Timing --------------------------------------------------------------
    event_date: date | Unset | None = UNSET
    start_time: time | Unset | None = UNSET
    end_time: time | Unset | None = UNSET

    # --- Logistics -----------------------------------------------------------
    location: str | Unset | None = UNSET
    is_online: bool | Unset | None = UNSET
    meeting_url: str | Unset | None = UNSET

    # --- Reminders -----------------------------------------------------------
    reminder_minutes: int | Unset | None = UNSET

    # --- Lifecycle -----------------------------------------------------------
    # When the event transitioned into COMPLETED; explicit None = clear (reopen).
    completed_at: datetime | Unset | None = UNSET

    # --- Quality / learning --------------------------------------------------
    habit_completion_quality: int | Unset | None = UNSET
    knowledge_retention_check: bool | Unset | None = UNSET

    # --- Status / visibility / priority / tags / metadata --------------------
    status: str | Unset | None = UNSET
    visibility: str | Unset | None = UNSET
    priority: str | Unset | None = UNSET
    tags: list[str] | Unset | None = UNSET
    metadata: dict[str, Any] | Unset | None = UNSET

    # --- Edge-typed fields (split off by the facade, never node columns) ------
    # (Event)-[:CELEBRATES_GOAL]->(Goal) / (Event)-[:REINFORCES_HABIT]->(Habit).
    milestone_celebration_for_goal: str | Unset | None = UNSET
    reinforces_habit_uid: str | Unset | None = UNSET

    def to_changes(self) -> dict[str, Any]:
        """Return only the explicitly-set fields as a backend-ready patch.

        Fields left ``UNSET`` are omitted (untouched); a field set to ``None`` is
        included (an explicit clear). This is the dict materialized at the single
        ``backend.update`` seam — call it only on the *property* sub-intent, after the
        facade has split the two edge fields off (see ``_split_relationship_intent``).
        ``event_date`` is down-cast from any stray ``datetime`` so an update never
        persists a time component in a date field (#766).
        """
        from core.models.dto_helpers import coerce_date_fields

        changes = {
            f.name: value for f in fields(self) if (value := getattr(self, f.name)) is not UNSET
        }
        return coerce_date_fields(changes, "event_date")


__all__ = ["EventUpdateIntent"]
