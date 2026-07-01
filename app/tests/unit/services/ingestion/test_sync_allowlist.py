"""Fail-closed vault privacy wall — SyncAllowlist + collect_files integration.

The wall (``SKUEL_VAULT_SYNC_ALLOWED_DIRS``) scopes ingestion to explicitly
allowed folders under the personal vault root. Everything else under the root
(je_* journal staging, templates, loose notes) is walled off; content outside
the root (the admin curriculum vault) is unaffected. ``permits`` is the single
predicate both ingestion doors inherit via
``UnifiedIngestionService.ingest_directory``.
"""

from pathlib import Path

import pytest

from core.services.ingestion.config import (
    SyncAllowlist,
    build_sync_allowlist,
    collect_files,
)

_ENV_VAR = "SKUEL_VAULT_SYNC_ALLOWED_DIRS"


# ---------------------------------------------------------------------------
# SyncAllowlist.permits — the pure predicate
# ---------------------------------------------------------------------------


def _wall(root: Path, *allowed: Path) -> SyncAllowlist:
    return SyncAllowlist(
        governed_root=root.resolve(),
        allowed_dirs=frozenset(a.resolve() for a in allowed),
    )


def test_permits_file_under_allowed_dir(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    allowed = root / "periodic_notes"
    wall = _wall(root, allowed)
    assert wall.permits(allowed / "Daily" / "2026-06-30.md") is True


def test_walls_file_under_root_but_not_allowed(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    wall = _wall(root, root / "periodic_notes")
    # je_raw / templates / loose root notes are all under the root but unlisted.
    assert wall.permits(root / "je_raw" / "archive.md") is False
    assert wall.permits(root / "templates" / "t_daily.md") is False
    assert wall.permits(root / "loose-note.md") is False


def test_permits_file_outside_governed_root(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    wall = _wall(root, root / "periodic_notes")
    # The curriculum content vault is a sibling, outside the governed root.
    assert wall.permits(tmp_path / "content_vault" / "ku.machine-learning.md") is True


def test_fail_closed_empty_allowed_walls_entire_root(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    wall = SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset())
    assert wall.permits(root / "periodic_notes" / "note.md") is False
    assert wall.permits(root / "anything.md") is False
    # Still permits content outside the root.
    assert wall.permits(tmp_path / "elsewhere" / "note.md") is True


def test_traversal_cannot_escape_the_wall(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    wall = _wall(root, root / "periodic_notes")
    # A ".." segment that climbs out of an allowed dir back into a walled one
    # must resolve and be rejected, not slip through lexically.
    sneaky = root / "periodic_notes" / ".." / "je_raw" / "secret.md"
    assert wall.permits(sneaky) is False


# ---------------------------------------------------------------------------
# build_sync_allowlist — env parsing
# ---------------------------------------------------------------------------


def test_build_returns_none_when_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV_VAR, raising=False)
    assert build_sync_allowlist(tmp_path) is None


def test_build_returns_none_when_blank(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV_VAR, "   ")
    assert build_sync_allowlist(tmp_path) is None


def test_build_parses_colon_separated_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "vault"
    a = root / "periodic_notes"
    b = root / "journal_exports"
    monkeypatch.setenv(_ENV_VAR, f"{a}:{b}")
    wall = build_sync_allowlist(root)
    assert wall is not None
    assert wall.governed_root == root.resolve()
    assert wall.allowed_dirs == frozenset({a.resolve(), b.resolve()})


def test_build_colon_only_is_fail_closed_wall_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_ENV_VAR, ":")
    wall = build_sync_allowlist(tmp_path / "vault")
    assert wall is not None
    assert wall.allowed_dirs == frozenset()


# ---------------------------------------------------------------------------
# collect_files — the chokepoint honours the wall
# ---------------------------------------------------------------------------


def test_collect_files_applies_allowlist(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    (root / "periodic_notes").mkdir(parents=True)
    (root / "je_raw").mkdir(parents=True)
    keep = root / "periodic_notes" / "2026-06-30.md"
    walled = root / "je_raw" / "archive.md"
    keep.write_text("- [ ] task", encoding="utf-8")
    walled.write_text("private", encoding="utf-8")

    wall = _wall(root, root / "periodic_notes")
    collected = collect_files(root, allowlist=wall)

    assert keep.resolve() in {p.resolve() for p in collected}
    assert walled.resolve() not in {p.resolve() for p in collected}


def test_collect_files_no_allowlist_keeps_all(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    (root / "je_raw").mkdir(parents=True)
    walled = root / "je_raw" / "archive.md"
    walled.write_text("private", encoding="utf-8")

    collected = collect_files(root, allowlist=None)

    assert walled.resolve() in {p.resolve() for p in collected}
