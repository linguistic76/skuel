"""Fail-closed vault privacy wall — SyncAllowlist + collect_files integration.

The wall scopes ingestion to explicitly allowed folders under the personal vault
root. Everything else under the root (je_* journal staging, templates, loose
notes) is walled off; content outside the root (the admin curriculum vault) is
unaffected. ``permits`` is the single predicate every ingestion path inherits —
the directory scan (``collect_files``) and single-file ingestion (``ingest_file``).
The wall is fail-closed by default: with no ``allowed_dirs`` it opens only the
code-level doorway folders (``_DEFAULT_SYNC_SUBDIRS``) rather than the whole vault.
``allowed_dirs`` is passed in explicitly — never read from the ambient process
environment — so a stale exported var can no longer shadow the intended config.
"""

from pathlib import Path

import pytest

from core.services.ingestion.config import (
    _DEFAULT_SYNC_SUBDIRS,
    SyncAllowlist,
    build_sync_allowlist,
    collect_files,
)


def _default_allowed(root: Path) -> frozenset[Path]:
    """The default doorway folders synced when no allowed_dirs are given (ADR-073)."""
    return frozenset((root / subdir).resolve() for subdir in _DEFAULT_SYNC_SUBDIRS)


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
    from core.services.ingestion.config import is_ingestible_path

    root = tmp_path / "vault"
    (root / "je_raw").mkdir(parents=True)
    outside = tmp_path / "outside" / "secret.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("private", encoding="utf-8")
    link = root / "je_raw" / "secret.md"
    link.symlink_to(outside)

    wall = _wall(root, root / "periodic_notes")
    assert wall.permits(link) is False  # staging-scoped
    assert is_ingestible_path(link, wall) is False  # and rejected as a symlink


def test_symlink_in_allowed_folder_is_rejected(tmp_path: Path) -> None:
    # Kody: a symlink in an ALLOWED folder passes permits() on its lexical name,
    # but its target may be external — is_ingestible_path must reject it before the
    # parser reads the target and ships that content downstream.
    from core.services.ingestion.config import is_ingestible_path

    root = tmp_path / "vault"
    (root / "periodic_notes").mkdir(parents=True)
    external = tmp_path / "external" / "leak.md"
    external.parent.mkdir(parents=True)
    external.write_text("external", encoding="utf-8")
    link = root / "periodic_notes" / "leak.md"
    link.symlink_to(external)

    wall = _wall(root, root / "periodic_notes")
    assert wall.permits(link) is True  # lexically inside an allowed folder
    assert is_ingestible_path(link, wall) is False  # but rejected as a symlink


def test_content_vault_je_folder_not_walled_when_allowlist_active(tmp_path: Path) -> None:
    # Kody: the je_* staging floor is scoped to the governed vault. A folder merely
    # NAMED je_out in an unrelated content tree must ingest normally.
    from core.services.ingestion.config import is_ingestible_path

    personal = tmp_path / "skuel"
    content = tmp_path / "0vault"
    (content / "je_out").mkdir(parents=True)
    content_file = content / "je_out" / "lesson.md"
    content_file.write_text("x", encoding="utf-8")

    wall = _wall(personal, personal / "periodic_notes")  # governs the personal vault only
    assert wall.permits(content_file) is True
    assert is_ingestible_path(content_file, wall) is True
    # ...but je_out UNDER the governed personal vault is still walled.
    assert wall.permits(personal / "je_out" / "t.md") is False


def test_governs(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    wall = _wall(root, root / "periodic_notes")
    assert wall.governs(root) is True
    assert wall.governs(root / "sub") is True  # under the vault
    assert wall.governs(tmp_path) is True  # ancestor (vault under it)
    assert wall.governs(tmp_path / "other_vault") is False  # disjoint tree


# ---------------------------------------------------------------------------
# build_sync_allowlist — explicit allowed_dirs parsing
# ---------------------------------------------------------------------------


def test_build_unset_defaults_to_fail_closed_wall(tmp_path: Path) -> None:
    # Fail-closed by default: no allowed_dirs must NOT mean "ingest everything".
    root = tmp_path / "vault"
    wall = build_sync_allowlist(root)
    assert wall is not None
    assert wall.allowed_dirs == _default_allowed(root)
    assert wall.permits(root / "je_raw" / "x.md") is False  # walled with no config
    assert wall.permits(root / "periodic_notes" / "d.md") is True
    # All doorway folders open by default; a non-doorway folder stays walled.
    assert wall.permits(root / "personal_notes" / "p.md") is True
    assert wall.permits(root / "activity_notes" / "a.md") is True
    assert wall.permits(root / "knowledge" / "k.md") is True
    assert wall.permits(root / "random_folder" / "r.md") is False


def test_build_blank_defaults_to_fail_closed_wall(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    wall = build_sync_allowlist(root, allowed_dirs="   ")
    assert wall is not None
    assert wall.allowed_dirs == _default_allowed(root)


def test_build_single_vault_allows_whole_vault_minus_staging(tmp_path: Path) -> None:
    # When the content vault IS (or is under) the governed root, the default wall
    # would starve curriculum — so allow the WHOLE vault, keeping only the je_*
    # staging floor. governs() must still hold so full-mode reprocesses retract.
    root = tmp_path / "vault"
    wall = build_sync_allowlist(root, content_root=root)
    assert wall.allowed_dirs == frozenset({root.resolve()})
    assert wall.permits(root / "curriculum" / "ku.md") is True  # curriculum ingests
    assert wall.permits(root / "je_out" / "t.md") is False  # staging still walled
    assert wall.governs(root) is True
    # content nested under the governed root is also single-vault
    assert build_sync_allowlist(root, content_root=root / "sub").allowed_dirs == frozenset(
        {root.resolve()}
    )


def test_build_distinct_vaults_get_default_wall(tmp_path: Path) -> None:
    personal = tmp_path / "skuel"
    content = tmp_path / "0vault"
    wall = build_sync_allowlist(personal, content_root=content)
    assert wall is not None
    assert wall.allowed_dirs == _default_allowed(personal)


def test_build_explicit_var_overrides_single_vault_guard(tmp_path: Path) -> None:
    # An explicit allowlist wins even when content_root == governed_root.
    root = tmp_path / "vault"
    wall = build_sync_allowlist(root, allowed_dirs=str(root / "periodic_notes"), content_root=root)
    assert wall is not None
    assert wall.allowed_dirs == frozenset({(root / "periodic_notes").resolve()})


def test_build_parses_colon_separated_dirs(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    a = root / "periodic_notes"
    b = root / "journal_exports"
    wall = build_sync_allowlist(root, allowed_dirs=f"{a}:{b}")
    assert wall is not None
    assert wall.governed_root == root.resolve()
    assert wall.allowed_dirs == frozenset({a.resolve(), b.resolve()})


def test_build_colon_only_is_fail_closed_wall_everything(tmp_path: Path) -> None:
    wall = build_sync_allowlist(tmp_path / "vault", allowed_dirs=":")
    assert wall is not None
    assert wall.allowed_dirs == frozenset()


def test_build_drops_ancestor_allow_dir(tmp_path: Path) -> None:
    # An allow-dir that is an ANCESTOR of the vault root would open the whole
    # vault — it must be dropped, leaving a fail-closed (wall-everything) result.
    root = tmp_path / "outer" / "vault"
    root.mkdir(parents=True)
    wall = build_sync_allowlist(root, allowed_dirs=str(tmp_path / "outer"))  # ancestor
    assert wall is not None
    assert wall.allowed_dirs == frozenset()
    assert wall.permits(root / "anything.md") is False


def test_build_drops_root_itself_and_outside_dirs(tmp_path: Path) -> None:
    # Keep only entries strictly under the governed root: the root itself (opens
    # everything) and a sibling/outside path are both dropped.
    root = tmp_path / "vault"
    good = root / "periodic_notes"
    outside = tmp_path / "elsewhere"
    wall = build_sync_allowlist(root, allowed_dirs=f"{good}:{root}:{outside}")
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


def test_collect_files_no_allowlist_keeps_non_staging_but_walls_staging(tmp_path: Path) -> None:
    # With no privacy allowlist, ordinary files are kept — but the je_* staging
    # floor still applies unconditionally (Codex R3: je_out must never auto-sync
    # even in the single-vault fallback where no allowlist is built).
    root = tmp_path / "vault"
    (root / "notes").mkdir(parents=True)
    (root / "je_out").mkdir(parents=True)
    kept = root / "notes" / "note.md"
    staging = root / "je_out" / "transcript.md"
    kept.write_text("x", encoding="utf-8")
    staging.write_text("x", encoding="utf-8")

    collected = {p.resolve() for p in collect_files(root, allowlist=None)}
    assert kept.resolve() in collected
    assert staging.resolve() not in collected


def test_collect_files_staging_floor_matches_component_exactly(tmp_path: Path) -> None:
    # "je_output" is not a staging folder — only exact je_* components are walled.
    root = tmp_path / "vault"
    (root / "je_output").mkdir(parents=True)
    lookalike = root / "je_output" / "note.md"
    lookalike.write_text("x", encoding="utf-8")

    collected = {p.resolve() for p in collect_files(root, allowlist=None)}
    assert lookalike.resolve() in collected


# ---------------------------------------------------------------------------
# ingest_file — single-file ingestion honours the wall (the /api/ingest/file door)
# ---------------------------------------------------------------------------


def _service_with_wall(wall: SyncAllowlist | None) -> "object":
    from unittest.mock import Mock

    from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService

    svc = UnifiedIngestionService(write_backend=Mock(), bulk_backend=Mock())
    svc.sync_allowlist = wall
    return svc


@pytest.mark.asyncio
async def test_ingest_file_rejects_walled_file(tmp_path: Path) -> None:
    """A walled single file must be refused before any parsing/persistence.

    /api/ingest/file calls ingest_file() directly, bypassing the collect_files
    directory scan — so the wall has to be enforced here too, or a walled file
    slips through. Uses a non-staging folder (templates/) to exercise the
    allowlist branch specifically.
    """
    root = tmp_path / "vault"
    walled = root / "templates" / "t_daily.md"
    walled.parent.mkdir(parents=True)
    walled.write_text("type: user_entry\n", encoding="utf-8")

    svc = _service_with_wall(_wall(root, root / "periodic_notes"))
    result = await svc.ingest_file(walled)  # type: ignore[attr-defined]

    assert result.is_error
    assert "allowlist" in str(result.expect_error()).lower()


@pytest.mark.asyncio
async def test_ingest_file_rejects_staging_even_without_allowlist(tmp_path: Path) -> None:
    """je_* staging files are refused by ingest_file even with no allowlist active.

    This is the Codex R3 single-vault fallback: build_sync_allowlist returns None,
    but /api/ingest/file must still never ingest a je_out transcript.
    """
    root = tmp_path / "vault"
    staging = root / "je_out" / "transcript.md"
    staging.parent.mkdir(parents=True)
    staging.write_text("type: user_entry\n", encoding="utf-8")

    svc = _service_with_wall(None)  # no privacy wall
    result = await svc.ingest_file(staging)  # type: ignore[attr-defined]

    assert result.is_error
    assert "staging" in str(result.expect_error()).lower()


@pytest.mark.asyncio
async def test_ingest_file_rejects_symlink(tmp_path: Path) -> None:
    # Kody: even in an allowed folder, a symlink must be refused (its target may be
    # external) before the parser reads it.
    root = tmp_path / "vault"
    (root / "periodic_notes").mkdir(parents=True)
    external = tmp_path / "ext.md"
    external.write_text("x", encoding="utf-8")
    link = root / "periodic_notes" / "leak.md"
    link.symlink_to(external)

    svc = _service_with_wall(_wall(root, root / "periodic_notes"))
    result = await svc.ingest_file(link)  # type: ignore[attr-defined]

    assert result.is_error
    assert "symlink" in str(result.expect_error()).lower()


@pytest.mark.asyncio
async def test_ingest_directory_upgrades_full_to_smart_when_wall_governs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Kody: full mode skips deletion reconciliation, so on a walled vault it would
    # leave now-private rows. The service upgrades full→smart when the wall governs.
    from core.services.ingestion import unified_ingestion_service as mod
    from core.services.ingestion.types import IngestionStats
    from core.utils.result_simplified import Result

    captured: dict[str, str] = {}

    async def _fake_batch(**kwargs: object) -> Result[IngestionStats]:
        captured["mode"] = str(kwargs["ingestion_mode"])
        return Result.ok(IngestionStats(total_files=0, duration_seconds=0))

    monkeypatch.setattr(mod, "ingest_directory", _fake_batch)

    root = tmp_path / "vault"
    root.mkdir()
    svc = _service_with_wall(_wall(root, root / "periodic_notes"))
    svc.ingestion_backend = object()  # type: ignore[attr-defined]  # non-None enables the upgrade

    await svc.ingest_directory(root, ingestion_mode="full")  # type: ignore[attr-defined]
    assert captured["mode"] == "smart"

    # An ungoverned tree (content vault) keeps full mode.
    captured.clear()
    await svc.ingest_directory(tmp_path / "content", ingestion_mode="full")  # type: ignore[attr-defined]
    assert captured["mode"] == "full"


def test_excluded_dir_walls_inside_open_vault(tmp_path: Path) -> None:
    # Content-vault posture: whole-vault allowlist + an explicit exclusion for
    # the raw reference library (Resources/ — no `type:` frontmatter, never
    # ingestible). Exclusion wins even though the dir nests under the allowed
    # root; everything else stays open.
    root = tmp_path / "vault"
    wall = build_sync_allowlist(
        root, content_root=root, excluded_dirs=frozenset({root / "Resources"})
    )
    assert wall.permits(root / "Resources" / "book" / "chapter1.md") is False
    assert wall.permits(root / "Ku" / "ku_breath.md") is True
    # Outside the governed root the wall never applies, excluded name or not.
    assert wall.permits(tmp_path / "elsewhere" / "Resources" / "x.md") is True


def test_excluded_dirs_default_empty_keeps_behavior(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    wall = build_sync_allowlist(root, content_root=root)
    assert wall.excluded_dirs == frozenset()
    assert wall.permits(root / "Resources" / "book.md") is True


# ---------------------------------------------------------------------------
# je_pro conditional doorway — frontmatter consent gate (ADR-073 amendment)
# ---------------------------------------------------------------------------

_JE_PRO_CONSENTED = "---\ntype: user_entry\npipeline: knowledge\n---\nA developed thought.\n"


def _je_pro_vault(tmp_path: Path) -> tuple[Path, SyncAllowlist]:
    """A personal vault with its default wall (je_pro is a default doorway now)."""
    root = tmp_path / "vault"
    (root / "je_pro").mkdir(parents=True)
    wall = build_sync_allowlist(root, content_root=tmp_path / "0vault")
    return root, wall


def test_default_wall_opens_je_pro_path(tmp_path: Path) -> None:
    # je_pro is in the default doorway set and out of the staging floor; the
    # PATH wall permits it — consent is decided per-file by the gate below.
    root = tmp_path / "vault"
    wall = build_sync_allowlist(root, content_root=tmp_path / "0vault")
    assert wall.permits(root / "je_pro" / "note.md") is True
    # The workshop trio stays unconditionally walled.
    assert wall.permits(root / "je_raw" / "note.md") is False
    assert wall.permits(root / "je_out" / "note.md") is False
    assert wall.permits(root / "je_in" / "note.md") is False


def test_je_pro_bare_file_skipped_with_promotion_warning(tmp_path: Path) -> None:
    from core.services.ingestion.config import collect_files_detailed

    root, wall = _je_pro_vault(tmp_path)
    bare = root / "je_pro" / "styled-output.md"
    bare.write_text("No frontmatter — exemplar half only.", encoding="utf-8")

    collected, skips = collect_files_detailed(root, allowlist=wall)
    assert bare.resolve() not in {p.resolve() for p in collected}
    assert len(skips.warnings) == 1
    assert "pipeline: knowledge" in skips.warnings[0]  # the promotion hint
    assert "styled-output.md" in skips.warnings[0]


def test_je_pro_consented_file_collected(tmp_path: Path) -> None:
    from core.services.ingestion.config import collect_files_detailed

    root, wall = _je_pro_vault(tmp_path)
    consented = root / "je_pro" / "promoted.md"
    consented.write_text(_JE_PRO_CONSENTED, encoding="utf-8")

    collected, skips = collect_files_detailed(root, allowlist=wall)
    assert consented.resolve() in {p.resolve() for p in collected}
    assert skips.warnings == ()


def test_je_pro_exemplar_only_skipped_with_twin_note(tmp_path: Path) -> None:
    from core.services.ingestion.config import collect_files_detailed

    root, wall = _je_pro_vault(tmp_path)
    exemplar = root / "je_pro" / "style-only.md"
    exemplar.write_text(
        "---\ntype: user_entry\npipeline: knowledge\nje_use: exemplar\n---\nStyle.\n",
        encoding="utf-8",
    )

    collected, skips = collect_files_detailed(root, allowlist=wall)
    assert collected == []
    assert len(skips.warnings) == 1
    assert "exemplar" in skips.warnings[0]
    # No je_raw twin shares the stem → gentle unpaired note.
    assert "raw twin" in skips.warnings[0]


def test_je_pro_exemplar_with_raw_twin_omits_twin_note(tmp_path: Path) -> None:
    from core.services.ingestion.config import collect_files_detailed

    root, wall = _je_pro_vault(tmp_path)
    (root / "je_raw").mkdir()
    (root / "je_raw" / "style-only.txt").write_text("raw half", encoding="utf-8")
    exemplar = root / "je_pro" / "style-only.md"
    exemplar.write_text("---\npipeline: knowledge\nje_use: exemplar\n---\nS.\n", encoding="utf-8")

    _, skips = collect_files_detailed(root, allowlist=wall)
    assert len(skips.warnings) == 1
    assert "raw twin" not in skips.warnings[0]


def test_je_pro_understanding_file_collected(tmp_path: Path) -> None:
    from core.services.ingestion.config import collect_files_detailed

    root, wall = _je_pro_vault(tmp_path)
    understanding = root / "je_pro" / "about-me.md"
    understanding.write_text(
        "---\ntype: user_entry\npipeline: knowledge\nje_use: understanding\n---\nMe.\n",
        encoding="utf-8",
    )

    collected, skips = collect_files_detailed(root, allowlist=wall)
    assert understanding.resolve() in {p.resolve() for p in collected}
    assert skips.warnings == ()


def test_je_pro_garbled_je_use_fails_closed(tmp_path: Path) -> None:
    from core.services.ingestion.config import collect_files_detailed

    root, wall = _je_pro_vault(tmp_path)
    garbled = root / "je_pro" / "typo.md"
    garbled.write_text("---\npipeline: knowledge\nje_use: exmplar\n---\nX.\n", encoding="utf-8")

    collected, skips = collect_files_detailed(root, allowlist=wall)
    assert collected == []
    assert len(skips.warnings) == 1
    assert "unrecognized" in skips.warnings[0].lower()


def test_je_pro_consent_narrowing_flips_ingestibility(tmp_path: Path) -> None:
    # THE consent-narrowing hook: is_ingestible_path is the exact predicate
    # deletion reconciliation uses ("a tracked row survives iff its file would
    # still be collected"), so flipping a stored file to exemplar-only must
    # flip this predicate — the reconciler then deletes the node for free.
    from core.services.ingestion.config import is_ingestible_path

    root, wall = _je_pro_vault(tmp_path)
    note = root / "je_pro" / "shared-then-withdrawn.md"
    note.write_text(_JE_PRO_CONSENTED, encoding="utf-8")
    assert is_ingestible_path(note, wall) is True

    note.write_text(
        "---\ntype: user_entry\npipeline: knowledge\nje_use: exemplar\n---\nA developed thought.\n",
        encoding="utf-8",
    )
    assert is_ingestible_path(note, wall) is False

    # Dropping pipeline: entirely also withdraws consent.
    note.write_text("---\ntype: user_entry\n---\nA developed thought.\n", encoding="utf-8")
    assert is_ingestible_path(note, wall) is False


def test_content_vault_je_pro_is_ungoverned(tmp_path: Path) -> None:
    # The consent gate is scoped to the governed personal vault — a content
    # tree folder that happens to be NAMED je_pro ingests normally (same
    # scoping as the staging floor).
    from core.services.ingestion.config import is_ingestible_path

    personal = tmp_path / "skuel"
    content = tmp_path / "0vault"
    (content / "je_pro").mkdir(parents=True)
    bare = content / "je_pro" / "lesson.md"
    bare.write_text("no frontmatter", encoding="utf-8")

    wall = build_sync_allowlist(personal, content_root=content)
    assert is_ingestible_path(bare, wall) is True


def test_single_vault_fallback_gates_je_pro(tmp_path: Path) -> None:
    # No allowlist (single-vault fallback): the whole vault is personal, so the
    # je_pro consent gate applies there too.
    from core.services.ingestion.config import is_ingestible_path

    root = tmp_path / "vault"
    (root / "je_pro").mkdir(parents=True)
    bare = root / "je_pro" / "bare.md"
    bare.write_text("no frontmatter", encoding="utf-8")
    consented = root / "je_pro" / "promoted.md"
    consented.write_text(_JE_PRO_CONSENTED, encoding="utf-8")

    assert is_ingestible_path(bare, None) is False
    assert is_ingestible_path(consented, None) is True


def test_je_pro_yaml_file_gated_too(tmp_path: Path) -> None:
    # .yaml je_pro files carry fields at top level (no --- fences).
    from core.services.ingestion.config import is_ingestible_path

    root, wall = _je_pro_vault(tmp_path)
    consented = root / "je_pro" / "entry.yaml"
    consented.write_text("type: user_entry\npipeline: knowledge\ntitle: T\n", encoding="utf-8")
    bare = root / "je_pro" / "loose.yaml"
    bare.write_text("title: no pipeline\n", encoding="utf-8")

    assert is_ingestible_path(consented, wall) is True
    assert is_ingestible_path(bare, wall) is False
