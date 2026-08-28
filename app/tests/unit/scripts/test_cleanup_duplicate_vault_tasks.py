"""Pure-rule tests for scripts/cleanup_duplicate_vault_tasks.py.

The script is a CLI over the live graph + the personal vault; the rules are
pure and pinned here. Proposal rule: one physical vault checkbox line ⇒ one
task — the keeper is the line's 🆔 owner (else the oldest), and only edge-less,
COMPLETED twins are proposed; strays are edge-less completed tasks on no line
at all. Nothing is deleted without a matching ``--confirm`` (Codex #1165 P1):
``select_confirmed`` refuses any uid the run does not propose.
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
    delete_blocker,
    entry_for_file,
    plan_repairs,
    scan_vault_task_lines,
    select_confirmed,
)

from core.services.dsl.activity_extractor import normalized_line_hash


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
    return VaultTaskLine(
        file=file,
        line_no=no,
        title=title,
        vault_id=vault_id,
        is_checked=checked,
        raw_line=f"- [ ] {title}",
    )


# --- PROPOSED re-mints --------------------------------------------------------


def test_vault_linked_twin_is_kept_and_edgeless_completed_original_proposed():
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
    assert [t.uid for t in s.proposed] == ["task_699a931e"]
    assert s.left_for_review == ()
    assert out.remint_uids == ["task_699a931e"]
    assert out.proposed_uids == ["task_699a931e"]
    assert out.review == [] and out.strays == [] and out.line_backed == []


def test_both_edgeless_keeps_the_oldest_and_proposes_the_later_remint():
    """'move furniture': neither task owns the line's 🆔 (phantom) → oldest wins, stays line-backed."""
    older = _task("task_b9d52706", "move furniture", created="2026-07-04T05:28:43", other=2)
    later = _task("task_0aa1f578", "move furniture", created="2026-07-11T20:59:06")
    line = _line(
        "move furniture", vault_id="sk_3uhmts", file="periodic_notes/Daily/2026-06-17.md", no=20
    )

    out = classify([later, older], [line], owned_vault_ids=set())

    s = out.duplicate_sets[0]
    assert s.keep is older
    assert [t.uid for t in s.proposed] == ["task_0aa1f578"]
    # The phantom id is reported with the KEPT task as its only likely owner,
    # and the keeper is line-backed — never a stray.
    assert [p.line.vault_id for p in out.phantom_ids] == ["sk_3uhmts"]
    assert [t.uid for t in out.phantom_ids[0].likely_owners] == ["task_b9d52706"]
    assert [t.uid for t in out.line_backed] == ["task_b9d52706"]
    assert out.strays == []


def test_title_match_uses_the_guard_normaliser():
    """Case and whitespace differences are the R3 key's business, not a new task."""
    a = _task("task_a", "Move  Furniture", created="2026-07-04T05:28:43")
    b = _task("task_b", "move furniture", created="2026-07-11T20:59:06")
    out = classify([a, b], [_line("move furniture", vault_id=None)], owned_vault_ids=set())
    assert [t.uid for t in out.duplicate_sets[0].proposed] == ["task_b"]


# --- REVIEW: no proof, no proposal -------------------------------------------


def test_no_vault_line_today_is_review_and_the_edgeless_twin_is_a_stray():
    """Deleted line or template variant: cannot prove one line; the edge-less one is a stray."""
    a = _task("task_a", "Ask about tests", created="2026-07-04T05:28:38", edges=1)
    b = _task("task_b", "Ask about tests", created="2026-07-11T20:59:24")
    out = classify([a, b], [], owned_vault_ids=set())
    assert out.duplicate_sets == []
    assert len(out.review) == 1
    assert "no vault checkbox line" in out.review[0].reason
    assert [t.uid for t in out.strays] == ["task_b"]


def test_recurring_template_line_in_two_notes_is_not_a_duplicate():
    """One 'Reflect…' line per daily note ⇒ one task per note. Never merged; edge-less one is line-backed."""
    a = _task("task_a", "Reflect on what went well today", created="2026-07-01T11:56:33", edges=1)
    b = _task("task_b", "Reflect on what went well today", created="2026-07-22T08:18:16")
    lines = [
        _line("Reflect on what went well today", file="periodic_notes/Daily/2026-06-29.md"),
        _line("Reflect on what went well today", file="periodic_notes/Daily/2026-06-30.md"),
    ]
    out = classify([a, b], lines, owned_vault_ids=set())
    assert out.duplicate_sets == []
    assert "recurring" in out.review[0].reason
    assert [t.uid for t in out.line_backed] == ["task_b"]
    assert out.strays == []


def test_edge_bearing_twins_are_never_proposed():
    """Two tasks with provenance edges may belong to two entries — not ours to judge."""
    a = _task("task_a", "Vacuum", created="2026-07-01T18:53:14", vault_ids=("sk_gnor1o",))
    b = _task("task_b", "Vacuum", created="2026-07-11T22:49:49", edges=1)
    out = classify([a, b], [_line("Vacuum", vault_id="sk_gnor1o")], owned_vault_ids={"sk_gnor1o"})
    assert out.duplicate_sets == []
    assert "provenance edges" in out.review[0].reason


def test_active_edgeless_twin_is_left_for_review_not_proposed():
    """Guard 4 owns active twins; the script only proposes completed re-mints."""
    keeper = _task("task_k", "Physio", created="2026-06-28T12:43:04", vault_ids=("sk_bcd7if",))
    active = _task("task_x", "Physio", created="2026-07-11T20:59:23", status="active")
    stale = _task("task_y", "Physio", created="2026-07-12T20:59:23")
    out = classify([keeper, active, stale], [_line("Physio", vault_id="sk_bcd7if")], {"sk_bcd7if"})
    s = out.duplicate_sets[0]
    assert s.keep is keeper
    assert [t.uid for t in s.proposed] == ["task_y"]
    assert [t.uid for t in s.left_for_review] == ["task_x"]
    assert [t.uid for t in out.line_backed] == ["task_x"]  # active + edge-less: not a stray


def test_id_owned_by_a_task_outside_the_title_group_is_review():
    """The line's 🆔 positively ties it to a task whose title diverged (vault edit, inbound
    propagation parked) — the same-title group is NOT that line's re-mints (Codex r8)."""
    outside = _task(
        "task_z", "Physio look 4 — OLD title", created="2026-06-20", vault_ids=("sk_x",)
    )
    a = _task("task_a", "Physio", created="2026-06-28T12:43:04")
    b = _task("task_b", "Physio", created="2026-07-11T20:59:23")
    out = classify([outside, a, b], [_line("Physio", vault_id="sk_x")], {"sk_x"})
    assert out.duplicate_sets == []
    assert len(out.review) == 1
    assert "task_z" in out.review[0].reason and "outside" in out.review[0].reason
    assert out.proposed_uids == []


def test_contested_id_is_review():
    """A 🆔 owned by two tasks (the pre-Guard-2b bug shape) is not resolved here."""
    a = _task("task_a", "Dr 9 am", created="2026-07-04T12:28:35", vault_ids=("sk_kqawpy",))
    b = _task("task_b", "Dr 9 am", created="2026-07-04T12:47:35", vault_ids=("sk_kqawpy",))
    c = _task("task_c", "Dr 9 am", created="2026-07-11T12:47:35")
    out = classify([a, b, c], [_line("Dr 9 am", vault_id="sk_kqawpy")], {"sk_kqawpy"})
    assert out.duplicate_sets == []
    assert "more than one task" in out.review[0].reason


# --- STRAYS vs LINE-BACKED ----------------------------------------------------


def test_stray_needs_no_line_at_all_and_completed_status():
    paraphrase = _task("task_p", "Consider trailer options", created="2026-06-28T12:43:08")
    draft = _task("task_d", "Track one pattern", created="2026-08-09T17:27:38", status="draft")
    owner = _task("task_o", "Consider the trailer", created="2026-06-29T01:49:07")
    out = classify(
        [paraphrase, draft, owner], [_line("Consider the trailer", vault_id=None)], set()
    )
    assert [t.uid for t in out.strays] == ["task_p"]
    assert [t.uid for t in out.line_backed] == ["task_o", "task_d"]
    assert out.proposed_uids == ["task_p"]


# --- PHANTOM / DANGLING -------------------------------------------------------


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
    assert [t.uid for t in out.line_backed] == ["task_p"]


# --- The human census: --confirm --------------------------------------------


def test_select_confirmed_intersects_and_refuses_unproposed():
    to_delete, refused = select_confirmed(
        ["task_a", "task_b", "task_c"], [" task_c ", "task_a", "task_zzz", ""]
    )
    assert to_delete == ["task_a", "task_c"]  # report order, not confirm order
    assert refused == ["task_zzz"]


def test_select_confirmed_with_nothing_confirmed_deletes_nothing():
    assert select_confirmed(["task_a"], []) == ([], [])


def test_delete_blocker_reflects_live_state_at_delete_time():
    """A confirmed uid is re-checked right before its delete (Codex r6): only the census shape passes."""
    assert delete_blocker("completed", False) is None
    assert delete_blocker("active", False) == "status is now 'active', not completed"
    assert delete_blocker("completed", True) == "now carries an EXTRACTED_FROM edge"
    assert delete_blocker(None, None) == "no longer exists"


# --- Repairs -----------------------------------------------------------------


def test_entry_for_file_uses_other_owned_ids_and_refuses_ambiguity():
    lines = [
        _line("Call Joffe", vault_id="sk_1hmd4h"),
        _line("Physio", vault_id="sk_bcd7if", no=20),
        _line("move furniture", vault_id="sk_3uhmts", file="periodic_notes/Daily/2026-06-17.md"),
        _line("a", vault_id="sk_aaaaaa", file="mixed.md", no=1),
        _line("b", vault_id="sk_bbbbbb", file="mixed.md", no=2),
    ]
    owned = {"sk_1hmd4h": {"ue:daily:u:2026-06-29"}, "sk_aaaaaa": {"ue:x"}, "sk_bbbbbb": {"ue:y"}}
    resolved = entry_for_file(lines, owned)
    assert resolved["periodic_notes/Daily/2026-06-29.md"] == "ue:daily:u:2026-06-29"
    assert resolved["mixed.md"] is None  # two entries → ambiguous
    assert "periodic_notes/Daily/2026-06-17.md" not in resolved  # no owned id at all


def test_an_owned_anchor_id_copied_into_two_files_anchors_neither():
    """An owned 🆔 on lines in two files would resolve both to one entry — it anchors nothing (Codex r7)."""
    owner = _task("task_o", "Physio", created="2026-06-28T12:43:04")
    lines = [
        _line("anchor", vault_id="sk_copied"),
        _line("anchor", vault_id="sk_copied", file="periodic_notes/Daily/2026-06-30.md"),
        _line("Physio", vault_id="sk_phantom", file="periodic_notes/Daily/2026-06-30.md", no=20),
    ]
    owned = {"sk_copied": {"ue:daily:u:2026-06-29"}}

    assert entry_for_file(lines, owned) == {}
    c = classify([owner], lines, set(owned))
    repairs, problems = plan_repairs(c, ["sk_phantom"], entry_for_file(lines, owned))
    assert repairs == []
    assert len(problems) == 1 and "no single entry" in problems[0]


def test_plan_repairs_builds_the_door_shaped_link_and_refuses_the_rest():
    owner = _task("task_091092e1", "Physio therapist look 4 - yes", created="2026-06-28T12:43:04")
    # The 06-17 line's task exists, but its entry is gone — no other owned 🆔 in that file.
    mover = _task("task_b9d52706", "move furniture", created="2026-07-04T05:28:43")
    lines = [
        _line("Call Joffe", vault_id="sk_1hmd4h"),
        VaultTaskLine(
            file="periodic_notes/Daily/2026-06-29.md",
            line_no=20,
            title="Physio therapist look 4 - yes",
            vault_id="sk_bcd7if",
            is_checked=False,
            raw_line="- [ ] Physio therapist look 4 - yes🔼",
        ),
        _line("move furniture", vault_id="sk_3uhmts", file="periodic_notes/Daily/2026-06-17.md"),
    ]
    owned = {"sk_1hmd4h": {"ue:daily:u:2026-06-29"}}
    c = classify([owner, mover], lines, set(owned))
    repairs, problems = plan_repairs(
        c, ["sk_bcd7if", "sk_3uhmts", "sk_1hmd4h"], entry_for_file(lines, owned)
    )

    assert [r.task.uid for r in repairs] == ["task_091092e1"]
    assert repairs[0].entry_uid == "ue:daily:u:2026-06-29"
    assert repairs[0].link == (
        "task_091092e1",
        normalized_line_hash("- [ ] Physio therapist look 4 - yes🔼"),
        "sk_bcd7if",
    )
    assert len(problems) == 2
    assert any(p.startswith("sk_3uhmts:") and "re-sync" in p for p in problems)
    assert any(p.startswith("sk_1hmd4h:") and "not a phantom" in p for p in problems)


def test_plan_repairs_refuses_an_id_copied_onto_two_lines():
    """A 🆔 on two vault lines is ambiguous — repairing either would mis-tie the other (Codex r3)."""
    owner = _task("task_o", "Vacuum", created="2026-07-01T18:53:14")
    lines = [
        _line("anchor", vault_id="sk_anchor"),
        _line("Vacuum", vault_id="sk_copied", no=30),
        _line("Vacuum", vault_id="sk_copied", file="periodic_notes/Weekly/2026-W29.md", no=31),
    ]
    owned = {"sk_anchor": {"ue:daily:u:2026-06-29"}}
    c = classify([owner], lines, set(owned))
    assert [p.line.vault_id for p in c.phantom_ids] == ["sk_copied", "sk_copied"]

    repairs, problems = plan_repairs(c, ["sk_copied"], entry_for_file(lines, owned))

    assert repairs == []
    assert len(problems) == 1 and "2 vault lines carry this id" in problems[0]
    assert "2026-06-29.md:30" in problems[0] and "2026-W29.md:31" in problems[0]


def test_an_anchor_id_reaching_two_entries_makes_the_file_ambiguous():
    """One 🆔 with edges into two entries cannot anchor a file — refuse, never pick one (Codex r4)."""
    owner = _task("task_o", "Physio", created="2026-06-28T12:43:04")
    lines = [
        _line("anchor", vault_id="sk_anchor"),
        _line("Physio", vault_id="sk_phantom", no=20),
    ]
    owned = {"sk_anchor": {"ue:daily:u:2026-06-29", "ue:daily:u:2026-06-30"}}

    assert entry_for_file(lines, owned) == {"periodic_notes/Daily/2026-06-29.md": None}
    c = classify([owner], lines, set(owned))
    repairs, problems = plan_repairs(c, ["sk_phantom"], entry_for_file(lines, owned))
    assert repairs == []
    assert len(problems) == 1 and "no single entry" in problems[0]


def test_a_task_that_is_the_candidate_for_two_phantom_lines_is_never_repaired():
    """Same title on two phantom lines with different ids: which line is the task's? Refuse (Codex r5)."""
    owner = _task("task_o", "Physio", created="2026-06-28T12:43:04")
    lines = [
        _line("anchor", vault_id="sk_anchor"),
        _line("Physio", vault_id="sk_first", no=20),
        _line("Physio", vault_id="sk_second", no=21),
    ]
    owned = {"sk_anchor": {"ue:daily:u:2026-06-29"}}
    c = classify([owner], lines, set(owned))
    assert [p.line.vault_id for p in c.phantom_ids] == ["sk_first", "sk_second"]

    # Even a single requested id is refused — the task's line is not knowable.
    repairs, problems = plan_repairs(c, ["sk_first"], entry_for_file(lines, owned))
    assert repairs == []
    assert len(problems) == 1 and "task_o" in problems[0] and "2 phantom lines" in problems[0]

    repairs, problems = plan_repairs(c, ["sk_first", "sk_second"], entry_for_file(lines, owned))
    assert repairs == [] and len(problems) == 2


# --- Vault scan ---------------------------------------------------------------


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
    # Ingestion's collector does NOT skip dot-directories (pathlib ``**`` matches
    # them), so a note there is a real task source and must be in the census too
    # — otherwise its task would read as "no vault line" and be proposed (Codex r2).
    hidden = tmp_path / "periodic_notes" / ".drafts"
    hidden.mkdir()
    (hidden / "2026-07-01.md").write_text(
        "---\npipeline: extract_activities\n---\n- [ ] hidden but ingested\n", encoding="utf-8"
    )

    lines = scan_vault_task_lines(tmp_path, allowlist=None)

    assert [(ln.file, ln.line_no, ln.title, ln.vault_id, ln.is_checked) for ln in lines] == [
        ("periodic_notes/.drafts/2026-07-01.md", 4, "hidden but ingested", None, False),
        ("periodic_notes/Daily/2026-06-29.md", 5, "Call Joffe office apt", "sk_1hmd4h", True),
        ("periodic_notes/Daily/2026-06-29.md", 6, "🏁 schedule trip to Van", "sk_er8cqr", False),
        ("periodic_notes/Daily/2026-06-29.md", 8, "Physio therapist look 4 - yes", None, False),
    ]
    # The raw line is the door's normalized form: checkbox canonicalised, 🆔 stripped —
    # so a hash of it matches what Guard 2 stores on the edge.
    assert lines[1].raw_line == "- [ ] Call Joffe office apt ✅ 2026-07-16"
    assert normalized_line_hash(lines[1].raw_line) == normalized_line_hash(
        "- [x] Call Joffe office apt 🆔 sk_1hmd4h ✅ 2026-07-16"
    )
