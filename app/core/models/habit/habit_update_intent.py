"""
HabitUpdateIntent — Typed contract for partial habit updates.
=============================================================

Frozen dataclass carrying exactly the node-property fields a habit update is allowed
to change — nothing else. The contract becomes visible in the type: a reader sees
precisely what an update may touch, and it cannot be silently widened to ``dict`` and
back.

Update is *partial* and ``None`` is a meaningful value (clear a field), so every field
defaults to the shared ``UNSET`` sentinel. ``to_changes()`` returns only the set fields —
the patch to apply at the backend seam.

Habits have **no edge fields on the update path** (like Goals, unlike Tasks). The four
cross-domain UID fields on ``HabitUpdateRequest`` (``linked_knowledge_uids``,
``linked_goal_uids``, ``linked_principle_uids``, ``prerequisite_habit_uids``) are graph
edges — synced on the create-with-context path, never written as node columns — so they
are deliberately absent here and ``HabitUpdateRequest.to_intent()`` does not carry them.

Beyond the request-settable columns, this intent also models the reminder columns that
the service-internal reminder methods (``set_habit_reminder`` / ``delete_habit_reminder``
in ``_CompletionMixin``) write by constructing this intent directly — carrying real columns
without leaking junk.

``force_archive`` is **not** a field here: it is a transient validation directive (bypass
the streak-preservation rule), not a persisted column. It travels as a dedicated keyword
argument on ``update_habit`` — never written to the node.

See: ADR-066 (Typed Update Intents) — the write-path sibling of ADR-065's
``*InferenceResult``; ``docs/roadmap/update-intents.md`` for the phased migration.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from core.models.sentinels import UNSET, Unset


@dataclass(frozen=True)
class HabitUpdateIntent:
    """The node-property fields a habit update may change (ADR-066). ``UNSET`` = not in
    this update.

    Enum fields (polarity, habit_category, habit_difficulty, recurrence_pattern,
    preferred_time, status, priority) carry their lowered string value, matching what the
    persistence boundary stores.
    """

    # --- Identity / content --------------------------------------------------
    title: str | None | Unset = UNSET
    description: str | None | Unset = UNSET

    # --- Classification ------------------------------------------------------
    polarity: str | None | Unset = UNSET
    habit_category: str | None | Unset = UNSET
    habit_difficulty: str | None | Unset = UNSET

    # --- Schedule ------------------------------------------------------------
    recurrence_pattern: str | None | Unset = UNSET
    target_days_per_week: int | None | Unset = UNSET
    preferred_time: str | None | Unset = UNSET
    duration_minutes: int | None | Unset = UNSET

    # --- Behavioral science (Atomic Habits loop) -----------------------------
    cue: str | None | Unset = UNSET
    routine: str | None | Unset = UNSET
    reward: str | None | Unset = UNSET

    # --- Reminders (not on the request; written by set/delete_habit_reminder
    #     through the core.update funnel) -----------------------------------
    reminder_time: str | None | Unset = UNSET
    reminder_days: list[str] | None | Unset = UNSET
    reminder_enabled: bool | None | Unset = UNSET

    # --- Status / priority / tags --------------------------------------------
    status: str | None | Unset = UNSET
    priority: str | None | Unset = UNSET
    tags: list[str] | None | Unset = UNSET

    def to_changes(self) -> dict[str, Any]:
        """Return only the explicitly-set fields as a backend-ready patch.

        Fields left ``UNSET`` are omitted (untouched); a field set to ``None`` is
        included (an explicit clear). This is the dict materialized at the single
        ``backend.update`` seam.
        """
        return {
            f.name: value for f in fields(self) if (value := getattr(self, f.name)) is not UNSET
        }


__all__ = ["HabitUpdateIntent"]
