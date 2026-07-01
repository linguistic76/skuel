"""Fail-closed vault privacy wall — SyncAllowlist + collect_files integration.

The wall (``SKUEL_VAULT_SYNC_ALLOWED_DIRS``) scopes ingestion to explicitly
allowed folders under the personal vault root. Everything else under the root
(je_* journal staging, templates, loose notes) is walled off; content outside
the root (the admin curriculum vault) is unaffected. ``permits`` is the single
predicate every ingestion path inherits — the directory scan (``collect_files``)
and single-file ingestion (``ingest_file``). The wall is fail-closed by default:
an unset env var still walls the personal vault rather than opening it.
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


def test_symlink_in_walled_folder_stays_walled(tmp_path: Path) -> None:
    # A symlink inside a walled folder that points OUTSIDE the vault must not
    # read as "ungoverned" — the wall judges a file by where it sits in the vault,
    # not where its symlink target resolves to.
    root = tmp_path / "vault"
    (root / "je_raw").mkdir(parents=True)
    outside = tmp_path / "outside" / "secret.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("private", encoding="utf-8")
    link = root / "je_raw" / "secret.md"
    link.symlink_to(outside)

    wall = _wall(root, root / "periodic_notes")
    assert wall.permits(link) is False


# ---------------------------------------------------------------------------
# build_sync_allowlist — env parsing
# ---------------------------------------------------------------------------


def test_build_unset_defaults_to_fail_closed_wall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fail-closed by default: an unset env var must NOT mean "ingest everything".
    monkeypatch.delenv(_ENV_VAR, raising=False)
    root = tmp_path / "vault"
    wall = build_sync_allowlist(root)
    assert wall is not None
    assert wall.allowed_dirs == frozenset({(root / "periodic_notes").resolve()})
    assert wall.permits(root / "je_raw" / "x.md") is False  # walled with no config
    assert wall.permits(root / "periodic_notes" / "d.md") is True


def test_build_blank_defaults_to_fail_closed_wall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_ENV_VAR, "   ")
    root = tmp_path / "vault"
    wall = build_sync_allowlist(root)
    assert wall is not None
    assert wall.allowed_dirs == frozenset({(root / "periodic_notes").resolve()})


def test_build_single_vault_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # When the content vault IS (or is nested under) the governed root, a default
    # wall would starve curriculum ingestion — so no wall is applied.
    monkeypatch.delenv(_ENV_VAR, raising=False)
    root = tmp_path / "vault"
    assert build_sync_allowlist(root, content_root=root) is None
    assert build_sync_allowlist(root, content_root=root / "sub") is None


def test_build_distinct_vaults_get_default_wall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_ENV_VAR, raising=False)
    personal = tmp_path / "skuel"
    content = tmp_path / "0vault"
    wall = build_sync_allowlist(personal, content_root=content)
    assert wall is not None
    assert wall.allowed_dirs == frozenset({(personal / "periodic_notes").resolve()})


def test_build_explicit_var_overrides_single_vault_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An explicit allowlist wins even when content_root == governed_root.
    root = tmp_path / "vault"
    monkeypatch.setenv(_ENV_VAR, str(root / "periodic_notes"))
    wall = build_sync_allowlist(root, content_root=root)
    assert wall is not None
    assert wall.allowed_dirs == frozenset({(root / "periodic_notes").resolve()})


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


def test_build_drops_ancestor_allow_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # An allow-dir that is an ANCESTOR of the vault root would open the whole
    # vault — it must be dropped, leaving a fail-closed (wall-everything) result.
    root = tmp_path / "outer" / "vault"
    root.mkdir(parents=True)
    monkeypatch.setenv(_ENV_VAR, str(tmp_path / "outer"))  # ancestor of root
    wall = build_sync_allowlist(root)
    assert wall is not None
    assert wall.allowed_dirs == frozenset()
    assert wall.permits(root / "anything.md") is False


def test_build_drops_root_itself_and_outside_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Keep only entries strictly under the governed root: the root itself (opens
    # everything) and a sibling/outside path are both dropped.
    root = tmp_path / "vault"
    good = root / "periodic_notes"
    outside = tmp_path / "elsewhere"
    monkeypatch.setenv(_ENV_VAR, f"{good}:{root}:{outside}")
    wall = build_sync_allowlist(root)
    assert wall is not None
    assert wall.allowed_dirs == frozenset({good.resolve()})


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


# ---------------------------------------------------------------------------
# ingest_file — single-file ingestion honours the wall (the /api/ingest/file door)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_file_rejects_walled_file(tmp_path: Path) -> None:
    """A walled single file must be refused before any parsing/persistence.

    /api/ingest/file calls ingest_file() directly, bypassing the collect_files
    directory scan — so the wall has to be enforced here too, or a walled file
    (e.g. je_raw/) slips through.
    """
    from unittest.mock import Mock

    from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService

    root = tmp_path / "vault"
    walled = root / "je_raw" / "secret.md"
    walled.parent.mkdir(parents=True)
    walled.write_text("type: user_entry\n", encoding="utf-8")

    svc = UnifiedIngestionService(write_backend=Mock(), bulk_backend=Mock())
    svc.sync_allowlist = _wall(root, root / "periodic_notes")

    result = await svc.ingest_file(walled)

    assert result.is_error
    assert "allowlist" in str(result.expect_error()).lower()
