"""The end-of-sync retirement sweep (R4 PR 1) — DB-free.

A 🆔 line's disappearance stamps its task (``retired_vault_id``,
``retired_source_line``, ``vault_line_retired_at``); a 🆔 that reappears within
one sync re-links through the extraction branch and the stamp clears there.
What this file pins is the SWEEP that judges the rest at the end of
``VaultReconciler.sync``:

- it lists stamps older than a cutoff read from the DATABASE clock at sync
  start — before ingest, before anything this sync retires;
- terminal tasks and tasks still tracked from another note have their stamp
  cleared; an open, untracked task's stamp is LEFT (the cancel consequence is
  PR 3's — clearing deletion evidence before any consequence exists would make
  every line deleted meanwhile indistinguishable from a pre-🆔-era orphan);
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
from core.models.type_hints import UserUID
from core.ports.query_types import VaultRetiredTaskRow
from core.ports.vault_bridge_protocol import VaultBridgePort, VaultSyncStats
from core.services.ingestion.config import SyncAllowlist
from core.services.ingestion.types import IncrementalStats
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler, _merge_ingest_stats
from core.utils.result_simplified import Errors, Result

OWNER = UserUID("user_owner")
ADMIN = UserUID("user_admin")
CLOCK = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


# =========================================================================
# Builders
# =========================================================================


def _registry(tmp_path: Path) -> VaultRegistry:
    def _descriptor(kind: VaultKind, root: Path, owner: str) -> VaultDescriptor:
        return VaultDescriptor(
            kind=kind,
            root=root,
            owner_uid=UserUID(owner),
            allowlist=SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset()),
            bridge=cast("VaultBridgePort", object()),
            supports_task_round_trip=kind is VaultKind.PERSONAL,
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
) -> tuple[VaultReconciler, Mock, list[str]]:
    """A reconciler over mocks that records the ORDER of the reads it makes."""
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

    reconciler = VaultReconciler(
        registry=_registry(tmp_path),
        unified_ingestion=ingestion,
        user_entry_service=user_entry,
        tasks_service=Mock(),
        user_service=user_service,
    )
    return reconciler, user_entry, order


# =========================================================================
# The sweep
# =========================================================================


@pytest.mark.asyncio
async def test_terminal_and_still_tracked_stamps_clear_open_untracked_stays(
    tmp_path: Path,
) -> None:
    """Four stamps past the grace: a completed task, a cancelled one, an open
    task still tracked from another note, and an open untracked one. The first
    three are cleared in one keyed call; the fourth is left for PR 3."""
    pending = [
        _row("done", status=EntityStatus.COMPLETED),
        _row("dropped", status=EntityStatus.CANCELLED),
        _row("twice", status=EntityStatus.ACTIVE, still_tracked=True),
        _row("gone", status=EntityStatus.ACTIVE),
    ]
    reconciler, user_entry, _order = _harness(tmp_path, pending=pending)
    user_entry.clear_vault_retirement_stamps = AsyncMock(return_value=Result.ok(3))

    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    user_entry.clear_vault_retirement_stamps.assert_awaited_once_with(
        OWNER, [("done", "sk_done"), ("dropped", "sk_dropped"), ("twice", "sk_twice")]
    )
    assert result.value.retirements_held == 0
    assert result.value.is_clean, (result.value.warnings, result.value.errors)


@pytest.mark.asyncio
async def test_an_open_untracked_stamp_alone_clears_nothing(tmp_path: Path) -> None:
    """Deletion evidence with no consequence to apply yet: no clear call at all."""
    reconciler, user_entry, _order = _harness(
        tmp_path, pending=[_row("gone", status=EntityStatus.DRAFT)]
    )
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    user_entry.clear_vault_retirement_stamps.assert_not_awaited()
    assert result.value.is_clean


@pytest.mark.asyncio
async def test_the_cutoff_is_the_graph_clock_read_before_ingest(tmp_path: Path) -> None:
    """One clock: the cutoff comes from the database (the stamps' own
    ``datetime()``), and it is read BEFORE ingest so nothing this sync retires
    can predate it."""
    reconciler, user_entry, order = _harness(
        tmp_path, pending=[_row("done", status=EntityStatus.COMPLETED)]
    )
    await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert order == ["clock", "ingest", "list"]
    user_entry.list_vault_retired_tasks.assert_awaited_once_with(OWNER, CLOCK)


@pytest.mark.asyncio
async def test_nothing_pending_means_no_clear_and_no_warning(tmp_path: Path) -> None:
    reconciler, user_entry, _order = _harness(tmp_path, pending=[])
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
    reconciler, user_entry, _order = _harness(tmp_path, pending=pending, ingest=ingest)
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    user_entry.clear_vault_retirement_stamps.assert_not_awaited()
    assert result.value.retirements_held == 2
    assert [w for w in result.value.warnings if "2 vault retirement(s) held" in w], (
        result.value.warnings
    )


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
    reconciler, user_entry, _order = _harness(
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
    reconciler, user_entry, _order = _harness(tmp_path, pending=[])
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
    reconciler, user_entry, order = _harness(tmp_path, pending=[])
    user_entry.read_graph_clock = AsyncMock(
        return_value=Result.fail(Errors.database("read_graph_clock", "down"))
    )
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_error
    assert order == []


@pytest.mark.asyncio
async def test_the_content_vault_reads_no_clock_and_sweeps_nothing(tmp_path: Path) -> None:
    reconciler, user_entry, order = _harness(tmp_path, pending=[])
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
