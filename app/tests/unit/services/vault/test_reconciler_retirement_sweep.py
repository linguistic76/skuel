"""The end-of-sync retirement sweep (R4 PR 1 + PR 3) — DB-free.

A 🆔 line's disappearance stamps its task (``retired_vault_id``,
``retired_source_line``, ``vault_line_retired_at``); a 🆔 that reappears within
one sync re-links through the extraction branch and the stamp clears there.
What this file pins is the SWEEP that judges the rest at the end of
``VaultReconciler.sync``:

- it lists stamps older than a cutoff read from the DATABASE clock at sync
  start — before ingest, before anything this sync retires;
- terminal tasks and tasks still tracked from another note have their stamp
  cleared; an open, untracked task is CANCELLED through the Tasks facade's
  ``update_task`` (status only — C3, never ``backend.update``) and its stamp
  cleared only when that write returns ok; a refused cancel keeps the stamp
  (the retry record) and warns, naming the task;
- it runs only after a complete inbound pass: any failed file, or any ignored
  file that opted in and could not be read (``files_broken``), holds every
  stamp — terminal ones included — with one warning;
- the content vault (no task round-trip) reads no clock and sweeps nothing.

The graph half — the stamp written by the retiring statement, the sweep read's
``still_tracked`` flag, the keyed clear — is pinned on the container in
``tests/integration/test_vault_inbound_propagation.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.entity_enums import EntityStatus
from core.models.task.task_update_intent import TaskUpdateIntent
from core.models.type_hints import UserUID
from core.ports.query_types import VaultRetiredTaskRow
from core.ports.vault_bridge_protocol import VaultBridgePort, VaultSyncStats
from core.services.ingestion.config import SyncAllowlist
from core.services.ingestion.types import IncrementalStats
from core.services.vault.mirror_sync import MirrorPullStats, VaultMirrorPuller
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler, _merge_ingest_stats
from core.utils.result_simplified import Errors, Result

OWNER = UserUID("user_owner")
ADMIN = UserUID("user_admin")
CLOCK = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


# =========================================================================
# Builders
# =========================================================================


def _registry(tmp_path: Path, mirror_pull: VaultMirrorPuller | None = None) -> VaultRegistry:
    def _descriptor(kind: VaultKind, root: Path, owner: str) -> VaultDescriptor:
        return VaultDescriptor(
            kind=kind,
            root=root,
            owner_uid=UserUID(owner),
            allowlist=SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset()),
            bridge=cast("VaultBridgePort", object()),
            supports_task_round_trip=kind is VaultKind.PERSONAL,
            mirror_pull=mirror_pull if kind is VaultKind.PERSONAL else None,
        )

    return VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, tmp_path / "content", str(ADMIN)),
        personal=_descriptor(VaultKind.PERSONAL, tmp_path / "personal", str(OWNER)),
    )


def _row(uid: str, *, status: EntityStatus, still_tracked: bool = False) -> VaultRetiredTaskRow:
    return {
        "entity_uid": uid,
        "retired_vault_id": f"sk_{uid}",
        "status": status.value,
        "still_tracked": still_tracked,
    }


def _harness(
    tmp_path: Path,
    *,
    pending: list[VaultRetiredTaskRow],
    ingest: IncrementalStats | None = None,
    mirror_pull: VaultMirrorPuller | None = None,
) -> tuple[VaultReconciler, Mock, Mock, list[str]]:
    """A reconciler over mocks that records the ORDER of the reads it makes.

    Returns ``(reconciler, user_entry, tasks, order)`` — ``tasks`` is the
    Tasks facade double every cancel the sweep posts lands on."""
    order: list[str] = []
    user = Mock()
    user.preferences.vault_write_consent = True
    user_service = Mock()
    user_service.get_user = AsyncMock(return_value=Result.ok(user))

    async def _clock() -> Result[datetime]:
        order.append("clock")
        return Result.ok(CLOCK)

    async def _ingest(*_args: object, **_kwargs: object) -> Result[IncrementalStats]:
        order.append("ingest")
        return Result.ok(ingest if ingest is not None else IncrementalStats(nodes_created=1))

    async def _list(_owner: UserUID, _cutoff: datetime) -> Result[list[VaultRetiredTaskRow]]:
        order.append("list")
        return Result.ok(pending)

    user_entry = Mock()
    user_entry.list_for_user = AsyncMock(return_value=Result.ok([]))
    user_entry.read_graph_clock = AsyncMock(side_effect=_clock)
    user_entry.list_vault_retired_tasks = AsyncMock(side_effect=_list)
    user_entry.clear_vault_retirement_stamps = AsyncMock(return_value=Result.ok(0))

    ingestion = Mock()
    ingestion.ingest_directory = AsyncMock(side_effect=_ingest)

    # The Tasks facade's status-guarded door: every cancel the sweep posts
    # lands here. Default: every write is accepted.
    tasks = Mock()
    tasks.update_task = AsyncMock(return_value=Result.ok(Mock()))

    reconciler = VaultReconciler(
        registry=_registry(tmp_path, mirror_pull),
        unified_ingestion=ingestion,
        user_entry_service=user_entry,
        tasks_service=tasks,
        user_service=user_service,
    )
    return reconciler, user_entry, tasks, order


def _cancel_intent(call: object) -> TaskUpdateIntent:
    """The intent one ``update_task`` call carried."""
    _uid, intent = call.args  # type: ignore[attr-defined]
    assert isinstance(intent, TaskUpdateIntent)
    return intent


# =========================================================================
# The sweep
# =========================================================================


@pytest.mark.asyncio
async def test_terminal_and_still_tracked_stamps_clear_open_untracked_is_cancelled(
    tmp_path: Path,
) -> None:
    """Four stamps past the grace: a completed task, a cancelled one, an open
    task still tracked from another note, and an open untracked one. The first
    three never reach the cancel and are cleared; the fourth is cancelled
    through the facade and, the write having landed, cleared in the same
    keyed call. One counter, one clean sync."""
    pending = [
        _row("done", status=EntityStatus.COMPLETED),
        _row("dropped", status=EntityStatus.CANCELLED),
        _row("twice", status=EntityStatus.ACTIVE, still_tracked=True),
        _row("gone", status=EntityStatus.ACTIVE),
    ]
    reconciler, user_entry, tasks, _order = _harness(tmp_path, pending=pending)
    user_entry.clear_vault_retirement_stamps = AsyncMock(return_value=Result.ok(4))

    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    assert [call.args[0] for call in tasks.update_task.await_args_list] == ["gone"], (
        "a terminal or still-tracked task reached the cancel"
    )
    user_entry.clear_vault_retirement_stamps.assert_awaited_once_with(
        OWNER,
        [
            ("done", "sk_done"),
            ("dropped", "sk_dropped"),
            ("twice", "sk_twice"),
            ("gone", "sk_gone"),
        ],
    )
    assert result.value.tasks_cancelled_by_deletion == 1
    assert result.value.retirements_held == 0
    assert result.value.is_clean, (result.value.warnings, result.value.errors)


@pytest.mark.asyncio
async def test_the_cancel_is_a_status_only_intent_through_the_facade(tmp_path: Path) -> None:
    """C3: the write is ``update_task`` on the Tasks facade with an intent
    that sets ``status = cancelled`` and nothing else — the status-guarded
    door decides the transition from the prior it reads under the lock, and
    no other field on the task is touched."""
    reconciler, _user_entry, tasks, _order = _harness(
        tmp_path, pending=[_row("gone", status=EntityStatus.DRAFT)]
    )
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    [call] = tasks.update_task.await_args_list
    assert call.args[0] == "gone"
    assert _cancel_intent(call).to_changes() == {"status": EntityStatus.CANCELLED.value}


@pytest.mark.asyncio
async def test_a_refused_cancel_keeps_the_stamp_and_warns_naming_the_task(
    tmp_path: Path,
) -> None:
    """The stamp is the retry record: a refused write leaves it in place (no
    clear for that task — the next sweep tries again), names the task in a
    warning, and is not counted. A second open task on the same sweep whose
    cancel lands is still cleared and counted."""
    pending = [
        _row("stuck", status=EntityStatus.ACTIVE),
        _row("gone", status=EntityStatus.ACTIVE),
    ]
    reconciler, user_entry, tasks, _order = _harness(tmp_path, pending=pending)

    async def _update(uid: str, _intent: TaskUpdateIntent) -> Result[Mock]:
        if uid == "stuck":
            return Result.fail(Errors.validation("status", "nope"))
        return Result.ok(Mock())

    tasks.update_task = AsyncMock(side_effect=_update)
    user_entry.clear_vault_retirement_stamps = AsyncMock(return_value=Result.ok(1))

    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    user_entry.clear_vault_retirement_stamps.assert_awaited_once_with(OWNER, [("gone", "sk_gone")])
    assert result.value.tasks_cancelled_by_deletion == 1
    [warning] = result.value.warnings
    assert "cancel refused for stuck" in warning and "retried next sync" in warning, warning
    assert not result.value.is_clean


@pytest.mark.asyncio
async def test_every_cancel_refused_clears_nothing(tmp_path: Path) -> None:
    """No landed write, no clear call at all — and no count."""
    reconciler, user_entry, tasks, _order = _harness(
        tmp_path, pending=[_row("stuck", status=EntityStatus.DRAFT)]
    )
    tasks.update_task = AsyncMock(return_value=Result.fail(Errors.database("update_task", "down")))
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    user_entry.clear_vault_retirement_stamps.assert_not_awaited()
    assert result.value.tasks_cancelled_by_deletion == 0
    assert any("cancel refused for stuck" in w for w in result.value.warnings)


@pytest.mark.asyncio
async def test_an_unreadable_status_is_held_not_cancelled(tmp_path: Path) -> None:
    """The sweep cancels what it can read as open, nothing else: a stamp whose
    task carries a status ``EntityStatus`` cannot parse is neither terminal
    nor open — held with a warning naming the task, retried next sync."""
    row: VaultRetiredTaskRow = {
        "entity_uid": "odd",
        "retired_vault_id": "sk_odd",
        "status": "???",
        "still_tracked": False,
    }
    reconciler, user_entry, tasks, _order = _harness(tmp_path, pending=[row])
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    tasks.update_task.assert_not_awaited()
    user_entry.clear_vault_retirement_stamps.assert_not_awaited()
    assert result.value.tasks_cancelled_by_deletion == 0
    [warning] = result.value.warnings
    assert "cancel not attempted for odd" in warning and "unreadable" in warning, warning


@pytest.mark.asyncio
async def test_the_cutoff_is_the_graph_clock_read_before_ingest(tmp_path: Path) -> None:
    """One clock: the cutoff comes from the database (the stamps' own
    ``datetime()``), and it is read BEFORE ingest so nothing this sync retires
    can predate it."""
    reconciler, user_entry, _tasks, order = _harness(
        tmp_path, pending=[_row("done", status=EntityStatus.COMPLETED)]
    )
    await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert order == ["clock", "ingest", "list"]
    user_entry.list_vault_retired_tasks.assert_awaited_once_with(OWNER, CLOCK)


@pytest.mark.asyncio
async def test_nothing_pending_means_no_clear_and_no_warning(tmp_path: Path) -> None:
    reconciler, user_entry, _tasks, _order = _harness(tmp_path, pending=[])
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    user_entry.clear_vault_retirement_stamps.assert_not_awaited()
    assert result.value.is_clean


@pytest.mark.parametrize(
    "ingest",
    [
        pytest.param(
            IncrementalStats(
                files_failed=1,
                errors=[{"file": "/v/personal/notes/a.md", "error": "db", "stage": "ingestion"}],
            ),
            id="system-failure",
        ),
        pytest.param(
            IncrementalStats(
                files_failed=1,
                errors=[{"file": "/v/personal/notes/a.md", "error": "yaml", "stage": "parsing"}],
            ),
            id="broken-frontmatter",
        ),
    ],
)
@pytest.mark.asyncio
async def test_an_incomplete_inbound_pass_holds_every_stamp(
    tmp_path: Path, ingest: IncrementalStats
) -> None:
    """A note that failed to ingest — or opted in and could not be read — has
    not had its say: it may hold the line that would revive a stamped task.
    Nothing is judged, terminal stamps included; one warning names the count."""
    pending = [
        _row("done", status=EntityStatus.COMPLETED),
        _row("gone", status=EntityStatus.ACTIVE),
    ]
    reconciler, user_entry, tasks, _order = _harness(tmp_path, pending=pending, ingest=ingest)
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    user_entry.clear_vault_retirement_stamps.assert_not_awaited()
    tasks.update_task.assert_not_awaited()
    assert result.value.tasks_cancelled_by_deletion == 0
    assert result.value.retirements_held == 2
    assert [w for w in result.value.warnings if "2 vault retirement(s) held" in w], (
        result.value.warnings
    )


@pytest.mark.asyncio
async def test_a_stale_mirror_file_holds_the_sweep(tmp_path: Path) -> None:
    """local_agent transport (Codex P1 on #1343): a file the mirror could not
    bring current — torn read, fetch or write failure — is read stale by the
    ingest, so that note has not had its say either. The refresh reports
    such rows as warnings and keeps the old copy; the sweep must hold on
    them exactly as on a failed file, or a restored line's revival is lost
    and the next clean pull mints a twin."""
    puller = Mock(spec=VaultMirrorPuller)
    puller.refresh = AsyncMock(
        return_value=Result.ok(
            MirrorPullStats(
                fetched=1, stale=1, warnings=["mirror refresh could not fetch 'notes/a.md': …"]
            )
        )
    )
    reconciler, user_entry, tasks, _order = _harness(
        tmp_path, pending=[_row("done", status=EntityStatus.COMPLETED)], mirror_pull=puller
    )
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    assert result.value.mirror_files_stale == 1
    user_entry.clear_vault_retirement_stamps.assert_not_awaited()
    tasks.update_task.assert_not_awaited()
    assert result.value.retirements_held == 1


@pytest.mark.asyncio
async def test_a_loose_note_does_not_hold_the_sweep(tmp_path: Path) -> None:
    """A file with no ``type:`` at all is deliberately not an entity — the
    ingest gate's own verdict. It is ignored on every sync by design, so it
    must not hold the sweep forever."""
    loose = tmp_path / "personal" / "notes" / "loose.md"
    loose.parent.mkdir(parents=True)
    loose.write_text("just a thought\n", encoding="utf-8")
    ingest = IncrementalStats(
        files_failed=1,
        errors=[{"file": str(loose), "error": "no 'type:' field", "stage": "type_detection"}],
    )
    reconciler, user_entry, _tasks, _order = _harness(
        tmp_path, pending=[_row("done", status=EntityStatus.COMPLETED)], ingest=ingest
    )
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    assert result.value.files_ignored == 1
    assert result.value.files_broken == 0
    user_entry.clear_vault_retirement_stamps.assert_awaited_once_with(OWNER, [("done", "sk_done")])
    assert result.value.retirements_held == 0


@pytest.mark.asyncio
async def test_a_listing_failure_is_an_error_not_a_crash(tmp_path: Path) -> None:
    reconciler, user_entry, _tasks, _order = _harness(tmp_path, pending=[])
    user_entry.list_vault_retired_tasks = AsyncMock(
        return_value=Result.fail(Errors.database("list_vault_retired_tasks", "boom"))
    )
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    assert any("retirement sweep failed" in e for e in result.value.errors), result.value.errors
    user_entry.clear_vault_retirement_stamps.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_clock_failure_fails_the_sync_before_ingest(tmp_path: Path) -> None:
    """Without a cutoff the sweep cannot be gated; the sync fails fast rather
    than ingesting and then guessing from the application clock."""
    reconciler, user_entry, _tasks, order = _harness(tmp_path, pending=[])
    user_entry.read_graph_clock = AsyncMock(
        return_value=Result.fail(Errors.database("read_graph_clock", "down"))
    )
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_error
    assert order == []


@pytest.mark.asyncio
async def test_the_content_vault_reads_no_clock_and_sweeps_nothing(tmp_path: Path) -> None:
    reconciler, user_entry, _tasks, order = _harness(tmp_path, pending=[])
    result = await reconciler.sync(VaultKind.CONTENT, ADMIN)

    assert result.is_ok
    assert order == ["ingest"]
    user_entry.read_graph_clock.assert_not_awaited()
    user_entry.list_vault_retired_tasks.assert_not_awaited()


# =========================================================================
# files_broken — the ignored files that hold the sweep
# =========================================================================


def test_files_broken_counts_opted_in_unreadable_files_only(tmp_path: Path) -> None:
    """Among content-fault (ignored) files: a broken fence and a declared type
    with a malformed field are broken — they opted in; a note with no
    ``type:`` is the non-entity verdict and is not. A system fault is a
    failure, not an ignored file, and is counted by ``files_failed``."""
    root = tmp_path / "personal"
    notes = root / "notes"
    notes.mkdir(parents=True)
    (notes / "loose.md").write_text("no frontmatter at all\n", encoding="utf-8")
    (notes / "fence.md").write_text("---\ntype: [unclosed\n---\nbody\n", encoding="utf-8")
    (notes / "typed.md").write_text("---\ntype: task\n---\nbody\n", encoding="utf-8")
    ingest = IncrementalStats(
        files_failed=4,
        errors=[
            {"file": str(notes / "loose.md"), "error": "no type", "stage": "type_detection"},
            {"file": str(notes / "fence.md"), "error": "bad yaml", "stage": "parsing"},
            {"file": str(notes / "typed.md"), "error": "bad field", "stage": "validation"},
            {"file": str(notes / "io.md"), "error": "unreadable", "stage": "file_io"},
        ],
    )
    stats = VaultSyncStats()
    _merge_ingest_stats(stats, ingest, root)

    assert stats.files_ignored == 3
    assert stats.files_broken == 2
    assert stats.files_failed == 1
