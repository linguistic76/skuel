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
    backend.delete_edge_with_metadata = AsyncMock(
        return_value=Result.ok([{"file_path": "x"}]),
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
    async def test_deleted_edge_file_removes_relationship(self, tmp_path) -> None:
        """An Edge YAML's tracking row carries the relationship identity —
        deleting the file deletes the relationship."""
        from core.models.relationship_names import RelationshipName

        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        gone_edge = tmp_path / "edge-a-b.yaml"  # never created

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(gone_edge), "entity_uid": "edge:ku.a|RELATED_TO|ku.b"},
            ]
        )

        result = await tracker.reconcile_deletions(tmp_path)
        assert result.is_ok
        assert result.value.edges_deleted == 1
        assert result.value.entities_deleted == 0
        backend.delete_edge_with_metadata.assert_awaited_once_with(
            str(gone_edge), "ku.a", "ku.b", RelationshipName.RELATED_TO
        )
        backend.delete_entities_with_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_unparseable_edge_identity_cleans_tracking_only(self, tmp_path) -> None:
        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        gone_edge = tmp_path / "edge-bad.yaml"

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(gone_edge), "entity_uid": "edge:not-an-identity"},
            ]
        )

        result = await tracker.reconcile_deletions(tmp_path)
        assert result.is_ok
        assert result.value.edges_deleted == 0
        assert result.value.stale_metadata_removed == 1
        backend.delete_edge_with_metadata.assert_not_called()
        backend.delete_ingestion_metadata.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stale_metadata_delete_failure_propagates(self, tmp_path) -> None:
        """A backend failure removing a stale (moved-file) tracking row must
        fail the reconciliation — not report a clean sync."""
        from core.utils.result_simplified import Errors

        new_path = tmp_path / "ku.thing-new.md"
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
        backend.delete_ingestion_metadata = AsyncMock(
            return_value=Result.fail(Errors.database(operation="delete", message="boom"))
        )

        result = await tracker.reconcile_deletions(tmp_path)
        assert result.is_error

    @pytest.mark.asyncio
    async def test_relative_paths_stored_canonical(self, tmp_path, monkeypatch) -> None:
        """Metadata written from a relative path reaches the backend as the
        resolved absolute string — otherwise reconciliation's absolute
        directory-prefix query would never see it and deletions would not
        propagate for relative-path callers."""
        from pathlib import Path

        monkeypatch.chdir(tmp_path)
        target = tmp_path / "ku.rel.md"
        target.write_text("x")

        backend = MagicMock()
        backend.update_ingestion_metadata_batch = AsyncMock(
            return_value=Result.ok([{"updated": 1}])
        )
        tracker = IngestionTracker(backend)

        await tracker.update_ingestion_metadata_batch([(Path("ku.rel.md"), "ku.rel", "hash")])

        items = backend.update_ingestion_metadata_batch.await_args.args[0]
        assert items[0]["file_path"] == str(target.resolve())

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
