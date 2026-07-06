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
    backend.get_entity_owner_uids = AsyncMock(return_value=Result.ok([]))
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
    async def test_scoped_run_refused_when_vault_globally_gone(self, tmp_path) -> None:
        """The valve is global: even a scoped run refuses when NO tracked file
        under the directory exists (unmounted vault), in or out of scope."""
        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(tmp_path / "a.md"), "entity_uid": "ku.a"},
                {"file_path": str(tmp_path / "b.yaml"), "entity_uid": "task.b"},
            ]
        )

        result = await tracker.reconcile_deletions(tmp_path, pattern="*.md")
        assert result.is_ok
        assert result.value.mass_deletion_refused
        backend.delete_entities_with_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_scoped_wipe_propagates_when_out_of_scope_file_exists(self, tmp_path) -> None:
        """100% of in-scope files missing is NOT a vault wipe when an
        out-of-scope tracked file still exists — in-scope deletions propagate."""
        alive_yaml = tmp_path / "task.alive.yaml"
        alive_yaml.write_text("x")

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(tmp_path / "a.md"), "entity_uid": "ku.a"},
                {"file_path": str(tmp_path / "b.md"), "entity_uid": "ku.b"},
                {"file_path": str(alive_yaml), "entity_uid": "task.alive"},
            ]
        )

        result = await tracker.reconcile_deletions(tmp_path, pattern="*.md")
        assert result.is_ok
        assert not result.value.mass_deletion_refused
        assert result.value.entities_deleted == 2
        items = backend.delete_entities_with_metadata.await_args.args[0]
        assert {item["entity_uid"] for item in items} == {"ku.a", "ku.b"}

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
    async def test_pattern_scope_protects_out_of_scope_rows(self, tmp_path) -> None:
        """A *.md-scoped run has no authority over tracked YAML files — a
        missing yaml row is ignored, only the missing md row is deleted."""
        alive_md = tmp_path / "ku.alive.md"
        alive_md.write_text("x")
        gone_md = tmp_path / "ku.gone.md"  # missing, in scope
        gone_yaml = tmp_path / "task.gone.yaml"  # missing, OUT of scope

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive_md), "entity_uid": "ku.alive"},
                {"file_path": str(gone_md), "entity_uid": "ku.gone"},
                {"file_path": str(gone_yaml), "entity_uid": "task.gone"},
            ]
        )

        result = await tracker.reconcile_deletions(tmp_path, pattern="*.md")
        assert result.is_ok
        assert result.value.entities_deleted == 1

        items = backend.delete_entities_with_metadata.await_args.args[0]
        assert items == [{"file_path": str(gone_md), "entity_uid": "ku.gone"}]

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


class TestReconcileDeletionsOwnerScope:
    """Owner-scoped deletion (per-user vault roots follow-up): a descriptor-
    governed sync must never delete an entity owned by a DIFFERENT user than
    the vault's owner — path prefix alone decided deletion before per-user
    roots. Foreign-owned rows are skipped (entity + tracking row survive) and
    surfaced via ownership_mismatches; ownerless SHARED entities and Edge
    YAMLs stay path-scoped."""

    @pytest.mark.asyncio
    async def test_unscoped_run_never_queries_owners(self, tmp_path) -> None:
        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        gone = tmp_path / "task.gone.yaml"

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(gone), "entity_uid": "task_gone_abc"},
            ]
        )

        result = await tracker.reconcile_deletions(tmp_path)  # owner_uid=None
        assert result.is_ok
        assert result.value.entities_deleted == 1
        backend.get_entity_owner_uids.assert_not_called()

    @pytest.mark.asyncio
    async def test_vault_owner_entity_deleted(self, tmp_path) -> None:
        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        gone = tmp_path / "task.gone.yaml"

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(gone), "entity_uid": "task_gone_abc"},
            ]
        )
        backend.get_entity_owner_uids = AsyncMock(
            return_value=Result.ok([{"uid": "task_gone_abc", "user_uid": "user_owner"}])
        )

        result = await tracker.reconcile_deletions(tmp_path, owner_uid="user_owner")
        assert result.is_ok
        assert result.value.entities_deleted == 1
        assert result.value.ownership_mismatches == []

    @pytest.mark.asyncio
    async def test_foreign_owned_entity_skipped_and_surfaced(self, tmp_path) -> None:
        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        gone = tmp_path / "task.gone.yaml"

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(gone), "entity_uid": "task_gone_abc"},
            ]
        )
        backend.get_entity_owner_uids = AsyncMock(
            return_value=Result.ok([{"uid": "task_gone_abc", "user_uid": "user_victim"}])
        )

        result = await tracker.reconcile_deletions(tmp_path, owner_uid="user_owner")
        assert result.is_ok
        # Entity NOT deleted, tracking row NOT removed, anomaly surfaced.
        assert result.value.entities_deleted == 0
        assert result.value.stale_metadata_removed == 0
        assert len(result.value.ownership_mismatches) == 1
        assert "task_gone_abc" in result.value.ownership_mismatches[0]
        backend.delete_entities_with_metadata.assert_not_called()
        backend.delete_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_ownerless_shared_entity_still_deleted(self, tmp_path) -> None:
        # SHARED curriculum carries no user_uid → no owner row → path-scoped
        # deletion proceeds exactly as before.
        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        gone = tmp_path / "ku.gone.md"

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(gone), "entity_uid": "ku.gone"},
            ]
        )
        backend.get_entity_owner_uids = AsyncMock(return_value=Result.ok([]))

        result = await tracker.reconcile_deletions(tmp_path, owner_uid="user_admin")
        assert result.is_ok
        assert result.value.entities_deleted == 1
        assert result.value.ownership_mismatches == []

    @pytest.mark.asyncio
    async def test_owner_lookup_failure_fails_closed(self, tmp_path) -> None:
        from core.utils.result_simplified import Errors

        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        gone = tmp_path / "task.gone.yaml"

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(gone), "entity_uid": "task_gone_abc"},
            ]
        )
        backend.get_entity_owner_uids = AsyncMock(
            return_value=Result.fail(Errors.database(operation="owners", message="boom"))
        )

        result = await tracker.reconcile_deletions(tmp_path, owner_uid="user_owner")
        # The guard fails CLOSED: no unscoped delete slips through.
        assert result.is_error
        backend.delete_entities_with_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_edge_deletion_stays_path_scoped(self, tmp_path) -> None:
        # Relationships carry no owner — an owner-scoped run still deletes a
        # vanished Edge YAML's relationship, and never queries owners for it.
        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        gone_edge = tmp_path / "edge-a-b.yaml"

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(gone_edge), "entity_uid": "edge:ku.a|RELATED_TO|ku.b"},
            ]
        )

        result = await tracker.reconcile_deletions(tmp_path, owner_uid="user_owner")
        assert result.is_ok
        assert result.value.edges_deleted == 1
        backend.get_entity_owner_uids.assert_not_called()


class TestReconcileDeletionsWall:
    """Wall symmetry (Codex R4): a tracked row is retracted when its file becomes
    disallowed by the vault wall, not only when deleted from disk — otherwise
    previously-synced content lingers in the graph after the wall is narrowed."""

    def _wall(self, root, *allowed):
        from core.services.ingestion.config import SyncAllowlist

        return SyncAllowlist(
            governed_root=root.resolve(),
            allowed_dirs=frozenset(a.resolve() for a in allowed),
        )

    @pytest.mark.asyncio
    async def test_walled_file_purged_even_though_present(self, tmp_path) -> None:
        # A non-staging folder that is not on the allowlist: the file exists on
        # disk but is now private, so its already-ingested entity is purged.
        (tmp_path / "periodic_notes").mkdir()
        (tmp_path / "oldnotes").mkdir()
        allowed = tmp_path / "periodic_notes" / "note.md"
        allowed.write_text("x")
        walled = tmp_path / "oldnotes" / "private.md"
        walled.write_text("x")

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(allowed), "entity_uid": "ku.allowed"},
                {"file_path": str(walled), "entity_uid": "ku.walled"},
            ]
        )
        result = await tracker.reconcile_deletions(
            tmp_path, allowlist=self._wall(tmp_path, tmp_path / "periodic_notes")
        )
        assert result.is_ok
        assert not result.value.mass_deletion_refused
        assert result.value.entities_deleted == 1
        items = backend.delete_entities_with_metadata.await_args.args[0]
        assert items == [{"file_path": str(walled), "entity_uid": "ku.walled"}]

    @pytest.mark.asyncio
    async def test_staging_file_purged_without_allowlist(self, tmp_path) -> None:
        # The staging floor retracts too, even when no privacy wall is active.
        (tmp_path / "notes").mkdir()
        (tmp_path / "je_out").mkdir()
        alive = tmp_path / "notes" / "n.md"
        alive.write_text("x")
        staging = tmp_path / "je_out" / "transcript.md"
        staging.write_text("x")

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(staging), "entity_uid": "ku.staging"},
            ]
        )
        result = await tracker.reconcile_deletions(tmp_path)  # allowlist=None
        assert result.is_ok
        assert result.value.entities_deleted == 1
        items = backend.delete_entities_with_metadata.await_args.args[0]
        assert items == [{"file_path": str(staging), "entity_uid": "ku.staging"}]

    @pytest.mark.asyncio
    async def test_walled_but_reingested_at_allowed_path_survives(self, tmp_path) -> None:
        # Same entity claimed by a walled old path AND an allowed new path (a move
        # into the synced folder). Entity survives; only the stale walled row goes.
        (tmp_path / "periodic_notes").mkdir()
        (tmp_path / "oldnotes").mkdir()
        walled_old = tmp_path / "oldnotes" / "thing.md"
        walled_old.write_text("x")
        allowed_new = tmp_path / "periodic_notes" / "thing.md"
        allowed_new.write_text("x")

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(walled_old), "entity_uid": "ku.thing"},
                {"file_path": str(allowed_new), "entity_uid": "ku.thing"},
            ]
        )
        result = await tracker.reconcile_deletions(
            tmp_path, allowlist=self._wall(tmp_path, tmp_path / "periodic_notes")
        )
        assert result.is_ok
        assert result.value.entities_deleted == 0
        assert result.value.stale_metadata_removed == 1
        backend.delete_entities_with_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_walled_but_present_purges_not_refused(self, tmp_path) -> None:
        # Everything walled but physically on disk: the vault is mounted, so the
        # unmount valve does NOT fire — the rows are purged (recoverable by
        # re-allowing the folder and re-syncing, since the vault is source of truth).
        (tmp_path / "oldnotes").mkdir()
        a = tmp_path / "oldnotes" / "a.md"
        a.write_text("x")
        b = tmp_path / "oldnotes" / "b.md"
        b.write_text("y")

        tracker, _backend = _tracker_with_tracked(
            [
                {"file_path": str(a), "entity_uid": "ku.a"},
                {"file_path": str(b), "entity_uid": "ku.b"},
            ]
        )
        # Allowlist points at a folder with no tracked files → everything walled.
        result = await tracker.reconcile_deletions(
            tmp_path, allowlist=self._wall(tmp_path, tmp_path / "periodic_notes")
        )
        assert result.is_ok
        assert not result.value.mass_deletion_refused
        assert result.value.entities_deleted == 2
