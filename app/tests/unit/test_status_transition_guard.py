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
3. **``is_repeat`` is exact by construction.** With the prior coming back from the
   write, ``is_repeat = not is_completion_transition(prior, changes)`` — no second
   definition of what completing means, anywhere.

That the DATABASE honours the conditions (and that concurrent writers cannot both see
the same prior) is a different claim, pinned against a real Neo4j in
``tests/integration/test_status_guarded_update.py``.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.update_contracts import StatusWriteGuard
from core.services.completion_stamp import (
    COMPLETION_FIELDS,
    is_completion_transition,
    is_reopen_transition,
    status_transition_guard,
    validate_status_target,
)

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

    def test_the_authority_rule_holds_on_the_reopen_direction_too(self) -> None:
        """A caller that supplies the field while REOPENING keeps it just the same —
        otherwise the clear would silently discard a date the caller meant to write."""
        guard = status_transition_guard(
            EntityType.TASK, {"status": "active", "completion_date": date(2026, 1, 1)}
        )
        assert guard.is_ok
        assert guard.value.has_patches() is False

    def test_a_domain_with_no_completion_field_gets_no_patches(self) -> None:
        """Principle records no completion moment — and cannot be completed at all."""
        guard = status_transition_guard(EntityType.PRINCIPLE, {"status": "active"})
        assert guard.is_ok
        assert guard.value.has_patches() is False

    def test_the_guard_never_refuses_a_write_on_its_own(self) -> None:
        """Refusal is a caller's knob (the terminal gate), never the stamp rules'."""
        for changes in ({"status": "completed"}, {"status": "active"}, {"title": "x"}):
            guard = status_transition_guard(EntityType.TASK, changes)
            assert guard.value.refuse_if_prior_in == frozenset()

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

    def test_is_repeat_is_the_exact_complement_of_the_transition(self) -> None:
        """``is_repeat = not is_completion_transition(prior, changes)`` — with the
        prior coming back from the write, that identity holds by construction rather
        than by whatever a pre-read happened to observe.
        """
        changes = {"status": "completed"}
        for prior in [*sorted(s.value for s in EntityType.TASK.valid_statuses()), None]:
            is_transition = is_completion_transition(prior, changes)
            is_repeat = not is_transition
            assert is_repeat is (prior == EntityStatus.COMPLETED.value)

    def test_a_write_that_touched_no_status_is_neither(self) -> None:
        for prior in ("active", "completed", None):
            assert is_completion_transition(prior, {"title": "x"}) is False
            assert is_reopen_transition(prior, {"title": "x"}) is False
