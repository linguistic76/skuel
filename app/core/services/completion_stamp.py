"""
Completion stamping — the shared status-transition helper for Activity updates.
==============================================================================

Every intent-based Activity update funnels through one per-domain core method
(``update_task`` … ``update_principle``). Each of those six chokepoints applies the
rules here at its write — the five stamping domains (Task, Goal, Habit, Event, Choice)
as a write-time guard (:func:`status_transition_guard`), Principle still via
:func:`completion_transition_patch`, for its legality check alone — so that:

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
caller-supplied date (``complete_goal(achieved_date=…)``) sets its own stamp and
nothing is injected. Default-dated ``complete_goal`` carries no field and defers
to the gate here, so a retried complete never re-dates. The explicit-complete
flows do the same: ``complete_task_with_cascade`` stopped stamping for itself
when it moved onto the guard (ADR-087 PR-2), so its repeat-complete protection is
the write's condition rather than a date it computed from a prior read.

Bypass paths are handled elsewhere by design: ingestion never auto-stamps (the
file is the source of truth for its own dates), and the DSL ``[x]`` create door
parses the obsidian-tasks ``✅ date`` into ``completion_date`` at conversion.

**Why every ``changes`` parameter below is ``Mapping[str, Any]``** (the ``# boundary:``
each one carries, stated once here rather than five times): ``changes`` is a materialized
update patch — an Activity ``*UpdateIntent.to_changes()`` — and it is genuinely
heterogeneous. It is specifically NOT ``Neo4jProperties``: ``GoalUpdateIntent.milestones``
is a ``list[dict[str, Any]]`` and ``.metadata`` a bare ``dict``, neither of which is a
``Neo4jValue``, so naming that type would claim a contract the callers do not meet.
Nothing here reads an arbitrary value out of it: ``status`` is read and immediately
narrowed by :func:`_coerce_status`, and every other use is a key-membership test.

**Two forms of the same rules, during the ADR-087 migration.**
:func:`completion_transition_patch` decides the patch in Python from a status the
caller read *before* the write; :func:`status_transition_guard` packages the same
decision as a :class:`StatusWriteGuard` the write statement evaluates against the
prior it reads *under the node's write-lock*, which is what makes the verdict exact
when two writers race. Both enforce the same legality check and the same authority
rule, and each chokepoint uses exactly one of them at any time. Every stamping domain
is now on the guard; the Python-side form survives only for Principle's legality check
and for the goal-progress writers PR-4 migrates, and retires with them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from types import MappingProxyType
from typing import Any

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.update_contracts import StatusWriteGuard
from core.utils.result_simplified import Errors, Result

__all__ = [
    "COMPLETION_FIELDS",
    "completion_transition_patch",
    "is_completion_transition",
    "is_reopen_transition",
    "status_transition_guard",
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
    old_status: EntityStatus | str | None,
    # boundary: a materialized update patch (see the module note) — only ``status``'s
    # VALUE is read, and ``_coerce_status`` narrows it; every other use is a key test.
    changes: Mapping[str, Any],
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


def is_reopen_transition(
    old_status: EntityStatus | str | None,
    # boundary: a materialized update patch (see the module note) — only ``status``'s
    # VALUE is read, and ``_coerce_status`` narrows it; every other use is a key test.
    changes: Mapping[str, Any],
) -> bool:
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


def _stamp_target(
    entity_type: EntityType,
    # boundary: a materialized update patch (see the module note) — only ``status``'s
    # VALUE is read, and ``_coerce_status`` narrows it; every other use is a key test.
    changes: Mapping[str, Any],
) -> Result[tuple[EntityStatus, str, Callable[[], date | datetime]] | None]:
    """Validate the status target and resolve the stamp spec this update would use.

    The shared front half of :func:`completion_transition_patch` and
    :func:`status_transition_guard`, so the legality check and the authority rule
    cannot drift between the read-then-write form and the write-time form.

    Returns:
        ``Result.ok(None)`` when nothing should be stamped — no status key, a domain
        with no completion field (Principle), or an update that already carries the
        field and therefore keeps authority over its own stamp. ``Result.ok((target,
        field, factory))` otherwise. ``Result.fail`` (validation) when the intended
        status is not a canonical ``EntityStatus`` or is not valid for this type.
    """
    if "status" not in changes:
        return Result.ok(None)

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
        return Result.ok(None)
    field_name, stamp_factory = spec
    if field_name in changes:
        # Explicit complete/reopen paths keep authority over their own stamp.
        return Result.ok(None)
    return Result.ok((new_status, field_name, stamp_factory))


def status_transition_guard(
    entity_type: EntityType,
    # boundary: a materialized update patch (see the module note) — only ``status``'s
    # VALUE is read, and ``_coerce_status`` narrows it; every other use is a key test.
    changes: Mapping[str, Any],
) -> Result[StatusWriteGuard]:
    """Package this update's completion-stamp rules as a write-time guard (ADR-087).

    The write-time successor of :func:`completion_transition_patch`. It enforces the
    same legality check and the same authority rule, but because the prior status is
    unknown until the write takes the node's lock it cannot choose a patch — it states
    the condition under which each patch applies and lets the write statement pick at
    most one:

    - target ``COMPLETED`` → stamp the field unless the prior was already
      ``COMPLETED`` (so a re-post never re-dates);
    - any other valid target → clear the field if the prior WAS ``COMPLETED``
      (the reopen);
    - no status key, a domain with no completion field, or an update that supplies
      the field itself → a guard with no patches (an ordinary write that still
      returns its prior).

    Only the caller knows the target, so the guard never needs to tell the backend
    what ``completed`` means — every condition is set-membership of the prior.

    Args:
        entity_type: The Activity domain being updated.
        changes: The materialized update patch (``intent.to_changes()``). Never mutated.

    Returns:
        ``Result.ok`` with the guard, or ``Result.fail`` (validation) on an illegal
        status target — the same refusal :func:`completion_transition_patch` makes.
    """
    target = _stamp_target(entity_type, changes)
    if target.is_error:
        return Result.fail(target)
    if target.value is None:
        return Result.ok(StatusWriteGuard())

    new_status, field_name, stamp_factory = target.value
    completed = frozenset({EntityStatus.COMPLETED.value})
    if new_status is EntityStatus.COMPLETED:
        return Result.ok(
            StatusWriteGuard(patch_if_prior_not_in=(completed, {field_name: stamp_factory()}))
        )
    return Result.ok(StatusWriteGuard(patch_if_prior_in=(completed, {field_name: None})))


def completion_transition_patch(
    entity_type: EntityType,
    old_status: EntityStatus | str | None,
    # boundary: a materialized update patch (see the module note) — only ``status``'s
    # VALUE is read, and ``_coerce_status`` narrows it; every other use is a key test.
    changes: Mapping[str, Any],
) -> Result[dict[str, Any]]:
    """Validate the status target and derive the completion-stamp patch.

    ⚠ **Being retired (ADR-087).** This is the read-then-write form: it needs a prior
    the caller read *before* the write, outside any lock, so two concurrent writers can
    both act on the same status. :func:`status_transition_guard` is the successor. Every
    Activity update chokepoint has moved (PR-1 ``update_task``; PR-2
    ``complete_task_with_cascade``, ``_trigger_task``, ``complete_tasks_bulk``; PR-3
    ``update_goal`` / ``update_event`` / ``update_choice`` / ``update_habit``). ONE
    caller remains:

    - ``update_principle`` — which calls this for the **legality check alone** (Principle
      has no ``_STAMP_SPECS`` entry, so the patch is always empty) and is deliberately
      NOT migrating: its gate is target-only and prior-independent, so there is no race
      to close. PR-4 must give it a legality-only successor — :func:`_stamp_target` is
      already that shape — before deleting this function.

    PR-4 also migrates the four ``goals_progress_service`` writers, which today decide
    completion from a pre-read and then blind-write; they never called this function, so
    they do not appear above.

    Each site holds exactly ONE path at any moment. Do not add a caller. Both forms
    share :func:`_stamp_target`, so the rules cannot drift meanwhile.

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
    target = _stamp_target(entity_type, changes)
    if target.is_error:
        return Result.fail(target)
    if target.value is None:
        return Result.ok({})

    new_status, field_name, stamp_factory = target.value
    old = _coerce_status(old_status)
    if new_status is EntityStatus.COMPLETED and old is not EntityStatus.COMPLETED:
        return Result.ok({field_name: stamp_factory()})
    if old is EntityStatus.COMPLETED and new_status is not EntityStatus.COMPLETED:
        return Result.ok({field_name: None})
    return Result.ok({})
