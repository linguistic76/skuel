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
    bridge.write_task_updates = AsyncMock(return_value=WriteResult(success=True))

    user_entry = Mock()
    user_entry.get_extracted_entities = AsyncMock(
        return_value=Result.ok([{"entity_uid": TASK_UID, "vault_id": VAULT_ID}])
    )

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
