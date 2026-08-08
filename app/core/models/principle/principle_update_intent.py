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
Tasks). They also carry two request-only fields that are *not* node columns and are
therefore deliberately absent here:

- ``why_important`` — folded into ``description`` with a canonical marker (see
  ``merge_why_important``); ``principles_ui`` re-folds it into the intent's
  ``description`` using the existing principle as the base. There is no
  ``why_important`` column, so ``PrincipleUpdateRequest.to_intent()`` drops it.
- ``decision_criteria`` — present on the request but absent from both ``Principle``
  and ``PrincipleDTO``; writing it would be a junk node property, so it is dropped.

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
    title: str | None | Unset = UNSET
    statement: str | None | Unset = UNSET
    description: str | None | Unset = UNSET

    # --- Classification ------------------------------------------------------
    principle_category: str | None | Unset = UNSET
    principle_source: str | None | Unset = UNSET
    strength: str | None | Unset = UNSET

    # --- Philosophical context ----------------------------------------------
    tradition: str | None | Unset = UNSET
    personal_interpretation: str | None | Unset = UNSET

    # --- Behavioral expression ----------------------------------------------
    key_behaviors: list[str] | None | Unset = UNSET

    # --- Status / priority / tags -------------------------------------------
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


__all__ = ["PrincipleUpdateIntent"]
