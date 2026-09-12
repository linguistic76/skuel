"""``status_transition_guard`` — the completion-stamp rules as conditions of the write.

The prior status is unknown until the write takes the node's lock, so the guard cannot
pick a patch: it states the CONDITION under which each patch applies and lets the write
choose (ADR-087). Its read-then-write predecessor, ``completion_transition_patch``,
picked one patch from a status the caller read beforehand and was deleted when its last
caller left (PR-4) — which is why the sweep below no longer compares two forms.

Three things must hold, and this file pins all three:

1. **The guard's conditions mean what the domain's verdict helpers mean.** For every
   (prior, target) pair, the patch the guard selects is a stamp exactly when
   ``is_completion_transition`` says so and a clear exactly when ``is_reopen_transition``
   says so. That is the agreement that matters now: the write and the event it triggers
   must not be able to disagree about what completing is. Swept over the whole status
   matrix, so a new ``EntityStatus`` member cannot split them apart unnoticed.
2. **The legality check is one rule with two entry points.** ``status_transition_guard``
   (the five stamping domains) and ``validate_status_target`` (Principle, which has
   nothing to stamp) refuse exactly the same targets.
3. **A re-post is silent by construction.** With the prior coming back from the
   write, ``is_completion_transition(prior, changes)`` is false for a re-posted
   ``completed`` — no second definition of what completing means, anywhere.

That the DATABASE honours the conditions (and that concurrent writers cannot both see
the same prior) is a different claim, pinned against a real Neo4j in
``tests/integration/test_status_guarded_update.py``.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from core.models.choice.choice_request import ChoiceUpdateRequest
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.update_contracts import StatusWriteGuard
from core.services.completion_stamp import (
    COMPLETION_FIELDS,
    is_completion_transition,
    is_reopen_transition,
    status_transition_guard,
    stranded_stamp_error,
    validate_status_target,
)
from core.utils.result_simplified import ErrorCategory

_COMPLETED = frozenset({EntityStatus.COMPLETED.value})
_STAMPING_TYPES = sorted(COMPLETION_FIELDS, key=lambda t: t.value)


def _select(guard: StatusWriteGuard, prior: str | None) -> dict:
    """Resolve the guard against a prior, exactly as the Cypher's CASE merges do."""
    key = prior or ""
    merged: dict = {}
    if guard.patch_if_prior_in is not None:
        statuses, patch = guard.patch_if_prior_in
        if key in statuses:
            merged.update(patch)
    if guard.patch_if_prior_not_in is not None:
        statuses, patch = guard.patch_if_prior_not_in
        if key not in statuses:
            merged.update(patch)
    return merged


# ---------------------------------------------------------------------------
# 1. The builder matrix
# ---------------------------------------------------------------------------


class TestGuardBuilder:
    def test_a_completion_target_offers_the_stamp_conditionally(self) -> None:
        guard = status_transition_guard(EntityType.TASK, {"status": "completed"})
        assert guard.is_ok
        assert guard.value.patch_if_prior_in is None
        statuses, patch = guard.value.patch_if_prior_not_in
        assert statuses == _COMPLETED
        assert patch == {"completion_date": date.today()}

    def test_a_valid_non_completion_target_offers_the_clear_conditionally(self) -> None:
        guard = status_transition_guard(EntityType.TASK, {"status": "active"})
        assert guard.is_ok
        assert guard.value.patch_if_prior_not_in is None
        statuses, patch = guard.value.patch_if_prior_in
        assert statuses == _COMPLETED
        assert patch == {"completion_date": None}

    def test_no_status_key_means_no_patches(self) -> None:
        guard = status_transition_guard(EntityType.TASK, {"title": "renamed"})
        assert guard.is_ok
        assert guard.value.has_patches() is False

    def test_a_caller_supplied_stamp_disables_the_patches(self) -> None:
        """The authority rule: an explicit complete flow sets its own date."""
        guard = status_transition_guard(
            EntityType.TASK, {"status": "completed", "completion_date": date(2026, 1, 1)}
        )
        assert guard.is_ok
        assert guard.value.has_patches() is False

    def test_a_non_null_stamp_while_reopening_is_refused(self) -> None:
        """The invariant: the stamp is non-null exactly when the entity is completed.

        The authority rule stands the guard down on any patch carrying the stamp
        field, so this pair would otherwise take the reopen without its clear and
        leave the entity in ``active`` still stamped — the stranded stamp the vault
        door's ``clear_completion_stamps`` exists to undo, which reads to every
        consumer as an entity that is still done.

        See: ``docs/decisions/ADR-087-status-guarded-conditional-writes.md``
        """
        guard = status_transition_guard(
            EntityType.TASK, {"status": "active", "completion_date": date(2026, 1, 1)}
        )
        assert guard.is_error
        assert "requires status=completed" in guard.expect_error().message

    def test_a_stamp_with_no_status_named_is_not_refused_here(self) -> None:
        """A patch carrying a stamp and no status resolves against the PRIOR.

        Nothing at THIS layer can judge it, so the plain refusal does not fire: the
        resulting status is whatever the node already holds. Demanding the status
        instead would demand one the caller may have no way to send —
        ``ChoiceUpdateRequest`` exposes ``completed_at`` and no status field at all.
        The claim is judged by the write instead, as the prior it requires
        (``TestTheBareStampGate`` below).
        """
        guard = status_transition_guard(EntityType.TASK, {"completion_date": date(2026, 1, 1)})
        assert guard.is_ok

    def test_a_choice_may_correct_its_own_timestamp(self) -> None:
        """The shape ``ChoiceUpdateRequest`` can actually express, kept working.

        Its update request carries ``completed_at`` and no ``status``; the separate
        status endpoint sends ``status`` alone. A rule demanding both in one patch
        makes the documented field unusable rather than merely strict.
        """
        guard = status_transition_guard(EntityType.CHOICE, {"completed_at": datetime(2026, 1, 1)})
        assert guard.is_ok

    def test_a_choice_reopen_carrying_a_stamp_is_still_refused(self) -> None:
        """Narrowing to patches that NAME a status keeps the actual bug closed."""
        guard = status_transition_guard(
            EntityType.CHOICE, {"status": "active", "completed_at": datetime(2026, 1, 1)}
        )
        assert guard.is_error
        assert "completed_at requires status=completed" in guard.expect_error().message

    def test_an_explicit_clear_while_reopening_still_keeps_authority(self) -> None:
        """Only a NON-NULL stamp is a completion claim. Clearing is the reopen itself,
        so a caller that writes ``None`` still keeps authority and the guard adds no
        patch of its own — the write carries the clear."""
        guard = status_transition_guard(
            EntityType.TASK, {"status": "active", "completion_date": None}
        )
        assert guard.is_ok
        assert guard.value.has_patches() is False

    def test_re_dating_a_finished_entity_stays_legal(self) -> None:
        """Re-posting ``completed`` with a corrected date is the shape the invariant
        asks for, and is not a transition — so it re-dates without firing a completion
        event. The deliberate re-date the authority rule exists to serve."""
        guard = status_transition_guard(
            EntityType.TASK, {"status": "completed", "completion_date": date(2026, 1, 1)}
        )
        assert guard.is_ok
        assert guard.value.has_patches() is False

    @pytest.mark.parametrize("entity_type", _STAMPING_TYPES)
    def test_the_invariant_holds_for_every_stamping_domain(self, entity_type: EntityType) -> None:
        """Not a Task rule. Goal, Event and Choice carry their stamp on the update
        intent too, so each could strand one the same way."""
        field = COMPLETION_FIELDS[entity_type]
        reopen_target = next(
            s.value for s in entity_type.valid_statuses() if s is not EntityStatus.COMPLETED
        )
        guard = status_transition_guard(
            entity_type, {"status": reopen_target, field: datetime(2026, 1, 1)}
        )
        assert guard.is_error
        assert f"{field} requires status=completed" in guard.expect_error().message

    def test_a_domain_with_no_completion_field_gets_no_patches(self) -> None:
        """Principle records no completion moment — and cannot be completed at all."""
        guard = status_transition_guard(EntityType.PRINCIPLE, {"status": "active"})
        assert guard.is_ok
        assert guard.value.has_patches() is False

    def test_the_guard_never_fills_the_refuse_set_on_its_own(self) -> None:
        """``refuse_if_prior_in`` is a caller's knob (the terminal gate, decision
        immutability), never the stamp rules'. The stamp rules refuse through the
        PRECONDITION gate instead, and only for a bare stamp — see the class below."""
        for changes in ({"status": "completed"}, {"status": "active"}, {"title": "x"}):
            guard = status_transition_guard(EntityType.TASK, changes)
            assert guard.value.refuse_if_prior_in == frozenset()
            assert guard.value.refuse_unless_prior_in == frozenset()

    @pytest.mark.parametrize("entity_type", _STAMPING_TYPES)
    def test_each_stamping_domain_names_its_own_field(self, entity_type: EntityType) -> None:
        guard = status_transition_guard(entity_type, {"status": "completed"})
        assert guard.is_ok
        _statuses, patch = guard.value.patch_if_prior_not_in
        assert list(patch) == [COMPLETION_FIELDS[entity_type]]
        # Task/Goal stamp a calendar date; the datetime domains stamp the moment.
        assert isinstance(next(iter(patch.values())), date | datetime)

    def test_an_unrecognized_status_is_refused(self) -> None:
        guard = status_transition_guard(EntityType.TASK, {"status": "not-a-status"})
        assert guard.is_error
        assert "Invalid status value" in guard.expect_error().message

    def test_an_explicit_null_status_is_refused(self) -> None:
        """A present ``status`` key means a target was intended; ``None`` is not one.
        Distinct from the no-key case above, which passes with no patches."""
        guard = status_transition_guard(EntityType.TASK, {"status": None})
        assert guard.is_error
        assert "Invalid status value" in guard.expect_error().message

    def test_a_status_illegal_for_the_type_is_refused(self) -> None:
        """``completed`` is not a valid Principle status — enforcement, not documentation."""
        guard = status_transition_guard(EntityType.PRINCIPLE, {"status": "completed"})
        assert guard.is_error
        assert "not valid for principle" in guard.expect_error().message


# ---------------------------------------------------------------------------
# 2. The guard agrees with the verdict helpers, across the whole matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entity_type", _STAMPING_TYPES)
def test_the_guard_stamps_exactly_when_the_verdict_helpers_say_so(
    entity_type: EntityType,
) -> None:
    """Swept over every legal (prior, target) pair for every stamping domain.

    The condition the WRITE evaluates and the condition the SERVICE evaluates to publish
    its completion event are two expressions of one rule, and they are written in two
    different places — the guard's set membership, and ``is_completion_transition`` on
    the prior the write hands back. This sweep is what makes them one rule in fact: a
    stamp lands exactly on a completion transition, a clear exactly on a reopen, and
    nothing is written on any other pair.
    """
    legal = sorted(s.value for s in entity_type.valid_statuses())
    field = COMPLETION_FIELDS[entity_type]

    for prior in [*legal, None]:
        for target in legal:
            changes = {"status": target}
            guard = status_transition_guard(entity_type, changes)
            assert guard.is_ok

            selected = _select(guard.value, prior)
            stamped = field in selected and selected[field] is not None
            cleared = field in selected and selected[field] is None

            assert stamped is is_completion_transition(prior, changes), (prior, target)
            assert cleared is is_reopen_transition(prior, changes), (prior, target)


@pytest.mark.parametrize("entity_type", _STAMPING_TYPES)
def test_the_two_legality_entry_points_refuse_the_same_targets(
    entity_type: EntityType,
) -> None:
    """One rule, two doors: the stamping domains reach it through the guard builder,
    Principle through ``validate_status_target``. They share ``_stamp_target``, and this
    is what says so — including that the legality-only door refuses nothing extra."""
    illegal = [
        *sorted(s.value for s in EntityStatus if s not in entity_type.valid_statuses()),
        "not-a-status",
    ]
    for target in illegal:
        changes = {"status": target}
        assert status_transition_guard(entity_type, changes).is_error
        assert validate_status_target(entity_type, changes).is_error

    for target in sorted(s.value for s in entity_type.valid_statuses()):
        assert validate_status_target(entity_type, {"status": target}).is_ok


class TestValidateStatusTarget:
    """The legality-only door, for the chokepoint with nothing to stamp."""

    def test_an_illegal_principle_status_is_refused(self) -> None:
        result = validate_status_target(EntityType.PRINCIPLE, {"status": "completed"})
        assert result.is_error
        assert "not valid for principle" in result.expect_error().message

    def test_an_unrecognized_status_is_refused(self) -> None:
        result = validate_status_target(EntityType.PRINCIPLE, {"status": "not-a-status"})
        assert result.is_error
        assert "Invalid status value" in result.expect_error().message

    def test_a_legal_principle_status_passes(self) -> None:
        assert validate_status_target(EntityType.PRINCIPLE, {"status": "active"}).is_ok

    def test_an_update_with_no_status_key_passes(self) -> None:
        """There is no target to judge — a title edit is not a status change."""
        assert validate_status_target(EntityType.PRINCIPLE, {"title": "renamed"}).is_ok

    def test_it_does_not_carry_the_stranded_stamp_refusal(self) -> None:
        """Legality only — the invariant is the GUARD's, and must not leak here.

        This door's callers ask one question: is this status legal for this type.
        The ingestion validator is one of them, and a vault file carrying a stale
        ``completion_date:`` beside an open status must be ingested and CLEANED (the
        vault door clears the stamp after the write), never refused — refusing it
        rejects a file over a line the door exists to tidy up. Sharing
        ``_stamp_target`` makes that leak a one-line accident, so it is pinned.
        """
        changes = {"status": "active", "completion_date": date(2026, 1, 1)}
        assert validate_status_target(EntityType.TASK, changes).is_ok
        assert status_transition_guard(EntityType.TASK, changes).is_error

    def test_it_carries_no_stamp_for_a_stamping_domain_either(self) -> None:
        """It answers legality and nothing else — the caller that wants a stamp asks
        ``status_transition_guard``. A Task completion passing here writes no date."""
        assert validate_status_target(EntityType.TASK, {"status": "completed"}).value is None


# ---------------------------------------------------------------------------
# 3. The verdicts derived from a returned prior
# ---------------------------------------------------------------------------


class TestVerdictsFromTheReturnedPrior:
    """The service reads ``outcome.prior_status`` into the same two pure helpers it
    always called. Only the argument became exact — so pin the table."""

    @pytest.mark.parametrize(
        ("prior", "target", "transition", "reopen"),
        [
            ("active", "completed", True, False),
            ("completed", "completed", False, False),  # a repeat
            ("completed", "active", False, True),
            ("active", "paused", False, False),  # lateral
            ("paused", "completed", True, False),
            (None, "completed", True, False),  # status property absent
            (None, "active", False, False),
        ],
    )
    def test_the_verdict_table(
        self, prior: str | None, target: str, transition: bool, reopen: bool
    ) -> None:
        changes = {"status": target}
        assert is_completion_transition(prior, changes) is transition
        assert is_reopen_transition(prior, changes) is reopen
        # The two gates are mutually exclusive — one write is never both.
        assert not (transition and reopen)

    def test_a_write_that_touched_no_status_is_neither(self) -> None:
        for prior in ("active", "completed", None):
            assert is_completion_transition(prior, {"title": "x"}) is False
            assert is_reopen_transition(prior, {"title": "x"}) is False


class TestTheBareStampGate:
    """A patch that carries a completion stamp and names NO status.

    It resolves against whatever status the node already holds, so it cannot be judged
    from the patch — the claim "this entity is completed" travels to the write as the
    prior it REQUIRES, and comes back as ``applied=False``. A refusal, not a silent
    clear, because here the stamp IS the caller's edit.

    Case file: ``docs/roadmap/done/stranded-completion-stamp.md``.
    """

    @pytest.mark.parametrize("entity_type", _STAMPING_TYPES)
    def test_a_bare_stamp_demands_a_completed_prior(self, entity_type: EntityType) -> None:
        field = COMPLETION_FIELDS[entity_type]
        guard = status_transition_guard(entity_type, {field: datetime(2026, 3, 4)})

        assert guard.is_ok
        assert guard.value.refuse_unless_prior_in == _COMPLETED
        # Stated as a precondition, not an enumerated complement: an entity carrying no
        # status property at all is outside the requirement and refused with the rest.
        assert guard.value.refuse_if_prior_in == frozenset()
        assert guard.value.has_patches() is False

    @pytest.mark.parametrize("entity_type", _STAMPING_TYPES)
    def test_clearing_the_stamp_demands_nothing(self, entity_type: EntityType) -> None:
        """``None`` is the reopen's own clear, not a claim that anything completed."""
        guard = status_transition_guard(entity_type, {COMPLETION_FIELDS[entity_type]: None})

        assert guard.is_ok
        assert guard.value.refuse_unless_prior_in == frozenset()

    def test_a_stamp_that_names_completed_demands_nothing(self) -> None:
        """The deliberate re-date the authority rule serves: the patch says what status
        it means, so nothing is left for the write to decide."""
        guard = status_transition_guard(
            EntityType.TASK, {"status": "completed", "completion_date": date(2026, 3, 4)}
        )

        assert guard.is_ok
        assert guard.value.refuse_unless_prior_in == frozenset()

    def test_a_patch_carrying_no_stamp_demands_nothing(self) -> None:
        for changes in ({"title": "x"}, {"due_date": date(2026, 3, 4)}, {}):
            guard = status_transition_guard(EntityType.TASK, changes)
            assert guard.value.refuse_unless_prior_in == frozenset(), changes

    def test_a_foreign_field_is_not_this_domains_stamp(self) -> None:
        """The gate reads the domain's OWN field (``COMPLETION_FIELDS``) — a Task's key
        on a Habit patch is an ordinary property, not a completion claim."""
        guard = status_transition_guard(EntityType.HABIT, {"completion_date": datetime.now()})

        assert guard.value.refuse_unless_prior_in == frozenset()

    def test_principle_has_no_stamp_to_gate(self) -> None:
        guard = status_transition_guard(EntityType.PRINCIPLE, {"completed_at": datetime.now()})

        assert guard.is_ok
        assert guard.value.refuse_unless_prior_in == frozenset()


class TestTheRefusalMessage:
    """What the chokepoint says when the write comes back refused."""

    @pytest.mark.parametrize("entity_type", _STAMPING_TYPES)
    def test_it_names_the_field_the_domain_the_prior_and_both_remedies(
        self, entity_type: EntityType
    ) -> None:
        error = stranded_stamp_error(entity_type, "active")

        assert COMPLETION_FIELDS[entity_type] in error.message
        assert entity_type.value in error.message
        assert "'active'" in error.message
        assert error.details["field"] == COMPLETION_FIELDS[entity_type]
        assert error.details["value"] == "active"
        assert error.category is ErrorCategory.VALIDATION

    def test_an_absent_status_reads_as_one(self) -> None:
        """A vault file can erase the property; the message must not say "is 'None'"."""
        error = stranded_stamp_error(EntityType.TASK, None)

        assert "has no status" in error.message
        assert "None" not in error.message

    def test_the_remedy_is_reachable_from_a_door_with_no_status_field(self) -> None:
        """``ChoiceUpdateRequest`` exposes ``completed_at`` and NO status, so a message
        whose only remedy was "send status in the same update" would instruct that door
        to do something it cannot. The two-call route has to be named as well."""
        assert "status" not in ChoiceUpdateRequest.model_fields
        assert "completed_at" in ChoiceUpdateRequest.model_fields

        message = stranded_stamp_error(EntityType.CHOICE, "active").message

        assert "Complete it first" in message
