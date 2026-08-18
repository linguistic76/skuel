"""
PrincipleUpdateIntent — Typed contract for partial principle updates.
====================================================================

Frozen dataclass carrying exactly the node-property fields a principle update is
allowed to change — nothing else. The contract becomes visible in the type: a
reader sees precisely what an update may touch, and it cannot be silently widened
to ``dict`` and back.

Update is *partial* and ``None`` is a meaningful value (clear a field), so every
field defaults to the shared ``UNSET`` sentinel. ``to_changes()`` returns only the
set fields — the patch to apply at the backend seam.

Principles have **no edge fields on the update path** (like Goals/Choices, unlike
Tasks). They carry one request-only field that is *not* a node column and is therefore
deliberately absent here: ``decision_criteria`` is present on the request but absent
from both ``Principle`` and ``PrincipleDTO``, so writing it would be a junk node
property and ``PrincipleUpdateRequest.to_intent()`` drops it.

Beyond the request-settable columns, this intent also models ``status`` — set by the
dedicated status route (``principles_api`` → ``update_principle(PrincipleUpdateIntent(
status=...))``), mirroring ``tasks_api`` / ``events_api`` / ``choices_api``.
``PrincipleUpdateRequest`` has no ``status`` field, so the request→intent path can
never carry it (no junk write).

See: ADR-066 (Typed Update Intents) — the write-path sibling of ADR-065's
``*InferenceResult``; ``docs/roadmap/done/update-intents.md`` for the phased migration.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from core.models.sentinels import UNSET, Unset


@dataclass(frozen=True)
class PrincipleUpdateIntent:
    """The node-property fields a principle update may change (ADR-066). ``UNSET`` =
    not in this update.

    Enum fields (principle_category, principle_source, strength, priority, status)
    carry their lowered string value, matching what the persistence boundary stores.
    """

    # --- Identity / statement ------------------------------------------------
    title: str | Unset | None = UNSET
    statement: str | Unset | None = UNSET
    description: str | Unset | None = UNSET

    # --- Classification ------------------------------------------------------
    principle_category: str | Unset | None = UNSET
    principle_source: str | Unset | None = UNSET
    strength: str | Unset | None = UNSET

    # --- Philosophical context ----------------------------------------------
    tradition: str | Unset | None = UNSET
    personal_interpretation: str | Unset | None = UNSET

    # --- Personal reflection --------------------------------------------------
    why_important: str | Unset | None = UNSET

    # --- Behavioral expression ----------------------------------------------
    key_behaviors: list[str] | Unset | None = UNSET

    # --- Status / priority / tags -------------------------------------------
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


__all__ = ["PrincipleUpdateIntent"]
