"""A minted 🆔 is persisted only when ITS OWN injection landed in the file.

``_process_entry_outbound`` mints a ``vault_id``, queues the line injection,
and afterwards writes the id onto the ``EXTRACTED_FROM`` edge. It used to gate
that persist on FILE-level ``WriteResult.success`` — which says the file was
written, not that a given update found its target line. An injection that
matched no line is a no-op inside a successful write, so the edge would carry a
🆔 the file never received: no later sync can locate the line by it, and that
task's completion write-back silently never happens (deferred-work
§ Phantom-🆔).

``WriteResult.updates_applied`` reports each update's own outcome, positionally
parallel to the batch, and the persist now gates on that.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

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
FIRST_LINE = "- [ ] Ship the fix\n"
SECOND_LINE = "- [ ] Water the plants\n"
TAGGED_LINE = "- [ ] Already tagged 🆔 sk_zz9zz9\n"
NOTE = f"# Daily\n\n{FIRST_LINE}{SECOND_LINE}{TAGGED_LINE}"


def _descriptor(root: Path, bridge: Mock) -> VaultDescriptor:
    return VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=root,
        owner_uid=UserUID(OWNER),
        allowlist=SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset()),
        bridge=cast("VaultBridgePort", bridge),
        supports_task_round_trip=True,
    )


def _reconciler(
    rels: list[dict[str, str | None]], write: WriteResult
) -> tuple[VaultReconciler, Mock, Mock]:
    """A reconciler over ``NOTE`` whose bridge reports ``write`` for the batch."""
    bridge = Mock()
    bridge.read_note = AsyncMock(return_value=NoteSnapshot.from_content("daily.md", NOTE))
    bridge.write_task_updates = AsyncMock(return_value=write)

    user_entry = Mock()
    user_entry.get_extracted_entities = AsyncMock(return_value=Result.ok(rels))
    user_entry.update_extracted_vault_id = AsyncMock(return_value=Result.ok(None))
    user_entry.update_entry = AsyncMock(return_value=Result.ok(Mock()))

    reconciler = VaultReconciler(
        registry=Mock(spec=VaultRegistry),
        unified_ingestion=Mock(),
        user_entry_service=user_entry,
        tasks_service=Mock(),
        user_service=Mock(),
    )
    return reconciler, bridge, user_entry


async def _run(
    rels: list[dict[str, str | None]], write: WriteResult, tmp_path: Path
) -> tuple[VaultSyncStats, Mock, Mock]:
    reconciler, bridge, user_entry = _reconciler(rels, write)
    entry = Mock()
    entry.uid = ENTRY_UID
    entry.metadata = {}
    stats = VaultSyncStats()

    await reconciler._process_entry_outbound(
        _descriptor(tmp_path, bridge), entry, str(tmp_path / "daily.md"), stats
    )
    return stats, bridge, user_entry


_UNUSED = WriteResult(success=False, error="the bridge must not be called at all")


def _rel(entity_uid: str, line: str) -> dict[str, str | None]:
    return {
        "entity_uid": entity_uid,
        "vault_id": None,
        "source_line_hash": normalize_vault_line_hash(line),
    }


async def test_landed_injection_is_persisted(tmp_path: Path) -> None:
    stats, bridge, user_entry = await _run(
        [_rel("task_ship", FIRST_LINE)],
        WriteResult(success=True, new_sha256=None, updates_applied=(True,)),
        tmp_path,
    )

    queued = bridge.write_task_updates.await_args.kwargs["updates"]
    assert len(queued) == 1 and queued[0].inject_vault_id is True
    user_entry.update_extracted_vault_id.assert_awaited_once()
    assert user_entry.update_extracted_vault_id.await_args.args[2] == queued[0].vault_id
    assert stats.ids_injected == 1
    assert stats.is_clean


async def test_noop_injection_inside_a_successful_write_is_not_persisted(
    tmp_path: Path,
) -> None:
    """The defect in one assertion: file-level success, update-level no-op."""
    stats, _bridge, user_entry = await _run(
        [_rel("task_ship", FIRST_LINE)],
        WriteResult(success=True, new_sha256=None, updates_applied=(False,)),
        tmp_path,
    )

    user_entry.update_extracted_vault_id.assert_not_awaited()
    # The count follows the file, not the queue — nothing was injected.
    assert stats.ids_injected == 0
    # And the sync says so rather than reporting "complete" over a divergence.
    assert not stats.is_clean
    assert any("task_ship" in w for w in stats.warnings)


async def test_a_transport_that_reports_no_outcomes_withholds_the_persist(
    tmp_path: Path,
) -> None:
    """Fail-closed: unreported is 'did not land', never 'assume it did'."""
    stats, _bridge, user_entry = await _run(
        [_rel("task_ship", FIRST_LINE)],
        WriteResult(success=True),  # protocol-v1 shape: no per-update outcomes
        tmp_path,
    )

    user_entry.update_extracted_vault_id.assert_not_awaited()
    assert stats.ids_injected == 0


async def test_only_the_injection_that_landed_is_persisted(tmp_path: Path) -> None:
    """Two injections, one hit — the outcomes are read POSITIONALLY."""
    stats, bridge, user_entry = await _run(
        [_rel("task_ship", FIRST_LINE), _rel("task_water", SECOND_LINE)],
        WriteResult(success=True, new_sha256=None, updates_applied=(False, True)),
        tmp_path,
    )

    queued = bridge.write_task_updates.await_args.kwargs["updates"]
    assert len(queued) == 2
    user_entry.update_extracted_vault_id.assert_awaited_once()
    persisted = user_entry.update_extracted_vault_id.await_args.args
    assert persisted[1] == "task_water"
    assert persisted[2] == queued[1].vault_id
    assert stats.ids_injected == 1


async def test_recovery_of_an_id_already_in_the_file_needs_no_write_to_gate_on(
    tmp_path: Path,
) -> None:
    """The vault already carries the 🆔: nothing is queued, and it still persists.

    Gating this on an update outcome would strand a recovery that has no update
    — the write batch below contains only the other task's injection.
    """
    stats, bridge, user_entry = await _run(
        [_rel("task_tagged", TAGGED_LINE), _rel("task_ship", FIRST_LINE)],
        WriteResult(success=True, new_sha256=None, updates_applied=(True,)),
        tmp_path,
    )

    queued = bridge.write_task_updates.await_args.kwargs["updates"]
    assert len(queued) == 1  # only the ID-less line needed a write
    persisted = {
        call.args[1]: call.args[2] for call in user_entry.update_extracted_vault_id.await_args_list
    }
    assert persisted["task_tagged"] == "sk_zz9zz9"  # read out of the file
    assert persisted["task_ship"] == queued[0].vault_id
    # The recovery is not an injection into the file, so it is not counted.
    assert stats.ids_injected == 1


async def test_a_recovery_with_nothing_to_write_still_reaches_neo4j(
    tmp_path: Path,
) -> None:
    """The recovery arm's DEFINING case: the file has the 🆔, Neo4j does not.

    It is reached after a partial-write failure — the id landed in the file and
    the edge update did not (a transient DB error, or an outcome the transport
    could not report). Nothing needs writing on the healing pass, so gating the
    persist on a non-empty write batch made the divergence permanent: no later
    sync could ever locate the line by an id it never learned.
    """
    stats, bridge, user_entry = await _run([_rel("task_tagged", TAGGED_LINE)], _UNUSED, tmp_path)

    bridge.write_task_updates.assert_not_awaited()  # and no pointless write RPC
    user_entry.update_extracted_vault_id.assert_awaited_once()
    assert user_entry.update_extracted_vault_id.await_args.args[1:] == (
        "task_tagged",
        "sk_zz9zz9",
    )
    assert stats.ids_injected == 0  # adopted from the file, not injected into it
    assert stats.is_clean


async def test_a_file_level_write_failure_persists_nothing(tmp_path: Path) -> None:
    """A stale snapshot makes even its recovery 🆔s untrustworthy."""
    stats, _bridge, user_entry = await _run(
        [_rel("task_tagged", TAGGED_LINE), _rel("task_ship", FIRST_LINE)],
        WriteResult(success=False, error="Stale-read guard: file changed since last sync"),
        tmp_path,
    )

    user_entry.update_extracted_vault_id.assert_not_awaited()
    assert stats.ids_injected == 0
    assert any("write_task_updates failed" in e for e in stats.errors)


async def test_the_filesystem_transport_reports_the_hit_and_the_miss_positionally(
    tmp_path: Path,
) -> None:
    """The gate is only as good as what the transport reports — real adapter.

    One injection targets a line that is in the file, the other a hash that
    matches nothing. The write succeeds at file level; ``updates_applied`` is
    what separates them.
    """
    from adapters.vault.filesystem_adapter import FilesystemVaultAdapter
    from core.ports.vault_bridge_protocol import TaskLineUpdate

    note = tmp_path / "daily.md"
    note.write_text(NOTE, encoding="utf-8")
    adapter = FilesystemVaultAdapter(allowed_root=tmp_path)
    snapshot = await adapter.read_note(OWNER, "daily.md")

    write = await adapter.write_task_updates(
        user_uid=OWNER,
        path="daily.md",
        updates=[
            TaskLineUpdate(
                vault_id="sk_miss11",
                inject_vault_id=True,
                source_line_hash=normalize_vault_line_hash("- [ ] Not in this file\n"),
            ),
            TaskLineUpdate(
                vault_id="sk_hit222",
                inject_vault_id=True,
                source_line_hash=normalize_vault_line_hash(FIRST_LINE),
            ),
        ],
        expected_sha256=snapshot.sha256,
    )

    assert write.success is True
    assert write.updates_applied == (False, True)
    assert write.was_applied(1) and not write.was_applied(0)
    written = note.read_text(encoding="utf-8")
    assert "🆔 sk_hit222" in written and "sk_miss11" not in written
