"""
ChoiceUpdateIntent — Typed contract for partial choice updates.
==============================================================

Frozen dataclass carrying exactly the node-property fields a choice update is
allowed to change — nothing else. The contract becomes visible in the type: a
reader sees precisely what an update may touch, and it cannot be silently widened
to ``dict`` and back.

Update is *partial* and ``None`` is a meaningful value (clear a field), so every
field defaults to the shared ``UNSET`` sentinel. ``to_changes()`` returns only the
set fields — the patch to apply at the backend seam.

Choices have **no edge fields on the update path** (like Goals, unlike Tasks). The
``informed_by_knowledge_uids`` field exists only on ``ChoiceCreateRequest`` — it is a
graph edge (``(Choice)-[:INFORMED_BY_KNOWLEDGE]->(Ku)``) synced on the create path,
never written as a node column. ``ChoiceUpdateRequest`` carries no edge fields at all,
so there is nothing to split off here.

Beyond the request-settable columns, this intent also models ``status`` — set by the
dedicated status route (``choices_api`` → ``update_choice(ChoiceUpdateIntent(status=...))``),
mirroring ``tasks_api`` / ``events_api``. Decision-finalization and outcome columns
(``selected_option_uid`` / ``decided_at`` / ``satisfaction_score`` / ``actual_outcome`` /
``lessons_learned`` / ``metadata``) are deliberately absent — they flow through the
``make_decision`` / ``evaluate_choice_outcome`` raw-write paths (each with its own
provenance event), not this generic property-update path. ``decision_context`` IS here:
it is the circumstance the choice is made in, authored up front and editable at any
time, unlike ``decision_rationale``, which ``make_decision`` writes once.

See: ADR-066 (Typed Update Intents) — the write-path sibling of ADR-065's
``*InferenceResult``; ``docs/roadmap/done/update-intents.md`` for the phased migration.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any

from core.models.sentinels import UNSET, Unset

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class ChoiceUpdateIntent:
    """The node-property fields a choice update may change (ADR-066). ``UNSET`` = not
    in this update.

    Enum fields (choice_type, domain, priority, status) carry their lowered string
    value, matching what the persistence boundary stores.
    """

    # --- Identity / classification -------------------------------------------
    title: str | Unset | None = UNSET
    description: str | Unset | None = UNSET
    choice_type: str | Unset | None = UNSET
    domain: str | Unset | None = UNSET

    # --- Decision context ----------------------------------------------------
    decision_context: str | Unset | None = UNSET
    decision_deadline: datetime | Unset | None = UNSET
    decision_criteria: list[str] | Unset | None = UNSET
    constraints: list[str] | Unset | None = UNSET
    stakeholders: list[str] | Unset | None = UNSET

    # --- Status / priority / tags --------------------------------------------
    status: str | Unset | None = UNSET
    priority: str | Unset | None = UNSET
    tags: list[str] | Unset | None = UNSET

    def to_changes(self) -> dict[str, Any]:
        """Return only the explicitly-set fields as a backend-ready patch.

        Fields left ``UNSET`` are omitted (untouched); a field set to ``None`` is
        included (an explicit clear). This is the dict materialized at the single
        ``backend.update`` seam.
        """
        return {
            f.name: value for f in fields(self) if (value := getattr(self, f.name)) is not UNSET
        }


__all__ = ["ChoiceUpdateIntent"]
