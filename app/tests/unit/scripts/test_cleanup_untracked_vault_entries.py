"""Pure-filter tests for scripts/cleanup_untracked_vault_entries.py.

The script is a CLI over the live graph; ``select_orphans`` is the pure
criterion and is pinned here against fixture rows. The DELETE set requires the
positive orphan signal (path tracked to a live entry, Codex #616 P1); an
untracked path is REVIEW-only (ambiguous). Contract:
docs/roadmap/done/uidless-vault-entry-identity-upsert.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from cleanup_untracked_vault_entries import select_orphans  # type: ignore[import-not-found]


def _row(uid, *, path=None, vault=True, has_fulfills=False, pipeline="knowledge"):
    vfp = path if path is not None else f"/vault/{uid}.md"
    meta = json.dumps({"vault_file_path": vfp}) if vault else json.dumps({})
    return {"uid": uid, "metadata": meta, "pipeline": pipeline, "has_fulfills": has_fulfills}


def test_tracked_path_is_deletable():
    """Positive orphan signal: the path is tracked to a live entry → DELETE."""
    rows = [_row("ue_orphan", path="/vault/note.md")]
    deletable, ambiguous = select_orphans(
        rows, tracked_uids=set(), live_ue_paths={"/vault/note.md"}
    )
    assert [o["uid"] for o in deletable] == ["ue_orphan"]
    assert deletable[0]["vault_file_path"] == "/vault/note.md"
    assert ambiguous == []


def test_untracked_path_is_ambiguous_not_deletable():
    """No tracked entry at this path → REVIEW-only, never auto-deleted."""
    rows = [_row("ue_lonely", path="/vault/lonely.md")]
    deletable, ambiguous = select_orphans(rows, tracked_uids=set(), live_ue_paths=set())
    assert deletable == []
    assert [o["uid"] for o in ambiguous] == ["ue_lonely"]


def test_tracked_entry_is_kept_entirely():
    """A tracked (live) entry is neither deletable nor ambiguous."""
    rows = [_row("ue_live", path="/vault/note.md")]
    deletable, ambiguous = select_orphans(
        rows, tracked_uids={"ue_live"}, live_ue_paths={"/vault/note.md"}
    )
    assert deletable == []
    assert ambiguous == []


def test_turn_in_copy_is_kept():
    """Belt-and-braces: a FULFILLS_EXERCISE-bearing entry is never a candidate."""
    rows = [_row("ue_turnin", path="/vault/t.md", has_fulfills=True)]
    deletable, ambiguous = select_orphans(rows, tracked_uids=set(), live_ue_paths={"/vault/t.md"})
    assert deletable == []
    assert ambiguous == []


def test_entry_without_vault_path_is_kept():
    """A non-vault UserEntry (no vault_file_path key) is out of scope entirely."""
    rows = [_row("ue_form", vault=False)]
    deletable, ambiguous = select_orphans(rows, tracked_uids=set(), live_ue_paths=set())
    assert deletable == []
    assert ambiguous == []


def test_null_or_malformed_metadata_is_kept():
    rows = [
        {"uid": "ue_none", "metadata": None, "pipeline": "knowledge", "has_fulfills": False},
        {"uid": "ue_bad", "metadata": "{not json", "pipeline": "knowledge", "has_fulfills": False},
    ]
    deletable, ambiguous = select_orphans(rows, tracked_uids=set(), live_ue_paths=set())
    assert deletable == []
    assert ambiguous == []


def test_substring_only_match_is_not_a_hit():
    """A structured parse, not a CONTAINS heuristic: the key must genuinely
    exist, not merely appear as a substring in some other value."""
    rows = [
        {
            "uid": "ue_decoy",
            "metadata": json.dumps({"note": "see vault_file_path docs"}),
            "pipeline": "knowledge",
            "has_fulfills": False,
        }
    ]
    deletable, ambiguous = select_orphans(rows, tracked_uids=set(), live_ue_paths=set())
    assert deletable == []
    assert ambiguous == []


def test_mixed_batch_splits_correctly():
    rows = [
        _row("ue_super", path="/vault/a.md"),  # path tracked → DELETE
        _row("ue_lonely", path="/vault/b.md"),  # path untracked → REVIEW
        _row("ue_live", path="/vault/c.md"),  # tracked uid → kept
    ]
    deletable, ambiguous = select_orphans(
        rows,
        tracked_uids={"ue_live"},
        live_ue_paths={"/vault/a.md", "/vault/c.md"},
    )
    assert [o["uid"] for o in deletable] == ["ue_super"]
    assert [o["uid"] for o in ambiguous] == ["ue_lonely"]
