"""SKUEL's own outbound writes advance the edge's base (R4 PR 2, C1).

The base (``EXTRACTED_FROM.source_line``) is the line as SKUEL last saw it.
An outbound ``[x] ✅`` write, an un-check, or a 🆔 injection changes the line
AFTER the note's ingest — so without this, the next ingest would read SKUEL's
own write as a vault-side edit. Harmless when the task still agrees with it (a
tie); wrong the moment the task moved again in SKUEL between the write and the
ingest: a task reopened after its ``[x] ✅`` landed would be re-completed by its
own write-back. So each landed mutation is applied to the BASE too — the same
pure function the file took, not a copy of the file line — and base + digest
advance to the result. A vault edit sitting on the line stays a diff.
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
from core.ports.vault_bridge_protocol import (
    NoteSnapshot,
    VaultBridgePort,
    WriteResult,
    normalize_vault_line_hash,
)
from core.services.ingestion.config import SyncAllowlist
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler, VaultSyncStats
from core.utils.result_simplified import Result

pytestmark = pytest.mark.asyncio

OWNER = "user_vault_owner"
ENTRY_UID = "ue_outbound"
TASK_UID = "task_own_write"
VAULT_ID = "sk_a1b2c3"
DONE = date(2026, 8, 20)

OPEN_LINE = f"- [ ] Ship the fix 🆔 {VAULT_ID}"
DONE_LINE = f"- [x] Ship the fix 🆔 {VAULT_ID} ✅ {DONE.isoformat()}"


def _descriptor(root: Path, bridge: Mock) -> VaultDescriptor:
    return VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=root,
        owner_uid=UserUID(OWNER),
        allowlist=SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset()),
        bridge=cast("VaultBridgePort", bridge),
        supports_task_round_trip=True,
    )


def _task(status: EntityStatus) -> Task:
    return Task(
        uid=TASK_UID,
        user_uid=OWNER,
        title="Ship the fix",
        status=status,
        completion_date=DONE if status == EntityStatus.COMPLETED else None,
    )


async def _run(
    task: Task,
    note: str,
    *,
    edge: dict,
    applied: tuple[bool, ...] = (True,),
    tmp_path: Path,
) -> tuple[VaultSyncStats, Mock, Mock]:
    bridge = Mock()
    bridge.read_note = AsyncMock(return_value=NoteSnapshot.from_content("daily.md", note))
    bridge.write_task_updates = AsyncMock(
        return_value=WriteResult(success=True, new_sha256="abc", updates_applied=applied)
    )
    user_entry = Mock()
    user_entry.get_extracted_entities = AsyncMock(return_value=Result.ok([edge]))
    user_entry.update_entry = AsyncMock(return_value=Result.ok(Mock()))
    user_entry.update_extracted_vault_id = AsyncMock(return_value=Result.ok(True))
    user_entry.advance_extracted_from_links = AsyncMock(return_value=Result.ok(1))
    tasks = Mock()
    tasks.get_task = AsyncMock(return_value=Result.ok(task))
    reconciler = VaultReconciler(
        registry=Mock(spec=VaultRegistry),
        unified_ingestion=Mock(),
        user_entry_service=user_entry,
        tasks_service=tasks,
        user_service=Mock(),
    )
    entry = Mock()
    entry.uid = ENTRY_UID
    entry.metadata = {}
    stats = VaultSyncStats()
    await reconciler._process_entry_outbound(
        _descriptor(tmp_path, bridge), entry, str(tmp_path / "daily.md"), stats
    )
    return stats, bridge, user_entry


def _edge(
    base: str | None, *, vault_id: str | None = VAULT_ID, line_hash: str | None = None
) -> dict:
    return {
        "entity_uid": TASK_UID,
        "vault_id": vault_id,
        "source_line_hash": line_hash or normalize_vault_line_hash(base or OPEN_LINE),
        "source_line": base,
    }


async def test_a_done_write_back_advances_the_base_to_the_written_line(tmp_path: Path) -> None:
    stats, _bridge, user_entry = await _run(
        _task(EntityStatus.COMPLETED), OPEN_LINE + "\n", edge=_edge(OPEN_LINE), tmp_path=tmp_path
    )
    assert stats.tasks_marked_done == 1
    user_entry.advance_extracted_from_links.assert_awaited_once_with(
        ENTRY_UID, [(TASK_UID, normalize_vault_line_hash(DONE_LINE), VAULT_ID, DONE_LINE)]
    )


async def test_an_uncheck_advances_the_base_to_the_restored_line(tmp_path: Path) -> None:
    stats, _bridge, user_entry = await _run(
        _task(EntityStatus.ACTIVE), DONE_LINE + "\n", edge=_edge(DONE_LINE), tmp_path=tmp_path
    )
    assert stats.tasks_marked_undone == 1
    user_entry.advance_extracted_from_links.assert_awaited_once_with(
        ENTRY_UID, [(TASK_UID, normalize_vault_line_hash(OPEN_LINE), VAULT_ID, OPEN_LINE)]
    )


async def test_the_mutation_is_applied_to_the_base_not_copied_from_the_file(
    tmp_path: Path,
) -> None:
    """The file line carries a vault retitle the ingest has not reconciled
    (its ingest failed this sync). The done write lands on the file; the base
    takes the same mutation on ITS text — so the retitle stays a diff for the
    next ingest instead of being absorbed as already seen."""
    edited = f"- [ ] Ship the fix today 🆔 {VAULT_ID}"
    stats, _bridge, user_entry = await _run(
        _task(EntityStatus.COMPLETED), edited + "\n", edge=_edge(OPEN_LINE), tmp_path=tmp_path
    )
    assert stats.tasks_marked_done == 1
    [(_entry, [(_uid, _hash, _vid, new_base)])] = [
        user_entry.advance_extracted_from_links.await_args.args
    ]
    assert new_base == DONE_LINE, new_base
    assert "today" not in new_base


async def test_an_injection_advances_the_base_after_the_id_is_persisted(tmp_path: Path) -> None:
    """The base was seeded from the pre-injection line; the injected 🆔 is
    SKUEL's own write, appended to the base the same way — keyed on the 🆔
    the persist has just written, so it runs after it."""
    seed = "- [ ] Ship the fix"
    stats, _bridge, user_entry = await _run(
        _task(EntityStatus.DRAFT),
        seed + "\n",
        edge=_edge(seed, vault_id=None),
        tmp_path=tmp_path,
    )
    assert stats.ids_injected == 1
    user_entry.update_extracted_vault_id.assert_awaited_once()
    minted = user_entry.update_extracted_vault_id.await_args.args[2]
    user_entry.advance_extracted_from_links.assert_awaited_once_with(
        ENTRY_UID,
        [(TASK_UID, normalize_vault_line_hash(seed), minted, f"{seed} 🆔 {minted}")],
    )


async def test_an_edge_without_a_base_is_not_advanced(tmp_path: Path) -> None:
    _stats, _bridge, user_entry = await _run(
        _task(EntityStatus.COMPLETED), OPEN_LINE + "\n", edge=_edge(None), tmp_path=tmp_path
    )
    user_entry.advance_extracted_from_links.assert_not_awaited()


async def test_an_update_that_did_not_land_advances_nothing(tmp_path: Path) -> None:
    _stats, _bridge, user_entry = await _run(
        _task(EntityStatus.COMPLETED),
        OPEN_LINE + "\n",
        edge=_edge(OPEN_LINE),
        applied=(False,),
        tmp_path=tmp_path,
    )
    user_entry.advance_extracted_from_links.assert_not_awaited()


async def test_a_mutation_that_does_not_apply_to_the_base_leaves_it(tmp_path: Path) -> None:
    """The base holds no 🆔 (seeded before injection, the persist landed but
    the base never caught up): ``mark_done`` cannot find its line in the base.
    Held — the next ingest brings it current — never guessed."""
    seed = "- [ ] Ship the fix"
    _stats, _bridge, user_entry = await _run(
        _task(EntityStatus.COMPLETED),
        OPEN_LINE + "\n",
        edge=_edge(seed, line_hash=normalize_vault_line_hash(seed)),
        tmp_path=tmp_path,
    )
    user_entry.advance_extracted_from_links.assert_not_awaited()
