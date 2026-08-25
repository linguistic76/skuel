"""The Obsidian ``✅ date`` is the completion stamp, not the last touch.

Outbound vault sync marks a SKUEL-completed task done in the user's vault file.
It derived the ``✅ date`` from ``Task.updated_at`` — the mutable proxy the
completion-stamping arc exists to retire. That meant editing a long-done task
rewrote the vault line to today, silently falsifying the user's own record in
their own files.

The reconciler now reads ``Task.completion_date``, the field every completion
path stamps. Only a completion that predates the stamp (and the one-shot
backfill) has none; today's date is the honest floor for those, and it is the
only case where the written date is an approximation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus
from core.models.task.task import Task
from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import NoteSnapshot, VaultBridgePort, WriteResult
from core.services.ingestion.config import SyncAllowlist
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler, VaultSyncStats
from core.utils.result_simplified import Result

pytestmark = pytest.mark.asyncio

OWNER = "user_vault_owner"
ENTRY_UID = "ue_outbound"
TASK_UID = "task_done_in_skuel"
VAULT_ID = "sk_a1b2c3"
NOTE = f"# Daily\n\n- [ ] Ship the fix 🆔 {VAULT_ID}\n"


def _descriptor(root: Path, bridge: Mock) -> VaultDescriptor:
    return VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=root,
        owner_uid=UserUID(OWNER),
        allowlist=SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset()),
        bridge=cast("VaultBridgePort", bridge),
        supports_task_round_trip=True,
    )


def _reconciler(task: Task) -> tuple[VaultReconciler, Mock]:
    """A reconciler whose only extracted entity is ``task``, already 🆔-tagged."""
    bridge = Mock()
    bridge.read_note = AsyncMock(return_value=NoteSnapshot.from_content("daily.md", NOTE))
    # A real transport answers with one outcome per queued update (protocol
    # v2). The outbound counters are settled from those, so a bridge that
    # reported none would under-count by design (fail-closed) — this fixture
    # mirrors the writers, it does not paper over them.
    bridge.write_task_updates = AsyncMock(
        return_value=WriteResult(success=True, updates_applied=(True,))
    )

    user_entry = Mock()
    user_entry.get_extracted_entities = AsyncMock(
        return_value=Result.ok([{"entity_uid": TASK_UID, "vault_id": VAULT_ID}])
    )
    # Reached only when a bridge reports a new content hash (the real adapter
    # does; the Mock bridge above does not).
    user_entry.update_entry = AsyncMock(return_value=Result.ok(Mock()))

    tasks = Mock()
    tasks.get_task = AsyncMock(return_value=Result.ok(task))

    reconciler = VaultReconciler(
        registry=Mock(spec=VaultRegistry),
        unified_ingestion=Mock(),
        user_entry_service=user_entry,
        tasks_service=tasks,
        user_service=Mock(),
    )
    return reconciler, bridge


async def _written_done_date(task: Task, tmp_path: Path) -> str | None:
    reconciler, bridge = _reconciler(task)
    entry = Mock()
    entry.uid = ENTRY_UID
    entry.metadata = {}
    stats = VaultSyncStats()

    await reconciler._process_entry_outbound(
        _descriptor(tmp_path, bridge), entry, str(tmp_path / "daily.md"), stats
    )

    assert stats.tasks_marked_done == 1
    updates = bridge.write_task_updates.await_args.kwargs["updates"]
    assert len(updates) == 1
    assert updates[0].mark_done is True
    return updates[0].done_date


async def test_done_date_is_the_completion_stamp(tmp_path: Path) -> None:
    """A task completed in April writes ``✅ 2026-04-02`` — not today."""
    task = Task(
        uid=TASK_UID,
        user_uid=OWNER,
        title="Ship the fix",
        status=EntityStatus.COMPLETED,
        completion_date=date(2026, 4, 2),
        updated_at=datetime.now(),  # edited since — must not reach the vault
    )

    assert await _written_done_date(task, tmp_path) == "2026-04-02"


async def test_editing_a_long_completed_task_does_not_rewrite_the_vault_date(
    tmp_path: Path,
) -> None:
    """The regression in one assertion: updated_at moves, the ✅ date does not."""
    completed = date.today() - timedelta(days=90)
    task = Task(
        uid=TASK_UID,
        user_uid=OWNER,
        title="Ship the fix",
        status=EntityStatus.COMPLETED,
        completion_date=completed,
        updated_at=datetime.now(),
    )

    written = await _written_done_date(task, tmp_path)
    assert written == completed.isoformat()
    assert written != date.today().isoformat()


async def test_unstamped_completion_falls_back_to_today(tmp_path: Path) -> None:
    """Pre-stamp history the backfill could not reach: today is the honest floor."""
    task = Task(
        uid=TASK_UID,
        user_uid=OWNER,
        title="Closed before the stamp existed",
        status=EntityStatus.COMPLETED,
        completion_date=None,
        updated_at=datetime(2026, 1, 1),
    )

    assert await _written_done_date(task, tmp_path) == date.today().isoformat()


async def test_the_written_back_line_keeps_its_identity(tmp_path: Path) -> None:
    """What the outbound pass writes — ``[x]`` + ``✅ date`` — moves the line's
    hash (the ✅ date is a discriminator, deliberately inside the digest), so
    the next sync's Guard 2 will miss it. The line is recognised by its 🆔
    instead (Guard 2b) — which is only possible if the write-back leaves the
    🆔 intact and the parser still reads it off the written line. Real
    adapter, real mutation (the end-to-end twin lives in
    tests/integration/test_vault_done_date_hash_roundtrip.py).
    """
    from adapters.vault.filesystem_adapter import FilesystemVaultAdapter
    from core.ports.vault_bridge_protocol import normalize_vault_line_hash
    from core.services.dsl.obsidian_tasks_adapter import obsidian_task_line_to_parsed

    note = tmp_path / "daily.md"
    note.write_text(NOTE, encoding="utf-8")
    original_line = NOTE.splitlines()[-1]

    task = Task(
        uid=TASK_UID,
        user_uid=OWNER,
        title="Ship the fix",
        status=EntityStatus.COMPLETED,
        completion_date=date(2026, 4, 2),
    )
    reconciler, _mock_bridge = _reconciler(task)
    descriptor = VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=tmp_path,
        owner_uid=UserUID(OWNER),
        allowlist=SyncAllowlist(governed_root=tmp_path.resolve(), allowed_dirs=frozenset()),
        bridge=FilesystemVaultAdapter(allowed_root=tmp_path),
        supports_task_round_trip=True,
    )
    entry = Mock()
    entry.uid = ENTRY_UID
    entry.metadata = {}
    stats = VaultSyncStats()

    await reconciler._process_entry_outbound(descriptor, entry, str(note), stats)

    assert stats.tasks_marked_done == 1 and not stats.errors, stats
    written_line = note.read_text(encoding="utf-8").splitlines()[-1]
    assert written_line.startswith("- [x]") and "✅ 2026-04-02" in written_line, written_line
    # The hash moved — by design — so identity has to come from the 🆔.
    assert normalize_vault_line_hash(written_line) != normalize_vault_line_hash(original_line)
    parsed = obsidian_task_line_to_parsed(written_line)
    assert parsed is not None and parsed.vault_id == VAULT_ID
    assert parsed.is_checked and parsed.completion_date == date(2026, 4, 2)


async def test_incomplete_task_is_never_marked_done(tmp_path: Path) -> None:
    """The status gate, not the stamp, decides whether the line is checked."""
    task = Task(
        uid=TASK_UID,
        user_uid=OWNER,
        title="Still open",
        status=EntityStatus.ACTIVE,
        completion_date=date(2026, 4, 2),  # stale stamp from a reopen
    )
    reconciler, bridge = _reconciler(task)
    entry = Mock()
    entry.uid = ENTRY_UID
    entry.metadata = {}
    stats = VaultSyncStats()

    await reconciler._process_entry_outbound(
        _descriptor(tmp_path, bridge), entry, str(tmp_path / "daily.md"), stats
    )

    assert stats.tasks_marked_done == 0
    bridge.write_task_updates.assert_not_awaited()
