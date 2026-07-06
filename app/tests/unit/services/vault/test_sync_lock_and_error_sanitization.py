"""Vault sync hardening — PR 5 of the 2026-07-05 vault security arc.

Part A — per-root concurrency lock: ``VaultReconciler.sync`` serializes
concurrent syncs of the SAME resolved vault root (the second waits, it never
errors), while syncs of DIFFERENT roots never block each other.

Part B — error-path sanitization: ``VaultSyncStats.errors``/``.warnings``
reach the HTMX fragment and the JSON API verbatim, so they must never embed
the vault root's absolute host path — paths render vault-relative (or bare
basename), and the full absolute detail lives in logs only.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.config import SyncAllowlist
from core.services.ingestion.types import IncrementalStats
from core.services.vault.vault_descriptor import (
    VaultDescriptor,
    VaultKind,
    VaultRegistry,
)
from core.services.vault.vault_reconciler import VaultReconciler
from core.utils.path_display import display_path, strip_root_prefix
from core.utils.result_simplified import Result

OWNER = UserUID("user_owner")
ADMIN = UserUID("user_admin")


# =========================================================================
# Fixtures / builders
# =========================================================================


def _wall(root: Path) -> SyncAllowlist:
    return SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset())


def _descriptor(
    kind: VaultKind, root: Path, owner: str, bridge: VaultBridgePort | None = None
) -> VaultDescriptor:
    return VaultDescriptor(
        kind=kind,
        root=root,
        owner_uid=UserUID(owner),
        allowlist=_wall(root),
        bridge=bridge if bridge is not None else cast("VaultBridgePort", object()),
        supports_task_round_trip=kind is VaultKind.PERSONAL,
    )


def _split_root_registry(tmp_path: Path, personal_bridge: VaultBridgePort | None = None):
    """Split-root config: content and personal are sibling directories."""
    return VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, tmp_path / "content", str(ADMIN)),
        personal=_descriptor(
            VaultKind.PERSONAL, tmp_path / "personal", str(OWNER), bridge=personal_bridge
        ),
    )


def _user_service(*, consent: bool = True) -> Mock:
    user = Mock()
    user.preferences.vault_write_consent = consent
    service = Mock()
    service.get_user = AsyncMock(return_value=Result.ok(user))
    return service


def _reconciler(registry: VaultRegistry, ingestion: Mock, user_entry: Mock | None = None):
    if user_entry is None:
        user_entry = Mock()
        user_entry.list_for_user = AsyncMock(return_value=Result.ok([]))
    return VaultReconciler(
        registry=registry,
        unified_ingestion=ingestion,
        user_entry_service=user_entry,
        tasks_service=Mock(),
        user_service=_user_service(consent=True),
    )


class _BlockingIngestProbe:
    """``ingest_directory`` stand-in that records call overlap and blocks until released.

    Deterministic overlap detection: ``max_active`` > 1 iff two syncs were
    inside ingest at the same time. No timed sleeps in the probe itself.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, *args: object, **kwargs: object) -> Result[None]:
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.entered.set()
        await self.release.wait()
        self.active -= 1
        return Result.ok(None)


# =========================================================================
# Part A — per-root sync lock
# =========================================================================


@pytest.mark.asyncio
async def test_concurrent_syncs_of_same_root_serialize(tmp_path: Path) -> None:
    """Second sync of the SAME root waits at the lock — no interleaving, no error."""
    probe = _BlockingIngestProbe()
    ingestion = Mock()
    ingestion.ingest_directory = probe
    reconciler = _reconciler(_split_root_registry(tmp_path), ingestion)

    first = asyncio.create_task(reconciler.sync(VaultKind.PERSONAL, OWNER))
    await asyncio.wait_for(probe.entered.wait(), timeout=2)

    second = asyncio.create_task(reconciler.sync(VaultKind.PERSONAL, OWNER))
    await asyncio.sleep(0.02)  # let the second task run up to the lock

    # The second sync is parked at the per-root lock: it has NOT entered ingest.
    assert probe.calls == 1
    assert not second.done()

    probe.release.set()
    first_result = await asyncio.wait_for(first, timeout=2)
    second_result = await asyncio.wait_for(second, timeout=2)

    # Both complete OK (the second serialized, it did not error) and the
    # ingest bodies never overlapped.
    assert first_result.is_ok
    assert second_result.is_ok
    assert probe.calls == 2
    assert probe.max_active == 1


@pytest.mark.asyncio
async def test_syncs_of_different_roots_do_not_block(tmp_path: Path) -> None:
    """A CONTENT sync completes while a PERSONAL sync of a different root is mid-ingest."""
    personal_probe = _BlockingIngestProbe()
    personal_root = (tmp_path / "personal").resolve()

    async def _ingest_directory(path: Path, **kwargs: object) -> Result[None]:
        if Path(path).resolve() == personal_root:
            return await personal_probe(path, **kwargs)
        return Result.ok(None)

    ingestion = Mock()
    ingestion.ingest_directory = _ingest_directory
    reconciler = _reconciler(_split_root_registry(tmp_path), ingestion)

    personal = asyncio.create_task(reconciler.sync(VaultKind.PERSONAL, OWNER))
    await asyncio.wait_for(personal_probe.entered.wait(), timeout=2)

    # Different root ⇒ different lock: the content sync must run to completion
    # while the personal sync still holds its own root's lock.
    content_result = await asyncio.wait_for(reconciler.sync(VaultKind.CONTENT, ADMIN), timeout=2)
    assert content_result.is_ok
    assert not personal.done()

    personal_probe.release.set()
    assert (await asyncio.wait_for(personal, timeout=2)).is_ok


# =========================================================================
# Part B — error-path sanitization
# =========================================================================


@pytest.mark.asyncio
async def test_read_note_failure_reports_vault_relative_path(tmp_path: Path) -> None:
    """A failed outbound read surfaces `notes/a.md`, never the absolute root."""
    personal_root = (tmp_path / "personal").resolve()
    note_abs = personal_root / "notes" / "a.md"

    bridge = Mock()
    bridge.read_note = AsyncMock(
        side_effect=PermissionError(f"[Errno 13] Permission denied: '{note_abs}'")
    )
    registry = _split_root_registry(tmp_path, personal_bridge=cast("VaultBridgePort", bridge))

    entry = Mock()
    entry.uid = "ue_1"
    entry.metadata = {"vault_file_path": str(note_abs)}
    user_entry = Mock()
    user_entry.list_for_user = AsyncMock(return_value=Result.ok([entry]))
    user_entry.get_extracted_entities = AsyncMock(
        return_value=Result.ok([{"entity_uid": "task_x", "source_line_hash": "h"}])
    )

    ingestion = Mock()
    ingestion.ingest_directory = AsyncMock(return_value=Result.ok(None))
    reconciler = _reconciler(registry, ingestion, user_entry=user_entry)

    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    assert len(result.value.errors) == 1
    error_line = result.value.errors[0]
    assert "read_note failed for notes/a.md" in error_line
    # Pragmatic bar: the vault root's absolute prefix never reaches stats —
    # not in the path we render, not in the OSError text we echo.
    assert str(personal_root) not in error_line


@pytest.mark.asyncio
async def test_ingest_errors_reach_stats_vault_relative(tmp_path: Path) -> None:
    """Ingest error dicts (absolute `file` paths) merge into stats relativized."""
    personal_root = (tmp_path / "personal").resolve()
    ingest_stats = IncrementalStats(
        nodes_created=1,
        files_failed=1,
        errors=[{"file": str(personal_root / "tasks" / "bad.md"), "error": "boom"}],
        warnings=[f"dangling target in {personal_root}/tasks/other.md"],
    )
    ingestion = Mock()
    ingestion.ingest_directory = AsyncMock(return_value=Result.ok(ingest_stats))
    reconciler = _reconciler(_split_root_registry(tmp_path), ingestion)

    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    assert result.value.errors == ["tasks/bad.md: boom"]
    assert result.value.warnings == ["dangling target in tasks/other.md"]
    for line in result.value.errors + result.value.warnings:
        assert str(personal_root) not in line


class TestPathDisplayHelpers:
    """Direct pins on the shared sanitizers (core/utils/path_display.py)."""

    def test_display_path_relative_inside_root(self, tmp_path: Path) -> None:
        assert display_path(tmp_path / "a" / "b.md", tmp_path) == "a/b.md"

    def test_display_path_basename_outside_root(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "elsewhere" / "c.md"
        assert display_path(outside, tmp_path / "vault") == "c.md"

    def test_strip_root_prefix_relativizes_embedded_paths(self, tmp_path: Path) -> None:
        text = f"[Errno 2] No such file or directory: '{tmp_path}/x/y.md'"
        assert strip_root_prefix(text, tmp_path) == (
            "[Errno 2] No such file or directory: 'x/y.md'"
        )

    def test_strip_root_prefix_masks_bare_root(self, tmp_path: Path) -> None:
        assert strip_root_prefix(f"root {tmp_path} vanished", tmp_path) == "root <vault> vanished"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
