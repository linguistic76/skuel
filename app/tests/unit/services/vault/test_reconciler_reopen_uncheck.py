"""A reopen un-checks its vault line — driven by STATE, not by ``TaskReopened``.

``_process_entry_outbound`` already walked every 🆔-bearing task line and read
the task's current status; the un-check is the ``else`` arm of the branch that
queued ``mark_done``. It is state-driven on purpose: ``is_reopen`` is only
knowable after the guarded write returns the prior, so the graph write has
already committed and a failed vault write has no retry. "Not completed AND its
line is still marked done" is re-evaluable on any sync and idempotent.

The gate (``needs_mark_undone``) is what keeps it cheap. Without it the batch
would be non-empty for nearly every file that holds tasks, and every sync would
issue a write RPC per file — a network round-trip each on the ``local_agent``
transport. That is the easy regression, and it is pinned below.
"""

from __future__ import annotations

from datetime import date
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
TASK_UID = "task_reopened_in_skuel"
VAULT_ID = "sk_a1b2c3"

OPEN_LINE = f"- [ ] Ship the fix 🆔 {VAULT_ID}\n"
DONE_LINE = f"- [x] Ship the fix 🆔 {VAULT_ID} ✅ 2026-08-20\n"


def _descriptor(root: Path, bridge: Mock) -> VaultDescriptor:
    return VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=root,
        owner_uid=UserUID(OWNER),
        allowlist=SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset()),
        bridge=cast("VaultBridgePort", bridge),
        supports_task_round_trip=True,
    )


def _reconciler(task: Task, note: str) -> tuple[VaultReconciler, Mock]:
    """A reconciler whose only extracted entity is ``task``, already 🆔-tagged."""
    bridge = Mock()
    bridge.read_note = AsyncMock(return_value=NoteSnapshot.from_content("daily.md", note))
    # A real transport reports one outcome per queued update (protocol v2).
    bridge.write_task_updates = AsyncMock(
        return_value=WriteResult(success=True, updates_applied=(True,))
    )

    user_entry = Mock()
    user_entry.get_extracted_entities = AsyncMock(
        return_value=Result.ok([{"entity_uid": TASK_UID, "vault_id": VAULT_ID}])
    )
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


async def _run(task: Task, note: str, tmp_path: Path) -> tuple[VaultSyncStats, Mock]:
    reconciler, bridge = _reconciler(task, note)
    entry = Mock()
    entry.uid = ENTRY_UID
    entry.metadata = {}
    stats = VaultSyncStats()
    await reconciler._process_entry_outbound(
        _descriptor(tmp_path, bridge), entry, str(tmp_path / "daily.md"), stats
    )
    return stats, bridge


def _open_task() -> Task:
    return Task(
        uid=TASK_UID,
        user_uid=OWNER,
        title="Ship the fix",
        status=EntityStatus.ACTIVE,
        # A stale stamp survives a reopen by design (ADR-087) — the STATUS is
        # what decides the checkbox, never the stamp.
        completion_date=date(2026, 8, 20),
    )


def _completed_task() -> Task:
    return Task(
        uid=TASK_UID,
        user_uid=OWNER,
        title="Ship the fix",
        status=EntityStatus.COMPLETED,
        completion_date=date(2026, 8, 20),
    )


async def test_reopened_task_with_a_checked_line_queues_exactly_one_uncheck(
    tmp_path: Path,
) -> None:
    """The build: a task no longer completed whose line is still ``[x] ✅``."""
    stats, bridge = await _run(_open_task(), DONE_LINE, tmp_path)

    updates = bridge.write_task_updates.await_args.kwargs["updates"]
    assert len(updates) == 1
    assert updates[0].mark_undone is True
    assert updates[0].mark_done is False
    assert updates[0].vault_id == VAULT_ID
    assert updates[0].done_date is None, "an un-check writes no date, it removes one"
    assert stats.tasks_marked_undone == 1
    assert stats.tasks_marked_done == 0
    assert not stats.warnings and not stats.errors, stats


async def test_a_checked_line_without_a_done_date_is_still_unchecked(tmp_path: Path) -> None:
    """Checked in Obsidian without the tasks plugin — the gate is two-part."""
    stats, bridge = await _run(_open_task(), f"- [x] Ship the fix 🆔 {VAULT_ID}\n", tmp_path)

    updates = bridge.write_task_updates.await_args.kwargs["updates"]
    assert len(updates) == 1 and updates[0].mark_undone is True
    assert stats.tasks_marked_undone == 1


async def test_a_stale_done_date_on_an_open_box_is_still_stripped(tmp_path: Path) -> None:
    """The gate's other half: manually un-checked, ✅ date left behind."""
    stats, bridge = await _run(
        _open_task(), f"- [ ] Ship the fix 🆔 {VAULT_ID} ✅ 2026-08-20\n", tmp_path
    )

    updates = bridge.write_task_updates.await_args.kwargs["updates"]
    assert len(updates) == 1 and updates[0].mark_undone is True
    assert stats.tasks_marked_undone == 1


async def test_an_already_unchecked_line_queues_nothing_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """The cost gate (Finding C) — the easy regression, pinned.

    Without it every sync would queue an un-check for every open task, and the
    reconciler calls the write door whenever its batch is non-empty: one write
    RPC per file, per sync, forever, changing nothing.
    """
    stats, bridge = await _run(_open_task(), OPEN_LINE, tmp_path)

    bridge.write_task_updates.assert_not_awaited()
    assert stats.tasks_marked_undone == 0
    assert not stats.warnings and not stats.errors, stats


async def test_a_completed_task_still_marks_done_and_never_both(tmp_path: Path) -> None:
    """The arm that already existed keeps its behaviour — and the two are exclusive."""
    stats, bridge = await _run(_completed_task(), OPEN_LINE, tmp_path)

    updates = bridge.write_task_updates.await_args.kwargs["updates"]
    assert len(updates) == 1
    assert updates[0].mark_done is True
    assert updates[0].mark_undone is False
    assert updates[0].done_date == "2026-08-20"
    assert stats.tasks_marked_done == 1
    assert stats.tasks_marked_undone == 0


async def test_a_completed_task_whose_line_is_already_done_writes_nothing(
    tmp_path: Path,
) -> None:
    """The done arm's own steady state: ``mark_done`` is queued, lands as a
    no-op, and — counting what LANDED — reports zero rather than re-reporting
    the same completion on every sync of an unchanged vault.
    """
    reconciler, bridge = _reconciler(_completed_task(), DONE_LINE)
    # What a real transport answers for a no-op update inside a good write.
    bridge.write_task_updates = AsyncMock(
        return_value=WriteResult(success=True, updates_applied=(False,))
    )
    entry = Mock()
    entry.uid = ENTRY_UID
    entry.metadata = {}
    stats = VaultSyncStats()

    await reconciler._process_entry_outbound(
        _descriptor(tmp_path, bridge), entry, str(tmp_path / "daily.md"), stats
    )

    assert stats.tasks_marked_done == 0, "a no-op mark_done is not a task marked done"
    assert not stats.warnings, "an already-done line is ORDINARY, never a warning"


async def test_an_uncheck_that_no_ops_warns_because_its_arm_was_gated(
    tmp_path: Path,
) -> None:
    """A queued un-check is gated on the mutation against THIS snapshot, so a
    successful write that changed nothing means the file moved underneath the
    batch. That is a divergence worth surfacing — unlike a ``mark_done`` no-op,
    which is the steady state of every completed task.
    """
    reconciler, bridge = _reconciler(_open_task(), DONE_LINE)
    bridge.write_task_updates = AsyncMock(
        return_value=WriteResult(success=True, updates_applied=(False,))
    )
    entry = Mock()
    entry.uid = ENTRY_UID
    entry.metadata = {}
    stats = VaultSyncStats()

    await reconciler._process_entry_outbound(
        _descriptor(tmp_path, bridge), entry, str(tmp_path / "daily.md"), stats
    )

    assert stats.tasks_marked_undone == 0
    assert len(stats.warnings) == 1
    assert TASK_UID in stats.warnings[0]
    assert "daily.md" in stats.warnings[0]
    assert str(tmp_path) not in stats.warnings[0], "stats reach the UI — no absolute host paths"
    assert not stats.is_clean, "a divergence must not report 'Sync complete'"


async def test_a_reopen_and_a_completion_in_one_file_each_get_their_own_operation(
    tmp_path: Path,
) -> None:
    """Two tasks, one note, opposite directions — positionally independent."""
    other_uid = "task_still_done"
    other_id = "sk_zzz999"
    note = DONE_LINE + f"- [ ] Second thing 🆔 {other_id}\n"

    reopened = _open_task()
    completed = Task(
        uid=other_uid,
        user_uid=OWNER,
        title="Second thing",
        status=EntityStatus.COMPLETED,
        completion_date=date(2026, 8, 22),
    )

    reconciler, bridge = _reconciler(reopened, note)
    reconciler._user_entry.get_extracted_entities = AsyncMock(
        return_value=Result.ok(
            [
                {"entity_uid": TASK_UID, "vault_id": VAULT_ID},
                {"entity_uid": other_uid, "vault_id": other_id},
            ]
        )
    )

    async def _get_task(uid: str) -> Result[Task]:
        return Result.ok(reopened if uid == TASK_UID else completed)

    reconciler._tasks.get_task = AsyncMock(side_effect=_get_task)
    bridge.write_task_updates = AsyncMock(
        return_value=WriteResult(success=True, updates_applied=(True, True))
    )

    entry = Mock()
    entry.uid = ENTRY_UID
    entry.metadata = {}
    stats = VaultSyncStats()
    await reconciler._process_entry_outbound(
        _descriptor(tmp_path, bridge), entry, str(tmp_path / "daily.md"), stats
    )

    updates = bridge.write_task_updates.await_args.kwargs["updates"]
    assert [(u.vault_id, u.mark_done, u.mark_undone) for u in updates] == [
        (VAULT_ID, False, True),
        (other_id, True, False),
    ]
    assert stats.tasks_marked_undone == 1
    assert stats.tasks_marked_done == 1


async def test_the_uncheck_reaches_the_file_byte_identically_through_a_real_adapter(
    tmp_path: Path,
) -> None:
    """Real mutation, real file: the line returns to what it was before completion."""
    from adapters.vault.filesystem_adapter import FilesystemVaultAdapter

    note = tmp_path / "daily.md"
    original = f"# Daily\n\n{OPEN_LINE}"
    note.write_text(original, encoding="utf-8")

    reconciler, _mock_bridge = _reconciler(_completed_task(), original)
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

    # Sync 1: SKUEL says completed → the line is checked and stamped.
    done_stats = VaultSyncStats()
    await reconciler._process_entry_outbound(descriptor, entry, str(note), done_stats)
    assert done_stats.tasks_marked_done == 1, done_stats
    assert note.read_text(encoding="utf-8") != original

    # Sync 2: the task is reopened → the line goes back, byte for byte.
    reconciler._tasks.get_task = AsyncMock(return_value=Result.ok(_open_task()))
    undo_stats = VaultSyncStats()
    await reconciler._process_entry_outbound(descriptor, entry, str(note), undo_stats)
    assert undo_stats.tasks_marked_undone == 1, undo_stats
    assert note.read_text(encoding="utf-8") == original

    # Sync 3: nothing left to do — no write is even attempted.
    quiet_stats = VaultSyncStats()
    await reconciler._process_entry_outbound(descriptor, entry, str(note), quiet_stats)
    assert quiet_stats.tasks_marked_undone == 0
    assert not quiet_stats.warnings and not quiet_stats.errors, quiet_stats
    assert note.read_text(encoding="utf-8") == original
