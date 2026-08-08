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
    title: str | None | Unset = UNSET
    description: str | None | Unset = UNSET
    vision_statement: str | None | Unset = UNSET
    goal_type: str | None | Unset = UNSET
    domain: str | None | Unset = UNSET
    timeframe: str | None | Unset = UNSET

    # --- Measurement ---------------------------------------------------------
    measurement_type: str | None | Unset = UNSET
    target_value: float | None | Unset = UNSET
    current_value: float | None | Unset = UNSET
    unit_of_measurement: str | None | Unset = UNSET

    # --- Timeline ------------------------------------------------------------
    start_date: date | None | Unset = UNSET
    target_date: date | None | Unset = UNSET
    completion_date: date | None | Unset = UNSET

    # --- Progress ------------------------------------------------------------
    progress_percentage: float | None | Unset = UNSET
    milestones: list[dict[str, Any]] | None | Unset = UNSET

    # --- Motivation ----------------------------------------------------------
    why_important: str | None | Unset = UNSET
    success_criteria: str | None | Unset = UNSET
    potential_obstacles: list[str] | None | Unset = UNSET
    strategies: list[str] | None | Unset = UNSET

    # --- Status / priority / tags / metadata ---------------------------------
    status: str | None | Unset = UNSET
    priority: str | None | Unset = UNSET
    tags: list[str] | None | Unset = UNSET
    metadata: dict[str, Any] | None | Unset = UNSET

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
