"""
Completion stamping — the shared status-transition helper for Activity updates.
==============================================================================

Every intent-based Activity update funnels through one per-domain core method
(``update_task`` … ``update_principle``). Each of those six chokepoints applies the
rules here at its write — the five stamping domains (Task, Goal, Habit, Event, Choice)
through a write-time guard (:func:`status_transition_guard`), Principle through
:func:`validate_status_target`, having nothing to stamp — so that:

1. **The status target is legal for the type** — ``EntityType.valid_statuses()``
   is enforced at the seam instead of being documentation (e.g. a Principle can
   never be written ``completed``).
2. **Transitions INTO ``COMPLETED`` stamp the domain's canonical completion
   field** (Task ``completion_date``, Goal ``achieved_date``, Habit / Event /
   Choice ``completed_at``) so the completion moment stops being approximated by
   the mutable ``updated_at``.
3. **Transitions OUT of ``COMPLETED`` clear that field** (reopen) — the stamp is
   non-null exactly when the entity is completed.
4. **A patch that would strand a stamp is refused**, in both of the shapes that
   can produce one: naming a status other than ``COMPLETED`` alongside a non-null
   stamp is contradictory on its face (:func:`_refuse_stranded_stamp`), and naming
   NO status makes the same claim against a prior only the write can see, so it
   travels as the prior the write requires (:func:`_bare_stamp_gate`) and comes
   back as ``applied=False`` for the chokepoint to voice
   (:func:`stranded_stamp_error`).

The gate is the *transition*, not the presence of the status key: re-posting
``status=completed`` on an already-completed entity must not re-date it. An
update that already carries the domain's completion field keeps authority — a
caller-supplied date (``complete_goal(achieved_date=…)``) sets its own stamp and
nothing is injected. Default-dated ``complete_goal`` carries no field and defers
to the gate here, so a retried complete never re-dates. The explicit-complete
flows do the same: ``complete_task_with_cascade`` carries no stamp of its own, so
its repeat-complete protection is the write's condition.

Bypass paths are handled elsewhere by design: ingestion never auto-stamps (the
file is the source of truth for its own dates), and the DSL ``[x]`` create door
parses the obsidian-tasks ``✅ date`` into ``completion_date`` at conversion.
The ingest doors do owe the other two rules, and honour them without the guard:
they ``MERGE`` in bulk, so ``core.services.ingestion.status_transitions``
reassembles the transition verdicts from the prior status the upsert returns —
same rules (:data:`COMPLETION_FIELDS` is the shared mapping), a different write
primitive.

**Why every ``changes`` parameter below is ``Mapping[str, Any]``** (the ``# boundary:``
each one carries, stated once here rather than five times): ``changes`` is a materialized
update patch — an Activity ``*UpdateIntent.to_changes()`` — and it is genuinely
heterogeneous. It is specifically NOT ``Neo4jProperties``: ``GoalUpdateIntent.milestones``
is a ``list[dict[str, Any]]`` and ``.metadata`` a bare ``dict``, neither of which is a
``Neo4jValue``, so naming that type would claim a contract the callers do not meet.
Nothing here reads an arbitrary value out of it: ``status`` is read and immediately
narrowed by :func:`_coerce_status`, and every other use is a key-membership test.

**The rules are conditions of the write, not decisions taken before it (ADR-087).**
:func:`status_transition_guard` packages them as a :class:`StatusWriteGuard` the write
statement evaluates against the prior status it reads *under the node's write-lock*,
and returns that prior so the caller derives its transition verdicts
(:func:`is_completion_transition` / :func:`is_reopen_transition`) from the same status
the stamp was decided on. A status read before the write is stale by the time it is
written, which is why the rules travel to the write as a guard and every verdict is
derived from the prior the write returns.

The goal-progress writers in ``GoalsProgressService`` build their achievement patch
themselves (they derive completion from a progress recompute, not from a status target
a caller supplied), but they express it the same way — a ``patch_if_prior_not_in``
whose verdict comes back from the write.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from types import MappingProxyType
from typing import Any

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.update_contracts import StatusWriteGuard
from core.utils.result_simplified import ErrorContext, Errors, Result

__all__ = [
    "COMPLETION_FIELDS",
    "completion_moment",
    "is_completion_transition",
    "is_reopen_transition",
    "stranded_stamp_error",
    "status_transition_guard",
    "validate_status_target",
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


def completion_moment(stamp: date | datetime | None) -> datetime:
    """Widen a domain completion stamp into the ``datetime`` an event's ``occurred_at`` wants.

    The born-completed create doors publish their completion event with the moment
    the entity says it was completed, not the moment it was ingested, so a vault
    ``- [x] … ✅ 2026-03-04`` line reports March 4th. Task and Goal stamp a ``date``
    (``completion_date`` / ``achieved_date``) while ``BaseEvent.occurred_at`` is a
    ``datetime``, so the widening has to be explicit — ``datetime`` is checked first
    because it is a subclass of ``date``.

    An absent stamp falls back to now, which is exactly what ``BaseEvent`` would have
    defaulted to.
    """
    if isinstance(stamp, datetime):
        return stamp
    if isinstance(stamp, date):
        return datetime.combine(stamp, datetime.min.time())
    return datetime.now()


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
    exactly with the guard's stamp-clearing patch
    (:func:`status_transition_guard`'s ``patch_if_prior_in``), including the
    requirement that the *new* status be a canonical ``EntityStatus`` value — an
    unrecognized status is a validation failure there, never a reopen here.

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

    The shared front half of :func:`status_transition_guard` and
    :func:`validate_status_target`, so the legality check cannot drift between the
    domains that stamp and the one that only validates.

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


def _refuse_stranded_stamp(
    entity_type: EntityType,
    # boundary: a materialized update patch (see the module note) — only ``status``'s
    # VALUE is read, and ``_coerce_status`` narrows it; every other use is a key test.
    changes: Mapping[str, Any],
) -> Result[None]:
    """Refuse a patch that sets a completion stamp while naming a status that is not
    ``COMPLETED``.

    The stamp's invariant is "non-null exactly when the entity is completed", so a
    non-null stamp is a claim that the entity IS completed. A patch that makes that
    claim while naming any other status contradicts itself, and the authority rule in
    :func:`_stamp_target` would otherwise stand the guard fully down on it — no stamp,
    and no reopen clear either — leaving the entity open and still stamped, which reads
    to every consumer as done and is what the vault door's ``clear_completion_stamps``
    exists to undo.

    Scoped to a patch that NAMES its status, which is the whole of what can be judged
    here: the resulting status is then known without reading the node, so this is a
    plain refusal rather than a guard condition. A patch carrying a stamp and NO status
    makes the same claim against a prior only the write can see, and is refused there
    instead (:func:`_bare_stamp_gate`). Requiring the status here would not have reached
    it either, and would have been unsatisfiable for Choice, whose update request exposes
    ``completed_at`` and no status at all — which is why the sibling gate demands the
    PRIOR rather than the patch.

    Two shapes stay legal, and both are the point: clearing (``None``) is the reopen
    rather than a completion claim, and re-posting ``completed`` alongside a corrected
    date re-dates a finished entity without firing a completion event (a re-post is not
    a transition).

    **Deliberately not part of :func:`_stamp_target`.** That shared front half also
    serves :func:`validate_status_target`, whose callers ask only "is this status legal
    for this type" — including the ingestion validator, where a file carrying a stale
    ``completion_date:`` beside an open status must be INGESTED AND CLEANED (the vault
    door clears the stamp after the write), never refused.
    """
    spec = _STAMP_SPECS.get(entity_type)
    if spec is None:
        return Result.ok(None)
    field_name, _stamp_factory = spec
    if changes.get(field_name) is None:
        return Result.ok(None)
    if "status" not in changes:
        return Result.ok(None)
    if _coerce_status(changes["status"]) is EntityStatus.COMPLETED:
        return Result.ok(None)
    return Result.fail(
        Errors.validation(
            message=(
                f"{field_name} requires status={EntityStatus.COMPLETED.value} in the same update"
            ),
            field=field_name,
            value=changes[field_name],
        )
    )


def _bare_stamp_gate(
    entity_type: EntityType,
    # boundary: a materialized update patch (see the module note) — only ``status``'s
    # VALUE is read, and ``_coerce_status`` narrows it; every other use is a key test.
    changes: Mapping[str, Any],
) -> frozenset[str]:
    """The prior this patch's completion stamp requires, when it names no status.

    The mirror of :func:`_refuse_stranded_stamp` for the half that cannot be judged from
    the patch: ``{"completion_date": …}`` with no ``status`` resolves against whatever
    status the node already holds, so on an open entity it strands a stamp that reads to
    every consumer as done. What the patch DOES say is that the entity is completed —
    so the write demands exactly that prior, and refuses anything else.

    Stated as a precondition (``refuse_unless_prior_in``) rather than an enumerated
    complement: a node whose ``status`` property was erased — which a vault file can do —
    is not "in" any enumeration of open statuses, and the complement would go stale the
    day an ``EntityStatus`` member is added.

    Returns an EMPTY set — demanding nothing — for every other shape:

    - a patch that names a status is judged without reading the node
      (:func:`_refuse_stranded_stamp` refuses it, or it legitimately completes);
    - a patch that clears the stamp (``None``) makes no completion claim;
    - a domain with no completion field (Principle) has no stamp to strand.

    Why a refusal and not a silent clear: here the stamp IS the caller's edit. Dropping
    it would discard the only field they sent and answer 200. ADR-087 holds the record.
    """
    spec = _STAMP_SPECS.get(entity_type)
    if spec is None:
        return frozenset()
    field_name, _stamp_factory = spec
    if changes.get(field_name) is None or "status" in changes:
        return frozenset()
    return frozenset({EntityStatus.COMPLETED.value})


def stranded_stamp_error(
    entity_type: EntityType,
    prior_status: str | None,
) -> ErrorContext:
    """The message a chokepoint gives back when the bare-stamp gate refused its write.

    The refusal is an *outcome* of the write (``applied=False``), read off the prior the
    statement captured under the node's lock — so the message can name the status that
    actually refused it rather than one read beforehand. Sourced here, once, so all five
    stamping chokepoints say the same thing.

    **The remedy names both routes, because no single one is open at every door.**
    ``TaskUpdateRequest`` and ``EventUpdateRequest`` carry a status and can satisfy this
    in one call; ``ChoiceUpdateRequest`` exposes ``completed_at`` and no status at all,
    so a choice is completed through its status endpoint first and dated after. A message
    naming only the same-update route would be an instruction that door cannot follow.

    Args:
        entity_type: The Activity domain whose write was refused.
        prior_status: The status the node held at write time; ``None`` when it carries
            no status property at all.
    """
    field_name = COMPLETION_FIELDS[entity_type]
    holds = f"is '{prior_status}'" if prior_status else "has no status"
    return Errors.validation(
        message=(
            f"{field_name} can only be set on a completed {entity_type.value}; "
            f"this one {holds}. Complete it first, or name "
            f"status={EntityStatus.COMPLETED.value} in the same update."
        ),
        field=field_name,
        value=prior_status,
    )


def validate_status_target(
    entity_type: EntityType,
    # boundary: a materialized update patch (see the module note) — only ``status``'s
    # VALUE is read, and ``_coerce_status`` narrows it; every other use is a key test.
    changes: Mapping[str, Any],
) -> Result[None]:
    """Refuse a status target that is not legal for this entity type.

    The legality half of the rules above, on its own, for the one Activity chokepoint
    that has nothing to stamp: ``update_principle``. Principle has no ``_STAMP_SPECS``
    entry — COMPLETED is not one of its valid statuses — so there is no completion field
    to set or clear and no prior-dependent decision to make, which is why that seam is
    deliberately NOT on the guarded write (ADR-087 § Scope). What it does still need is
    the check that a status it is handed belongs to the Principle lifecycle at all.

    An update with no ``status`` key passes: there is no target to judge.

    Args:
        entity_type: The Activity domain being updated.
        changes: The materialized update patch (``intent.to_changes()``). Never mutated.

    Returns:
        ``Result.ok(None)`` when the target is legal (or absent), ``Result.fail``
        (validation) when it is not a canonical ``EntityStatus`` value or not valid for
        this type — the same refusal :func:`status_transition_guard` makes.
    """
    target = _stamp_target(entity_type, changes)
    if target.is_error:
        return Result.fail(target)
    return Result.ok(None)


def status_transition_guard(
    entity_type: EntityType,
    # boundary: a materialized update patch (see the module note) — only ``status``'s
    # VALUE is read, and ``_coerce_status`` narrows it; every other use is a key test.
    changes: Mapping[str, Any],
) -> Result[StatusWriteGuard]:
    """Package this update's completion-stamp rules as a write-time guard (ADR-087).

    Because the prior status is unknown until the write takes the node's lock, this
    cannot choose a patch — it enforces the legality check and the authority rule, then
    states the condition under which each patch applies and lets the write statement
    pick at most one:

    - target ``COMPLETED`` → stamp the field unless the prior was already
      ``COMPLETED`` (so a re-post never re-dates);
    - any other valid target → clear the field if the prior WAS ``COMPLETED``
      (the reopen);
    - no status key, a domain with no completion field, or an update that supplies
      the field itself → a guard with no patches (an ordinary write that still
      returns its prior) — carrying, when that patch sets a bare stamp, the prior it
      demands (:func:`_bare_stamp_gate`).

    Only the caller knows the target, so the guard never needs to tell the backend
    what ``completed`` means — every condition is set-membership of the prior.

    **Both stranded-stamp shapes are refused, at the layer each is knowable.** A patch
    that sets a non-null stamp while naming a status other than ``COMPLETED`` is refused
    outright here (:func:`_refuse_stranded_stamp`) — the authority rule stands the guard
    down on any patch carrying the field, so absent that refusal the reopen clear does
    not fire and the entity keeps a completion stamp while open. A patch that sets one
    and names no status resolves against the prior, so it cannot be judged here at all:
    it becomes ``refuse_unless_prior_in={completed}`` and the write refuses it, reporting
    ``applied=False`` for the chokepoint to convert with :func:`stranded_stamp_error`.
    Both refusals are the guard's alone — :func:`validate_status_target` shares only the
    legality check.

    Args:
        entity_type: The Activity domain being updated.
        changes: The materialized update patch (``intent.to_changes()``). Never mutated.

    Returns:
        ``Result.ok`` with the guard, or ``Result.fail`` (validation) on an illegal
        status target — the same refusal :func:`validate_status_target` makes — or on
        a stranded stamp, which is this function's own.
    """
    target = _stamp_target(entity_type, changes)
    if target.is_error:
        return Result.fail(target)
    # After legality, so an illegal status is still reported as one.
    stranded = _refuse_stranded_stamp(entity_type, changes)
    if stranded.is_error:
        return Result.fail(stranded)
    if target.value is None:
        # The one branch a bare stamp can reach: no status key means no stamp target,
        # so the gate travels to the write as the prior it requires. Every other return
        # below is reached only with a status in the patch, where the gate is empty.
        return Result.ok(
            StatusWriteGuard(refuse_unless_prior_in=_bare_stamp_gate(entity_type, changes))
        )

    new_status, field_name, stamp_factory = target.value
    completed = frozenset({EntityStatus.COMPLETED.value})
    if new_status is EntityStatus.COMPLETED:
        return Result.ok(
            StatusWriteGuard(patch_if_prior_not_in=(completed, {field_name: stamp_factory()}))
        )
    return Result.ok(StatusWriteGuard(patch_if_prior_in=(completed, {field_name: None})))
