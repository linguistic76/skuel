"""``apply_inject_id`` — the 🆔 write keeps SKUEL's ``✅ date`` the last token.

``apply_mark_done`` keys its no-op on a TRAILING ``✅ date`` (the marker it
writes and ``apply_mark_undone`` reverses). A 🆔 appended after that marker
un-trails it, so the next outbound pass reads an already-done line as
unmarked and appends a second date. Reachable through the hand-authored
``- [x] … ✅ date`` create door and through a re-mint onto a written-back
line: the token goes in front of the marker, as the obsidian-tasks plugin
itself orders them, and the 🆔-blind digest is the same either side.
"""

from __future__ import annotations

import pytest

from core.ports.vault_bridge_protocol import (
    TaskLineUpdate,
    apply_inject_id,
    apply_mark_done,
    apply_mark_undone,
    apply_task_updates,
    normalize_vault_line_hash,
)

VAULT_ID = "sk_a1b2c3"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(
            "- [x] Ship the fix ✅ 2026-08-20\n",
            f"- [x] Ship the fix 🆔 {VAULT_ID} ✅ 2026-08-20\n",
            id="done-line-keeps-the-marker-trailing",
        ),
        pytest.param(
            "- [x] Ship the fix ✅ 2026-08-20",
            f"- [x] Ship the fix 🆔 {VAULT_ID} ✅ 2026-08-20",
            id="done-line-at-eof",
        ),
        pytest.param(
            "- [ ] Ship the fix\n",
            f"- [ ] Ship the fix 🆔 {VAULT_ID}\n",
            id="open-line-appends",
        ),
        pytest.param(
            "- [ ] Ship 📅 2026-01-01 ⏫\n",
            f"- [ ] Ship 📅 2026-01-01 ⏫ 🆔 {VAULT_ID}\n",
            id="open-line-with-other-tokens-appends",
        ),
        pytest.param(
            "- [ ] Compare ✅ 2025-01-01 vs now\n",
            f"- [ ] Compare ✅ 2025-01-01 vs now 🆔 {VAULT_ID}\n",
            id="a-date-inside-the-prose-is-not-a-marker",
        ),
        pytest.param(
            "- [x] Ship the fix ✅️ 2026-08-20\n",
            f"- [x] Ship the fix 🆔 {VAULT_ID} ✅️ 2026-08-20\n",
            id="variation-selector-on-the-marker",
        ),
    ],
)
def test_the_token_lands_where_the_plugin_puts_it(line: str, expected: str) -> None:
    lines, changed = apply_inject_id([line], VAULT_ID, normalize_vault_line_hash(line))
    assert changed
    assert lines[0] == expected
    assert normalize_vault_line_hash(lines[0]) == normalize_vault_line_hash(line), (
        "the digest must not move on injection"
    )


def test_a_done_line_is_a_no_op_for_mark_done_after_injection() -> None:
    """The defect in one assertion: inject, then mark done — nothing to add."""
    line = "- [x] Ship the fix ✅ 2026-08-20\n"
    injected, _ = apply_inject_id([line], VAULT_ID, None)
    marked, changed = apply_mark_done(list(injected), VAULT_ID, "2026-08-20")
    assert not changed, marked[0]
    assert marked[0].count("✅") == 1


def test_inject_then_reopen_restores_the_open_line_the_completion_would_have_written() -> None:
    """Inject onto a done line, reopen: the result is exactly the open 🆔 line
    that completing again would carry — the three writes compose."""
    line = "- [x] Ship the fix ✅ 2026-08-20\n"
    injected, _ = apply_inject_id([line], VAULT_ID, None)
    reopened, changed = apply_mark_undone(list(injected), VAULT_ID)
    assert changed
    assert reopened[0] == f"- [ ] Ship the fix 🆔 {VAULT_ID}\n"
    redone, _ = apply_mark_done(list(reopened), VAULT_ID, "2026-08-20")
    assert redone[0] == injected[0]


def test_through_the_batch_dispatcher() -> None:
    content = "# Daily\n- [x] Ship the fix ✅ 2026-08-20\n- [ ] Water the plants\n"
    new_content, applied = apply_task_updates(
        content,
        [
            TaskLineUpdate(
                vault_id=VAULT_ID,
                inject_vault_id=True,
                source_line_hash=normalize_vault_line_hash("- [x] Ship the fix ✅ 2026-08-20"),
            ),
            TaskLineUpdate(
                vault_id="sk_d4e5f6",
                inject_vault_id=True,
                source_line_hash=normalize_vault_line_hash("- [ ] Water the plants"),
            ),
        ],
    )
    assert applied == (True, True)
    assert new_content == (
        f"# Daily\n- [x] Ship the fix 🆔 {VAULT_ID} ✅ 2026-08-20\n"
        "- [ ] Water the plants 🆔 sk_d4e5f6\n"
    )
