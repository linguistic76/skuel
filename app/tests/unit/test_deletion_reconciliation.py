"""Unit tests for IngestionTracker.reconcile_deletions.

Deletion propagation ruling (2026-06-12): a vault file deleted means the graph
entity is deleted. Covers the happy path, the moved/renamed-file guard (stale
metadata only), the mass-deletion safety valve, and the no-op cases.

Backend is mocked; file existence is real (tmp_path) since the tracker checks
the filesystem directly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.ingestion.ingestion_tracker import IngestionTracker
from core.utils.result_simplified import Result


def _tracker_with_tracked(rows: list[dict]) -> tuple[IngestionTracker, MagicMock]:
    backend = MagicMock()
    backend.get_tracked_files_under = AsyncMock(return_value=Result.ok(rows))
    backend.delete_entities_with_metadata = AsyncMock(
        side_effect=_echo_items_as_result,
    )
    backend.delete_ingestion_metadata = AsyncMock(
        return_value=Result.ok([{"deleted": 1}]),
    )
    return IngestionTracker(backend), backend


async def _echo_items_as_result(items: list[dict]) -> Result[list[dict]]:
    return Result.ok(items)


class TestReconcileDeletions:
    @pytest.mark.asyncio
    async def test_missing_file_deletes_entity(self, tmp_path) -> None:
        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        gone = tmp_path / "ku.gone.md"  # never created

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(gone), "entity_uid": "ku.gone"},
            ]
        )

        result = await tracker.reconcile_deletions(tmp_path)
        assert result.is_ok
        assert result.value.entities_deleted == 1
        assert result.value.stale_metadata_removed == 0
        assert not result.value.mass_deletion_refused

        items = backend.delete_entities_with_metadata.await_args.args[0]
        assert items == [{"file_path": str(gone), "entity_uid": "ku.gone"}]

    @pytest.mark.asyncio
    async def test_moved_file_removes_stale_metadata_not_entity(self, tmp_path) -> None:
        # Same entity_uid tracked under old (missing) and new (existing) paths
        # — a rename re-ingested under the new path. Entity must survive.
        new_path = tmp_path / "renamed" / "ku.thing.md"
        new_path.parent.mkdir()
        new_path.write_text("x")
        old_path = tmp_path / "ku.thing.md"  # missing
        alive = tmp_path / "ku.other.md"
        alive.write_text("y")

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(old_path), "entity_uid": "ku.thing"},
                {"file_path": str(new_path), "entity_uid": "ku.thing"},
                {"file_path": str(alive), "entity_uid": "ku.other"},
            ]
        )

        result = await tracker.reconcile_deletions(tmp_path)
        assert result.is_ok
        assert result.value.entities_deleted == 0
        assert result.value.stale_metadata_removed == 1
        backend.delete_entities_with_metadata.assert_not_called()
        backend.delete_ingestion_metadata.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mass_deletion_refused(self, tmp_path) -> None:
        # Every tracked file missing at once = unmounted vault / sync wipe.
        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(tmp_path / "a.md"), "entity_uid": "ku.a"},
                {"file_path": str(tmp_path / "b.md"), "entity_uid": "ku.b"},
            ]
        )

        result = await tracker.reconcile_deletions(tmp_path)
        assert result.is_ok
        assert result.value.mass_deletion_refused
        assert result.value.entities_deleted == 0
        backend.delete_entities_with_metadata.assert_not_called()
        backend.delete_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_nothing_tracked_is_noop(self, tmp_path) -> None:
        tracker, backend = _tracker_with_tracked([])
        result = await tracker.reconcile_deletions(tmp_path)
        assert result.is_ok
        assert result.value.entities_deleted == 0
        backend.delete_entities_with_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_files_present_is_noop(self, tmp_path) -> None:
        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        tracker, backend = _tracker_with_tracked(
            [{"file_path": str(alive), "entity_uid": "ku.alive"}]
        )
        result = await tracker.reconcile_deletions(tmp_path)
        assert result.is_ok
        assert result.value.entities_deleted == 0
        backend.delete_entities_with_metadata.assert_not_called()
