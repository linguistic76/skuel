"""
Completion stamping — the shared status-transition helper for Activity updates.
==============================================================================

Every intent-based Activity update funnels through one per-domain core method
(``update_task`` … ``update_principle``). Each of those six chokepoints calls
:func:`completion_transition_patch` before its write so that:

1. **The status target is legal for the type** — ``EntityType.valid_statuses()``
   is enforced at the seam instead of being documentation (e.g. a Principle can
   never be written ``completed``).
2. **Transitions INTO ``COMPLETED`` stamp the domain's canonical completion
   field** (Task ``completion_date``, Goal ``achieved_date``, Habit / Event /
   Choice ``completed_at``) so the completion moment stops being approximated by
   the mutable ``updated_at``.
3. **Transitions OUT of ``COMPLETED`` clear that field** (reopen) — the stamp is
   non-null exactly when the entity is completed.

The gate is the *transition*, not the presence of the status key: re-posting
``status=completed`` on an already-completed entity must not re-date it. An
update that already carries the domain's completion field keeps authority — a
caller-supplied date (``complete_goal(achieved_date=…)``) or an explicit
complete flow (``complete_task_with_cascade``) sets its own stamp and the
helper injects nothing. Default-dated ``complete_goal`` carries no field and
defers to the gate here, so a retried complete never re-dates.

Bypass paths are handled elsewhere by design: ingestion never auto-stamps (the
file is the source of truth for its own dates), and the DSL ``[x]`` create door
parses the obsidian-tasks ``✅ date`` into ``completion_date`` at conversion.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from types import MappingProxyType
from typing import Any

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.utils.result_simplified import Errors, Result

__all__ = [
    "COMPLETION_FIELDS",
    "completion_transition_patch",
    "is_completion_transition",
    "is_reopen_transition",
]

# Per-domain canonical completion field + stamp value factory. Task and Goal
# stamp calendar dates (matching their established writers); the datetime
# domains stamp the moment. Principle has no entry: COMPLETED is not a valid
# Principle status, so the legality check above refuses it before stamping
# could ever apply.
_STAMP_SPECS: dict[EntityType, tuple[str, Callable[[], date | datetime]]] = {
    EntityType.TASK: ("completion_date", date.today),
    EntityType.GOAL: ("achieved_date", date.today),
    EntityType.HABIT: ("completed_at", datetime.now),
    EntityType.EVENT: ("completed_at", datetime.now),
    EntityType.CHOICE: ("completed_at", datetime.now),
}

#: Which node property each Activity domain stamps on completion — the same
#: mapping the chokepoints write, published so out-of-process consumers (the
#: one-shot backfill in ``scripts/backfill_activity_completion_stamps.py``)
#: cannot drift from it. A domain absent here does not record a completion
#: moment; Principle is absent because COMPLETED is not one of its valid
#: statuses.
COMPLETION_FIELDS: Mapping[EntityType, str] = MappingProxyType(
    {entity_type: field for entity_type, (field, _) in _STAMP_SPECS.items()}
)


def _coerce_status(value: EntityStatus | str | None) -> EntityStatus | None:
    """Normalize a stored/intended status to the enum; ``None`` for anything else.

    Canonical values only — aliases are resolved at the API boundary
    (``from_string``), never at the write seam (emission rule).
    """
    if isinstance(value, EntityStatus):
        return value
    if isinstance(value, str):
        try:
            return EntityStatus(value)
        except ValueError:
            return None
    return None


def is_completion_transition(
    old_status: EntityStatus | str | None, changes: Mapping[str, Any]
) -> bool:
    """True when this update moves the entity INTO ``COMPLETED``.

    Transition-gated: re-posting ``completed`` on an already-completed entity is
    not a transition. Used by the chokepoints that publish a completion domain
    event (``CalendarEventCompleted``, ``GoalAchieved``) so the event and the
    stamp agree on what counts as completing.
    """
    if "status" not in changes:
        return False
    new_status = _coerce_status(changes["status"])
    return (
        new_status is EntityStatus.COMPLETED
        and _coerce_status(old_status) is not EntityStatus.COMPLETED
    )


def is_reopen_transition(old_status: EntityStatus | str | None, changes: Mapping[str, Any]) -> bool:
    """True when this update moves the entity OUT of ``COMPLETED``.

    The mirror of :func:`is_completion_transition`, and gated the same way: an
    update that leaves an already-open entity open is not a reopen. It agrees
    exactly with the branch of :func:`completion_transition_patch` that clears
    the stamp, including the requirement that the *new* status be a canonical
    ``EntityStatus`` value — an unrecognized status is a validation failure
    there, never a reopen here.

    Used by ``TasksCoreService.update_task`` to publish ``TaskReopened``, so the
    event and the stamp clear agree on what counts as reopening.
    """
    if "status" not in changes:
        return False
    new_status = _coerce_status(changes["status"])
    return (
        new_status is not None
        and new_status is not EntityStatus.COMPLETED
        and _coerce_status(old_status) is EntityStatus.COMPLETED
    )


def completion_transition_patch(
    entity_type: EntityType,
    old_status: EntityStatus | str | None,
    changes: Mapping[str, Any],
) -> Result[dict[str, Any]]:
    """Validate the status target and derive the completion-stamp patch.

    Args:
        entity_type: The Activity domain being updated.
        old_status: The entity's status before this update. ``None`` means "no
            prior state" (entity not found — the write then fails with
            not-found) and is treated as "not completed". Callers propagate
            read *errors* instead of passing ``None`` for them: a failed read
            must never be mistaken for "not completed" (re-dating risk).
        changes: The materialized update patch (``intent.to_changes()``). Never
            mutated.

    Returns:
        ``Result.ok`` with a patch to merge into the write — ``{field: stamp}``
        on a transition into COMPLETED, ``{field: None}`` on a transition out
        (the null clears the node property), ``{}`` otherwise — or
        ``Result.fail`` (validation) when the intended status is not a
        canonical ``EntityStatus`` value or is not valid for this entity type.
    """
    if "status" not in changes:
        return Result.ok({})

    raw_status = changes["status"]
    new_status = _coerce_status(raw_status)
    if new_status is None:
        return Result.fail(
            Errors.validation(
                message=f"Invalid status value: {raw_status!r}",
                field="status",
                value=raw_status,
            )
        )
    if new_status not in entity_type.valid_statuses():
        allowed = ", ".join(sorted(s.value for s in entity_type.valid_statuses()))
        return Result.fail(
            Errors.validation(
                message=(
                    f"Status '{new_status.value}' is not valid for "
                    f"{entity_type.value} (allowed: {allowed})"
                ),
                field="status",
                value=new_status.value,
            )
        )

    spec = _STAMP_SPECS.get(entity_type)
    if spec is None:
        return Result.ok({})
    field_name, stamp_factory = spec

    if field_name in changes:
        # Explicit complete/reopen paths keep authority over their own stamp.
        return Result.ok({})

    old = _coerce_status(old_status)
    if new_status is EntityStatus.COMPLETED and old is not EntityStatus.COMPLETED:
        return Result.ok({field_name: stamp_factory()})
    if old is EntityStatus.COMPLETED and new_status is not EntityStatus.COMPLETED:
        return Result.ok({field_name: None})
    return Result.ok({})
