"""Pure-filter tests for scripts/cleanup_untracked_vault_entries.py.

The script is a CLI over the live graph; ``select_orphans`` is the pure
criterion (uid-less vault UserEntry, no live tracker row, no turn-in edge) and
is pinned here against fixture rows. Contract:
/plans/uidless-vault-entry-identity-upsert.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from cleanup_untracked_vault_entries import select_orphans  # type: ignore[import-not-found]


def _row(uid, *, vault=True, tracked_marker=None, has_fulfills=False, pipeline="knowledge"):
    meta = json.dumps({"vault_file_path": f"/vault/{uid}.md"}) if vault else json.dumps({})
    return {"uid": uid, "metadata": meta, "pipeline": pipeline, "has_fulfills": has_fulfills}


def test_selects_untracked_vault_entry():
    rows = [_row("ue_orphan")]
    orphans = select_orphans(rows, tracked_uids=set())
    assert [o["uid"] for o in orphans] == ["ue_orphan"]
    assert orphans[0]["vault_file_path"] == "/vault/ue_orphan.md"


def test_tracked_entry_is_kept():
    rows = [_row("ue_live")]
    assert select_orphans(rows, tracked_uids={"ue_live"}) == []


def test_turn_in_copy_is_kept():
    """Belt-and-braces: a FULFILLS_EXERCISE-bearing entry is never deleted."""
    rows = [_row("ue_turnin", has_fulfills=True)]
    assert select_orphans(rows, tracked_uids=set()) == []


def test_entry_without_vault_path_is_kept():
    """A non-vault UserEntry (no vault_file_path key) is out of scope."""
    rows = [_row("ue_form", vault=False)]
    assert select_orphans(rows, tracked_uids=set()) == []


def test_null_or_malformed_metadata_is_kept():
    rows = [
        {"uid": "ue_none", "metadata": None, "pipeline": "knowledge", "has_fulfills": False},
        {"uid": "ue_bad", "metadata": "{not json", "pipeline": "knowledge", "has_fulfills": False},
    ]
    assert select_orphans(rows, tracked_uids=set()) == []


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
    assert select_orphans(rows, tracked_uids=set()) == []
