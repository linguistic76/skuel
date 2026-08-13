"""
TaskUpdateIntent — Typed contract for partial task updates.
===========================================================

Frozen dataclass carrying exactly the fields a task update is allowed to change —
nothing else. The contract becomes visible in the type: a reader sees precisely what
an update may touch, and it cannot be silently widened to ``dict`` and back.

Update is *partial* and ``None`` is a meaningful value (clear a field), so every field
defaults to the shared ``UNSET`` sentinel. ``to_changes()`` returns only the set fields —
the patch to apply at the backend seam.

Two field groups:

- **Node properties** (title, status, …) — materialized via ``to_changes()`` and written
  with a single ``backend.update`` at the service↔backend seam.
- **Relationship-typed fields** (``reinforces_habit_uid``, ``applies_knowledge_uids``) —
  graph edges, NOT node columns. The Tasks facade splits these off the intent and syncs
  them as ``REINFORCES_HABIT`` / ``APPLIES_KNOWLEDGE`` edges; they never reach
  ``backend.update`` as properties. They live on the intent so the typed
  ``TaskUpdateRequest.to_intent()`` path can carry them end to end.

See: ADR-066 (Typed Update Intents) — the write-path sibling of ADR-065's
``*InferenceResult``; ``docs/roadmap/done/update-intents.md`` for the phased migration.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any

from core.models.sentinels import UNSET, Unset

if TYPE_CHECKING:
    from datetime import date


@dataclass(frozen=True)
class TaskUpdateIntent:
    """The fields a task update may change (ADR-066). ``UNSET`` = not in this update.

    Mirrors the updatable fields of ``TaskUpdateRequest``; enum fields (priority, status)
    carry their lowered string value, matching what the persistence boundary stores.
    """

    # --- Node properties -----------------------------------------------------
    title: str | Unset | None = UNSET
    description: str | Unset | None = UNSET
    due_date: date | Unset | None = UNSET
    scheduled_date: date | Unset | None = UNSET
    duration_minutes: int | Unset | None = UNSET
    priority: str | Unset | None = UNSET
    status: str | Unset | None = UNSET
    project: str | Unset | None = UNSET
    assignee: str | Unset | None = UNSET
    tags: list[str] | Unset | None = UNSET
    actual_minutes: int | Unset | None = UNSET
    completion_date: date | Unset | None = UNSET
    fulfills_goal_uid: str | Unset | None = UNSET
    aligned_principle_uids: list[str] | Unset | None = UNSET
    goal_progress_contribution: float | Unset | None = UNSET
    knowledge_mastery_check: bool | Unset | None = UNSET
    habit_streak_maintainer: bool | Unset | None = UNSET
    prerequisite_knowledge_uids: list[str] | Unset | None = UNSET
    prerequisite_task_uids: list[str] | Unset | None = UNSET

    # --- Relationship-typed (edge) fields — split off by the facade ----------
    reinforces_habit_uid: str | Unset | None = UNSET
    applies_knowledge_uids: list[str] | Unset | None = UNSET

    def to_changes(self) -> dict[str, Any]:
        """Return only the explicitly-set fields as a backend-ready patch.

        Fields left ``UNSET`` are omitted (untouched); a field set to ``None`` is
        included (an explicit clear). This is the dict materialized at the single
        ``backend.update`` seam. Date fields are down-cast from any stray ``datetime``
        so an update never persists a time component in a date field (#766).
        """
        from core.models.dto_helpers import coerce_date_fields

        changes = {
            f.name: value for f in fields(self) if (value := getattr(self, f.name)) is not UNSET
        }
        return coerce_date_fields(changes, "due_date", "scheduled_date", "completion_date")


__all__ = ["TaskUpdateIntent"]
