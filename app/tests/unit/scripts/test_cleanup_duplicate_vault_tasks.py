"""Pure-rule tests for scripts/cleanup_duplicate_vault_tasks.py.

The script is a CLI over the live graph + the personal vault; ``classify`` is
the pure rule and is pinned here. The rule: one physical vault checkbox line ⇒
one task — the keeper is the line's 🆔 owner (else the oldest), and only
edge-less, COMPLETED twins are deleted. Anything short of that proof is REVIEW.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from cleanup_duplicate_vault_tasks import (  # type: ignore[import-not-found]
    TaskRow,
    VaultTaskLine,
    classify,
    scan_vault_task_lines,
)


def _task(uid, title, *, created, vault_ids=(), edges=None, status="completed", other=0):
    edge_count = len(vault_ids) if edges is None else edges
    return TaskRow(
        uid=uid,
        title=title,
        status=status,
        created_at=created,
        vault_ids=tuple(vault_ids),
        edge_count=edge_count,
        other_rel_count=other,
    )


def _line(title, *, vault_id=None, file="periodic_notes/Daily/2026-06-29.md", no=18, checked=True):
    return VaultTaskLine(file=file, line_no=no, title=title, vault_id=vault_id, is_checked=checked)


# --- DELETE -----------------------------------------------------------------


def test_vault_linked_twin_is_kept_and_edgeless_completed_original_deleted():
    """The live shape: 06-28 orphan (no edge) vs the 07-11 twin that owns the line's 🆔."""
    original = _task("task_699a931e", "Call Joffe office", created="2026-06-28T12:43:04")
    twin = _task(
        "task_dd3061ec",
        "Call Joffe office",
        created="2026-07-11T20:59:23",
        vault_ids=("sk_1hmd4h",),
    )
    line = _line("Call Joffe office", vault_id="sk_1hmd4h")

    out = classify([original, twin], [line], owned_vault_ids={"sk_1hmd4h"})

    assert len(out.duplicate_sets) == 1
    s = out.duplicate_sets[0]
    assert s.keep is twin
    assert [t.uid for t in s.delete] == ["task_699a931e"]
    assert s.left_for_review == ()
    assert out.delete_uids == ["task_699a931e"]
    assert out.review == []
    assert out.orphans == []  # the deleted original is not re-listed as an orphan


def test_both_edgeless_keeps_the_oldest_and_deletes_the_later_remint():
    """'move furniture': neither task owns the line's 🆔 (phantom) → oldest wins."""
    older = _task("task_b9d52706", "move furniture", created="2026-07-04T05:28:43", other=2)
    later = _task("task_0aa1f578", "move furniture", created="2026-07-11T20:59:06")
    line = _line(
        "move furniture", vault_id="sk_3uhmts", file="periodic_notes/Daily/2026-06-17.md", no=20
    )

    out = classify([later, older], [line], owned_vault_ids=set())

    s = out.duplicate_sets[0]
    assert s.keep is older
    assert [t.uid for t in s.delete] == ["task_0aa1f578"]
    # The phantom id is still reported, and its likely owner is the KEPT task only.
    assert [p.line.vault_id for p in out.phantom_ids] == ["sk_3uhmts"]
    assert [t.uid for t in out.phantom_ids[0].likely_owners] == ["task_b9d52706"]
    assert [t.uid for t in out.orphans] == ["task_b9d52706"]


def test_title_match_uses_the_guard_normaliser():
    """Case and whitespace differences are the R3 key's business, not a new task."""
    a = _task("task_a", "Move  Furniture", created="2026-07-04T05:28:43")
    b = _task("task_b", "move furniture", created="2026-07-11T20:59:06")
    out = classify([a, b], [_line("move furniture", vault_id=None)], owned_vault_ids=set())
    assert [t.uid for t in out.duplicate_sets[0].delete] == ["task_b"]


# --- REVIEW: no proof, no delete --------------------------------------------


def test_no_vault_line_today_is_review_only():
    """Deleted line or template variant: cannot prove one line."""
    a = _task("task_a", "Ask about tests", created="2026-07-04T05:28:38", edges=1)
    b = _task("task_b", "Ask about tests", created="2026-07-11T20:59:24")
    out = classify([a, b], [], owned_vault_ids=set())
    assert out.duplicate_sets == []
    assert len(out.review) == 1
    assert "no vault checkbox line" in out.review[0].reason
    assert [t.uid for t in out.orphans] == ["task_b"]


def test_recurring_template_line_in_two_notes_is_not_a_duplicate():
    """One 'Reflect…' line per daily note ⇒ one task per note. Never merged."""
    a = _task("task_a", "Reflect on what went well today", created="2026-07-01T11:56:33", edges=1)
    b = _task("task_b", "Reflect on what went well today", created="2026-07-22T08:18:16")
    lines = [
        _line("Reflect on what went well today", file="periodic_notes/Daily/2026-06-29.md"),
        _line("Reflect on what went well today", file="periodic_notes/Daily/2026-06-30.md"),
    ]
    out = classify([a, b], lines, owned_vault_ids=set())
    assert out.duplicate_sets == []
    assert "recurring" in out.review[0].reason


def test_edge_bearing_twins_are_never_deleted():
    """Two tasks with provenance edges may belong to two entries — not ours to judge."""
    a = _task("task_a", "Vacuum", created="2026-07-01T18:53:14", vault_ids=("sk_gnor1o",))
    b = _task("task_b", "Vacuum", created="2026-07-11T22:49:49", edges=1)
    out = classify([a, b], [_line("Vacuum", vault_id="sk_gnor1o")], owned_vault_ids={"sk_gnor1o"})
    assert out.duplicate_sets == []
    assert "provenance edges" in out.review[0].reason


def test_active_edgeless_twin_is_left_for_review_not_deleted():
    """Guard 4 owns active twins; the script only removes completed re-mints."""
    keeper = _task("task_k", "Physio", created="2026-06-28T12:43:04", vault_ids=("sk_bcd7if",))
    active = _task("task_x", "Physio", created="2026-07-11T20:59:23", status="active")
    stale = _task("task_y", "Physio", created="2026-07-12T20:59:23")
    out = classify([keeper, active, stale], [_line("Physio", vault_id="sk_bcd7if")], {"sk_bcd7if"})
    s = out.duplicate_sets[0]
    assert s.keep is keeper
    assert [t.uid for t in s.delete] == ["task_y"]
    assert [t.uid for t in s.left_for_review] == ["task_x"]


def test_contested_id_is_review():
    """A 🆔 owned by two tasks (the pre-Guard-2b bug shape) is not resolved here."""
    a = _task("task_a", "Dr 9 am", created="2026-07-04T12:28:35", vault_ids=("sk_kqawpy",))
    b = _task("task_b", "Dr 9 am", created="2026-07-04T12:47:35", vault_ids=("sk_kqawpy",))
    c = _task("task_c", "Dr 9 am", created="2026-07-11T12:47:35")
    out = classify([a, b, c], [_line("Dr 9 am", vault_id="sk_kqawpy")], {"sk_kqawpy"})
    assert out.duplicate_sets == []
    assert "more than one task" in out.review[0].reason


# --- PHANTOM / DANGLING / ORPHANS -------------------------------------------


def test_phantom_and_dangling_ids_are_reconciled_both_ways():
    task = _task("task_p", "Physio therapist", created="2026-06-28T12:43:04")
    lines = [
        _line("Physio therapist", vault_id="sk_bcd7if", no=20, checked=False),
        _line("tenants message", vault_id="sk_bds4oj", file="periodic_notes/Daily/2026-06-30.md"),
    ]
    out = classify([task], lines, owned_vault_ids={"sk_bds4oj", "sk_gone01"})
    assert [p.line.vault_id for p in out.phantom_ids] == ["sk_bcd7if"]
    assert [t.uid for t in out.phantom_ids[0].likely_owners] == ["task_p"]
    assert out.dangling_ids == ["sk_gone01"]
    assert [t.uid for t in out.orphans] == ["task_p"]


def test_singleton_edgeless_task_is_an_orphan_only():
    task = _task(
        "task.three-moments-values", "Write the Three Moments", created="2026-08-09", status="draft"
    )
    out = classify([task], [], owned_vault_ids=set())
    assert out.duplicate_sets == [] and out.review == []
    assert [t.uid for t in out.orphans] == ["task.three-moments-values"]


# --- Vault scan -------------------------------------------------------------


def test_scan_reads_only_extract_activities_files_outside_staging(tmp_path: Path):
    daily = tmp_path / "periodic_notes" / "Daily"
    daily.mkdir(parents=True)
    (daily / "2026-06-29.md").write_text(
        "---\ntype: user_entry\npipeline: extract_activities\n---\n"
        "- [x] Call Joffe office apt 🆔 sk_1hmd4h ✅ 2026-07-16\n"
        "- [ ]  🏁 schedule trip to Van 📅 2026-07-01 ⏫ 🆔 sk_er8cqr\n"
        "- [ ] \n"  # blank template slot: not a task
        "- [ ] Physio therapist look 4 - yes🔼\n",
        encoding="utf-8",
    )
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "note.md").write_text(
        "---\npipeline: knowledge\n---\n- [ ] not a task source\n", encoding="utf-8"
    )
    (tmp_path / "je_out").mkdir()
    (tmp_path / "je_out" / "staged.md").write_text(
        "---\npipeline: extract_activities\n---\n- [ ] walled off\n", encoding="utf-8"
    )

    lines = scan_vault_task_lines(tmp_path, allowlist=None)

    assert [(ln.line_no, ln.title, ln.vault_id, ln.is_checked) for ln in lines] == [
        (5, "Call Joffe office apt", "sk_1hmd4h", True),
        (6, "🏁 schedule trip to Van", "sk_er8cqr", False),
        (8, "Physio therapist look 4 - yes", None, False),
    ]
    assert {ln.file for ln in lines} == {"periodic_notes/Daily/2026-06-29.md"}
