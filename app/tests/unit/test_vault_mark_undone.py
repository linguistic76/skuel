"""``apply_mark_undone`` — the reopen's vault surface (ADR-070, amended 2026-08-24).

The reverse of ``apply_mark_done``: un-check the ``🆔``-bearing line and strip
the ``✅ date`` it wrote. The round-trip must be BYTE-exact — ``apply_mark_done``
appends ``f"{stripped} ✅ {done_date}{eol}"`` with a leading space, so naive
removal of the bare done-date token leaves a trailing one behind and the line
is no longer what it was before completion. A whitespace bug there survives
every assertion that is not byte-exact, which is why the sweep below compares
whole strings and never ``startswith``/``in``.
"""

from __future__ import annotations

import pytest

from core.ports.vault_bridge_protocol import (
    TaskLineUpdate,
    apply_mark_done,
    apply_mark_undone,
    apply_task_updates,
    needs_mark_undone,
)

VAULT_ID = "sk_a1b2c3"

# Every line shape the round-trip has to survive. Each carries the 🆔 token
# somewhere, because that is the only locator the un-check has.
LINE_SHAPES = [
    pytest.param(f"- [ ] Ship the fix 🆔 {VAULT_ID}\n", id="dash-bullet-trailing-newline"),
    pytest.param(f"* [ ] Ship the fix 🆔 {VAULT_ID}\n", id="star-bullet"),
    pytest.param(f"- [ ] Ship the fix 🆔 {VAULT_ID}", id="no-trailing-newline-at-eof"),
    pytest.param(f"- [ ] Ship the fix 🆔 {VAULT_ID}   \n", id="pre-existing-trailing-spaces"),
    pytest.param(f"- [ ] Ship the fix 🆔 {VAULT_ID}\t\n", id="pre-existing-trailing-tab"),
    pytest.param(f"- [ ] 🆔 {VAULT_ID} Ship the fix 📅 2026-01-01\n", id="id-before-other-tokens"),
    pytest.param(f"- [ ] Ship 🆔 {VAULT_ID} 📅 2026-01-01 ⏫\n", id="id-among-other-tokens"),
    pytest.param(f"- [ ] Ship the fix 🆔️ {VAULT_ID}\n", id="variation-selector-on-id"),
]


@pytest.mark.parametrize("original", LINE_SHAPES)
def test_mark_done_then_mark_undone_restores_the_line_byte_for_byte(original: str) -> None:
    """THE test of this change: complete → reopen leaves the file as it was."""
    done_lines, done_changed = apply_mark_done([original], VAULT_ID, "2026-08-20")
    assert done_changed, original
    assert done_lines[0] != original

    back_lines, undone_changed = apply_mark_undone(list(done_lines), VAULT_ID)
    assert undone_changed
    assert back_lines[0] == original, (
        f"round-trip is not byte-identical:\n"
        f"  before: {original!r}\n"
        f"  done:   {done_lines[0]!r}\n"
        f"  after:  {back_lines[0]!r}"
    )


def test_round_trip_through_the_batch_dispatcher_is_byte_identical() -> None:
    """The same guarantee through ``apply_task_updates`` — the door both transports use."""
    content = f"# Daily\n\n- [ ] Ship the fix 🆔 {VAULT_ID}\n- [ ] Untouched\n"

    done, done_applied = apply_task_updates(
        content, [TaskLineUpdate(vault_id=VAULT_ID, mark_done=True, done_date="2026-08-20")]
    )
    assert done_applied == (True,)
    assert done != content

    back, undone_applied = apply_task_updates(
        done, [TaskLineUpdate(vault_id=VAULT_ID, mark_undone=True)]
    )
    assert undone_applied == (True,)
    assert back == content


def test_already_unchecked_dateless_line_is_a_no_op() -> None:
    """Nothing to undo — the steady state of every open task, on every sync."""
    line = f"- [ ] Ship the fix 🆔 {VAULT_ID}\n"
    lines, changed = apply_mark_undone([line], VAULT_ID)
    assert changed is False
    assert lines == [line]


def test_a_dateless_checked_line_is_the_users_own_check_and_is_left_alone() -> None:
    """⚠ The un-check takes back only what SKUEL wrote (Codex #1152 P2).

    ``apply_mark_done`` ALWAYS appends a ``✅ date``, so SKUEL never authors a
    dateless ``[x]``. One on a 🆔 line is therefore the user checking the box in
    Obsidian — and a vault-side check does not reach SKUEL (Guard 2b; inbound
    parked, § R4), so reverting it would silently erase a deliberate edit on the
    very next sync, an edit SKUEL cannot even read.
    """
    line = f"- [x] Ship the fix 🆔 {VAULT_ID}\n"
    lines, changed = apply_mark_undone([line], VAULT_ID)
    assert changed is False
    assert lines == [line]


def test_uppercase_checkbox_is_unchecked_too() -> None:
    """``[X]`` is a checked box to ``_CHECKED_RE``; the flip must handle it."""
    lines, changed = apply_mark_undone(
        [f"- [X] Ship the fix 🆔 {VAULT_ID} ✅ 2026-08-20\n"], VAULT_ID
    )
    assert changed is True
    assert lines == [f"- [ ] Ship the fix 🆔 {VAULT_ID}\n"]


def test_stale_done_date_on_a_manually_unchecked_line_is_stripped() -> None:
    """The other half: the box is open but the ✅ date is still there.

    Both halves independently, mirroring ``apply_mark_done``'s own two-part
    idempotency — the reason the gate is two-part and not just ``[x]``.
    """
    lines, changed = apply_mark_undone(
        [f"- [ ] Ship the fix 🆔 {VAULT_ID} ✅ 2026-08-20\n"], VAULT_ID
    )
    assert changed is True
    assert lines == [f"- [ ] Ship the fix 🆔 {VAULT_ID}\n"]


def test_done_date_with_a_variation_selector_is_stripped() -> None:
    """Some editors append ``️`` to ✅ — the strip must not leave half a token."""
    lines, changed = apply_mark_undone(
        [f"- [x] Ship the fix 🆔 {VAULT_ID} ✅️ 2026-08-20\n"], VAULT_ID
    )
    assert changed is True
    assert lines == [f"- [ ] Ship the fix 🆔 {VAULT_ID}\n"]


def test_absent_vault_id_changes_nothing() -> None:
    """A 🆔 that matches no line: indistinguishable from a no-op by return value alone.

    Which is why the reconciler gates the queue on ``needs_mark_undone`` and
    reads ``WriteResult.updates_applied`` afterwards, rather than trusting
    ``changed`` to mean "there was nothing to do".
    """
    lines = ["- [x] Someone else's task 🆔 sk_zzzzzz ✅ 2026-08-20\n"]
    result, changed = apply_mark_undone(list(lines), VAULT_ID)
    assert changed is False
    assert result == lines


def test_a_non_checkbox_line_carrying_the_id_is_never_edited() -> None:
    """Prose is not a task line — the same guard ``apply_mark_done`` holds."""
    line = f"Notes about 🆔 {VAULT_ID} — completed ✅ 2026-08-20 last week\n"
    lines, changed = apply_mark_undone([line], VAULT_ID)
    assert changed is False
    assert lines == [line]


def test_an_indented_checkbox_line_is_out_of_scope_for_both_directions() -> None:
    """The un-check is never more permissive than the check that wrote the line.

    The checkbox regexes are anchored at column 0, so a nested task line is
    not a task line to ``apply_mark_done`` either — it never receives a ``[x]``
    or a ✅ date from SKUEL. If the un-check reached further than the check, it
    would edit lines SKUEL never wrote to. Neither direction touches it.
    """
    indented = f"    - [x] Nested under a bullet 🆔 {VAULT_ID} ✅ 2026-08-20\n"

    _done, done_changed = apply_mark_done(
        [f"    - [ ] Nested 🆔 {VAULT_ID}\n"], VAULT_ID, "2026-08-20"
    )
    assert done_changed is False

    lines, undone_changed = apply_mark_undone([indented], VAULT_ID)
    assert undone_changed is False
    assert lines == [indented]


def test_only_the_matching_line_moves() -> None:
    """A sibling task in the same note keeps its ``[x]`` and its ✅ date."""
    mine = f"- [x] Mine 🆔 {VAULT_ID} ✅ 2026-08-20\n"
    theirs = "- [x] Theirs 🆔 sk_other1 ✅ 2026-08-21\n"
    lines, changed = apply_mark_undone([mine, theirs], VAULT_ID)
    assert changed is True
    assert lines == [f"- [ ] Mine 🆔 {VAULT_ID}\n", theirs]


class TestNeedsMarkUndone:
    """The queue-time cost gate — it answers by running the mutation itself."""

    def test_true_for_a_checked_line_carrying_the_done_date(self) -> None:
        assert needs_mark_undone(f"- [x] Ship 🆔 {VAULT_ID} ✅ 2026-08-20\n", VAULT_ID) is True

    def test_false_for_a_dateless_checked_line(self) -> None:
        """The user's own Obsidian check — never queued, so never reverted."""
        assert needs_mark_undone(f"- [x] Ship 🆔 {VAULT_ID}\n", VAULT_ID) is False

    def test_true_for_an_unchecked_line_with_a_stale_done_date(self) -> None:
        assert needs_mark_undone(f"- [ ] Ship 🆔 {VAULT_ID} ✅ 2026-08-20\n", VAULT_ID) is True

    def test_false_for_an_open_dateless_line(self) -> None:
        assert needs_mark_undone(f"- [ ] Ship 🆔 {VAULT_ID}\n", VAULT_ID) is False

    def test_false_when_the_id_is_not_in_the_file(self) -> None:
        assert needs_mark_undone("- [x] Someone else 🆔 sk_zzzzzz ✅ 2026-08-20\n", VAULT_ID) is (
            False
        )

    def test_it_does_not_mutate_the_content_it_inspects(self) -> None:
        content = f"# Daily\n\n- [x] Ship 🆔 {VAULT_ID} ✅ 2026-08-20\n"
        assert needs_mark_undone(content, VAULT_ID) is True
        assert content == f"# Daily\n\n- [x] Ship 🆔 {VAULT_ID} ✅ 2026-08-20\n"

    def test_it_agrees_with_the_mutation_on_every_line_shape(self) -> None:
        """The gate cannot drift from the write — it IS the write, run dry."""
        for content in (
            f"- [ ] open 🆔 {VAULT_ID}\n",
            f"- [x] checked-dateless 🆔 {VAULT_ID}\n",
            f"- [x] checked+dated 🆔 {VAULT_ID} ✅ 2026-08-20\n",
            f"- [ ] dated-only 🆔 {VAULT_ID} ✅ 2026-08-20\n",
            f"prose 🆔 {VAULT_ID} ✅ 2026-08-20\n",
            "- [x] other 🆔 sk_zzzzzz ✅ 2026-08-20\n",
        ):
            _lines, changed = apply_mark_undone(content.splitlines(keepends=True), VAULT_ID)
            assert needs_mark_undone(content, VAULT_ID) is changed, content


def test_mark_undone_dispatches_and_reports_its_own_outcome() -> None:
    """A batch mixing operations: each slot answers for ITSELF (protocol v2/v3)."""
    content = f"- [x] Reopened 🆔 {VAULT_ID} ✅ 2026-08-20\n- [ ] Never touched 🆔 sk_other1\n"
    new_content, applied = apply_task_updates(
        content,
        [
            TaskLineUpdate(vault_id=VAULT_ID, mark_undone=True),
            # Already open and dateless — a real no-op, reported as one.
            TaskLineUpdate(vault_id="sk_other1", mark_undone=True),
            # No such line at all — also False, and the caller can tell them
            # apart only through its own queue-time gate.
            TaskLineUpdate(vault_id="sk_absent", mark_undone=True),
        ],
    )
    assert applied == (True, False, False)
    assert new_content == f"- [ ] Reopened 🆔 {VAULT_ID}\n- [ ] Never touched 🆔 sk_other1\n"


def test_an_update_with_no_operation_flag_is_still_a_no_op() -> None:
    """What a STALE agent would build from a v3 frame it cannot parse.

    It is exactly why the un-check needed ``PROTOCOL_VERSION`` 2 → 3: a v2
    agent handed ``mark_undone`` sets no flag, changes nothing, and answers
    ``success: True``. The handshake refusal — not this branch — is what keeps
    the server from believing the un-check landed.
    """
    content = f"- [x] Ship 🆔 {VAULT_ID} ✅ 2026-08-20\n"
    new_content, applied = apply_task_updates(content, [TaskLineUpdate(vault_id=VAULT_ID)])
    assert applied == (False,)
    assert new_content == content
