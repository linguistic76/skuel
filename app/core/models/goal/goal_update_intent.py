"""
GoalUpdateIntent — Typed contract for partial goal updates.
==========================================================

Frozen dataclass carrying exactly the node-property fields a goal update is allowed
to change — nothing else. The contract becomes visible in the type: a reader sees
precisely what an update may touch, and it cannot be silently widened to ``dict`` and
back.

Update is *partial* and ``None`` is a meaningful value (clear a field), so every field
defaults to the shared ``UNSET`` sentinel. ``to_changes()`` returns only the set fields —
the patch to apply at the backend seam.

Goals have **no edge fields on the update path** (unlike Tasks). The three cross-domain
UID fields on ``GoalUpdateRequest`` (``required_knowledge_uids``, ``supporting_habit_uids``,
``guiding_principle_uids``) are graph edges — synced by ``create_goal_with_context`` on the
create path, never written as node columns — so they are deliberately absent here and
``GoalUpdateRequest.to_intent()`` does not carry them.

Beyond the request-settable columns, this intent also models the columns the
service-internal status transitions write (``status`` / ``progress_percentage`` /
``completion_date`` / ``metadata`` via ``complete_goal`` / ``pause_goal`` / ``archive_goal``),
which construct this intent directly.

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
class GoalUpdateIntent:
    """The node-property fields a goal update may change (ADR-066). ``UNSET`` = not in
    this update.

    Enum fields (goal_type, domain, timeframe, measurement_type, status, priority) carry
    their lowered string value, matching what the persistence boundary stores.
    """

    # --- Identity / classification -------------------------------------------
    title: str | Unset | None = UNSET
    description: str | Unset | None = UNSET
    vision_statement: str | Unset | None = UNSET
    goal_type: str | Unset | None = UNSET
    domain: str | Unset | None = UNSET
    timeframe: str | Unset | None = UNSET

    # --- Measurement ---------------------------------------------------------
    measurement_type: str | Unset | None = UNSET
    target_value: float | Unset | None = UNSET
    current_value: float | Unset | None = UNSET
    unit_of_measurement: str | Unset | None = UNSET

    # --- Timeline ------------------------------------------------------------
    start_date: date | Unset | None = UNSET
    target_date: date | Unset | None = UNSET
    completion_date: date | Unset | None = UNSET

    # --- Progress ------------------------------------------------------------
    progress_percentage: float | Unset | None = UNSET
    milestones: list[dict[str, Any]] | Unset | None = UNSET

    # --- Motivation ----------------------------------------------------------
    why_important: str | Unset | None = UNSET
    success_criteria: str | Unset | None = UNSET
    potential_obstacles: list[str] | Unset | None = UNSET
    strategies: list[str] | Unset | None = UNSET

    # --- Status / priority / tags / metadata ---------------------------------
    status: str | Unset | None = UNSET
    priority: str | Unset | None = UNSET
    tags: list[str] | Unset | None = UNSET
    metadata: dict[str, Any] | Unset | None = UNSET

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
        return coerce_date_fields(changes, "start_date", "target_date", "completion_date")


__all__ = ["GoalUpdateIntent"]
