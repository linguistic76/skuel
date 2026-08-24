"""``status_transition_guard`` — the write-time form of the completion-stamp rules.

The Python-side ``completion_transition_patch`` picks ONE patch using a prior the
caller read before the write. The guard cannot: the prior is unknown until the write
takes the node's lock. So it states the CONDITION under which each patch applies and
lets the write choose (ADR-087).

Two things must hold, and this file pins both:

1. **The two forms agree.** Same legality refusals, same authority rule, and for every
   (prior, target) pair the guard's condition selects exactly the patch the Python-side
   helper would have returned. Swept over the whole status matrix, so a new
   ``EntityStatus`` member cannot split them apart unnoticed.
2. **``is_repeat`` is exact by construction.** With the prior coming back from the
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
    completion_transition_patch,
    is_completion_transition,
    is_reopen_transition,
    status_transition_guard,
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

    def test_a_status_illegal_for_the_type_is_refused(self) -> None:
        """``completed`` is not a valid Principle status — enforcement, not documentation."""
        guard = status_transition_guard(EntityType.PRINCIPLE, {"status": "completed"})
        assert guard.is_error
        assert "not valid for principle" in guard.expect_error().message


# ---------------------------------------------------------------------------
# 2. The two forms agree, across the whole matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entity_type", _STAMPING_TYPES)
def test_the_guard_selects_what_the_python_helper_would_have_returned(
    entity_type: EntityType,
) -> None:
    """Swept over every legal (prior, target) pair for every stamping domain.

    The stamp VALUE is generated at build time in both forms, so compare which FIELD
    is written and whether it is a clear — that is the whole semantic difference.
    """
    legal = sorted(s.value for s in entity_type.valid_statuses())
    field = COMPLETION_FIELDS[entity_type]

    for prior in [*legal, None]:
        for target in legal:
            changes = {"status": target}
            guard = status_transition_guard(entity_type, changes)
            patch = completion_transition_patch(entity_type, prior, changes)
            assert guard.is_ok and patch.is_ok

            selected = _select(guard.value, prior)
            assert (field in selected) is (field in patch.value), (prior, target)
            if field in selected:
                assert (selected[field] is None) is (patch.value[field] is None)


@pytest.mark.parametrize("entity_type", _STAMPING_TYPES)
def test_both_forms_refuse_the_same_targets(entity_type: EntityType) -> None:
    illegal = [
        *sorted(s.value for s in EntityStatus if s not in entity_type.valid_statuses()),
        "not-a-status",
    ]
    for target in illegal:
        changes = {"status": target}
        assert status_transition_guard(entity_type, changes).is_error
        assert completion_transition_patch(entity_type, None, changes).is_error


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
