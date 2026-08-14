"""Dry-run vault sync preview (vault security arc PR 7).

Two layers under test:

1. ``IngestionTracker.plan_deletions`` — the read-only planning half of
   deletion reconciliation. It must classify everything (moved/stale split,
   valves, owner scope, edge parseability) WITHOUT executing any delete.
2. ``VaultReconciler.preview`` — the same descriptor resolution, per-root
   lock, and consent gate as ``sync()``, reporting what a sync WOULD do.
   Nothing is written to the graph or the vault; every path it surfaces is
   vault-relative (#525 sanitization policy).

Route fragments follow the fake-rt registry pattern from
test_vault_sync_privacy_wall_route.py (#526).
"""

from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from adapters.inbound.vault_routes import create_vault_routes
from core.services.ingestion.config import SyncAllowlist
from core.services.ingestion.ingestion_tracker import IngestionTracker
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind
from core.services.vault.vault_reconciler import (
    VaultDescription,
    VaultReconciler,
    VaultSyncPreview,
)
from core.utils.result_simplified import Result
from tests.fixtures.csrf import attach_csrf

# ---------------------------------------------------------------------------
# plan_deletions — read-only classification
# ---------------------------------------------------------------------------


def _tracker_with_tracked(rows: list[dict]) -> tuple[IngestionTracker, MagicMock]:
    backend = MagicMock()
    backend.get_tracked_files_under = AsyncMock(return_value=Result.ok(rows))
    backend.get_entity_owner_uids = AsyncMock(return_value=Result.ok([]))
    backend.delete_entities_with_metadata = AsyncMock()
    backend.delete_edge_with_metadata = AsyncMock()
    backend.delete_ingestion_metadata = AsyncMock()
    return IngestionTracker(backend), backend


def _assert_no_deletes(backend: MagicMock) -> None:
    backend.delete_entities_with_metadata.assert_not_called()
    backend.delete_edge_with_metadata.assert_not_called()
    backend.delete_ingestion_metadata.assert_not_called()


class TestPlanDeletionsIsReadOnly:
    @pytest.mark.asyncio
    async def test_plan_classifies_without_calling_any_delete(self, tmp_path) -> None:
        alive = tmp_path / "ku.alive.md"
        alive.write_text("x")
        gone = tmp_path / "ku.gone.md"  # never created
        gone_edge = tmp_path / "edge-a-b.yaml"  # never created
        moved_new = tmp_path / "renamed" / "ku.moved.md"
        moved_new.parent.mkdir()
        moved_new.write_text("x")

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.alive"},
                {"file_path": str(gone), "entity_uid": "ku.gone"},
                {"file_path": str(gone_edge), "entity_uid": "edge:ku.a|RELATED_TO|ku.b"},
                {"file_path": str(tmp_path / "ku.moved.md"), "entity_uid": "ku.moved"},
                {"file_path": str(moved_new), "entity_uid": "ku.moved"},
            ]
        )

        result = await tracker.plan_deletions(tmp_path)
        assert result.is_ok
        plan = result.value

        assert [(p.entity_uid, p.display_path) for p in plan.entity_deletions] == [
            ("ku.gone", "ku.gone.md")
        ]
        assert [(e.from_uid, e.to_uid, e.display_path) for e in plan.edge_deletions] == [
            ("ku.a", "ku.b", "edge-a-b.yaml")
        ]
        assert plan.stale_file_paths == (str(tmp_path / "ku.moved.md"),)
        assert not plan.mass_deletion_refused
        _assert_no_deletes(backend)

    @pytest.mark.asyncio
    async def test_plan_display_paths_are_vault_relative(self, tmp_path) -> None:
        alive = tmp_path / "notes" / "keep.md"
        alive.parent.mkdir()
        alive.write_text("x")
        gone = tmp_path / "notes" / "gone.md"

        tracker, backend = _tracker_with_tracked(
            [
                {"file_path": str(alive), "entity_uid": "ku.keep"},
                {"file_path": str(gone), "entity_uid": "ku.gone"},
            ]
        )

        result = await tracker.plan_deletions(tmp_path)
        assert result.is_ok
        assert result.value.entity_deletions[0].display_path == "notes/gone.md"
        _assert_no_deletes(backend)

    @pytest.mark.asyncio
    async def test_plan_threshold_refusal_still_no_deletes(self, tmp_path) -> None:
        present = tmp_path / "ku.present.md"
        present.write_text("x")
        rows = [{"file_path": str(present), "entity_uid": "ku.present"}]
        rows.extend(
            {"file_path": str(tmp_path / f"ku.m-{i}.md"), "entity_uid": f"ku.m-{i}"}
            for i in range(14)
        )
        tracker, backend = _tracker_with_tracked(rows)

        result = await tracker.plan_deletions(tmp_path)
        assert result.is_ok
        assert result.value.mass_deletion_refused
        assert result.value.refusal_warning is not None
        _assert_no_deletes(backend)


# ---------------------------------------------------------------------------
# VaultReconciler.preview
# ---------------------------------------------------------------------------


def _preview_harness(tmp_path, *, consented: bool = True):
    """A reconciler wired for PERSONAL preview over a real tmp vault root."""
    notes = tmp_path / "periodic_notes"
    notes.mkdir(exist_ok=True)
    allowlist = SyncAllowlist(
        governed_root=tmp_path.resolve(), allowed_dirs=frozenset({notes.resolve()})
    )
    descriptor = VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=tmp_path,
        owner_uid="user_owner",
        allowlist=allowlist,
        bridge=MagicMock(),
        supports_task_round_trip=True,
    )
    registry = MagicMock()
    registry.resolve = MagicMock(return_value=Result.ok(descriptor))
    registry.resolve_by_path = MagicMock(return_value=Result.ok(descriptor))
    registry.conflicting_nested_roots = MagicMock(return_value=[])

    backend = MagicMock()
    backend.get_ingestion_metadata = AsyncMock(return_value=Result.ok([]))
    backend.get_tracked_files_under = AsyncMock(return_value=Result.ok([]))
    backend.get_entity_owner_uids = AsyncMock(return_value=Result.ok([]))
    backend.delete_entities_with_metadata = AsyncMock()
    backend.delete_edge_with_metadata = AsyncMock()
    backend.delete_ingestion_metadata = AsyncMock()

    ingestion = MagicMock()
    ingestion.ingestion_backend = backend

    user = SimpleNamespace(preferences=SimpleNamespace(vault_write_consent=consented))
    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(user))

    reconciler = VaultReconciler(
        registry=registry,
        unified_ingestion=ingestion,
        user_entry_service=MagicMock(),
        tasks_service=MagicMock(),
        user_service=user_service,
    )
    return reconciler, backend, notes


def _walk_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [s for item in value for s in _walk_strings(item)]
    return []


class TestVaultPreview:
    @pytest.mark.asyncio
    async def test_preview_refuses_conflicting_nested_roots(self, tmp_path) -> None:
        """Kody #527: sync() gets the single-vault guard from ingest_directory;
        preview scans the root itself, so it must run the same guard — a
        nested different-owner vault must not have its filenames listed."""
        reconciler, backend, _notes = _preview_harness(tmp_path)
        reconciler._registry.conflicting_nested_roots = MagicMock(
            return_value=[tmp_path / "user_vaults" / "user_other"]
        )

        result = await reconciler.preview(VaultKind.PERSONAL, "user_owner")
        assert result.is_error
        assert "nested vault" in result.expect_error().message
        backend.get_ingestion_metadata.assert_not_called()
        backend.get_tracked_files_under.assert_not_called()

    @pytest.mark.asyncio
    async def test_preview_requires_consent_before_any_read(self, tmp_path) -> None:
        """Consent covers READING (ADR-070 Decision 6 amendment): a
        not-yet-consented user gets first_run_notice and NO vault/tracker read."""
        reconciler, backend, _notes = _preview_harness(tmp_path, consented=False)

        result = await reconciler.preview(VaultKind.PERSONAL, "user_owner")
        assert result.is_ok
        assert result.value.first_run_notice
        backend.get_ingestion_metadata.assert_not_called()
        backend.get_tracked_files_under.assert_not_called()

    @pytest.mark.asyncio
    async def test_preview_reports_would_ingest_new_file(self, tmp_path) -> None:
        reconciler, backend, notes = _preview_harness(tmp_path)
        (notes / "note1.md").write_text("# hello")

        result = await reconciler.preview(VaultKind.PERSONAL, "user_owner")
        assert result.is_ok
        preview = result.value
        assert preview.would_ingest_count == 1
        assert preview.would_ingest_new == 1
        assert preview.would_ingest_changed == 0
        assert preview.would_ingest_examples == ("periodic_notes/note1.md (new)",)
        _assert_no_deletes(backend)

    @pytest.mark.asyncio
    async def test_preview_reports_would_delete_without_deleting(self, tmp_path) -> None:
        reconciler, backend, notes = _preview_harness(tmp_path)
        alive = notes / "keep.md"
        alive.write_text("x")
        gone = notes / "gone.md"  # tracked but deleted from disk

        backend.get_tracked_files_under = AsyncMock(
            return_value=Result.ok(
                [
                    {"file_path": str(alive), "entity_uid": "ku.keep"},
                    {"file_path": str(gone), "entity_uid": "ku.gone"},
                ]
            )
        )

        result = await reconciler.preview(VaultKind.PERSONAL, "user_owner")
        assert result.is_ok
        preview = result.value
        assert preview.would_delete_entities == 1
        assert preview.would_delete_entity_examples == ("periodic_notes/gone.md",)
        # The owner scope of a governed sync applies to the plan too.
        backend.get_entity_owner_uids.assert_awaited_once_with(["ku.gone"])
        _assert_no_deletes(backend)

    @pytest.mark.asyncio
    async def test_preview_contains_no_absolute_paths(self, tmp_path) -> None:
        """#525 policy: no string in the preview may carry the host vault root."""
        reconciler, backend, notes = _preview_harness(tmp_path)
        (notes / "new-note.md").write_text("x")
        gone = notes / "gone.md"
        alive = notes / "keep.md"
        alive.write_text("x")
        backend.get_tracked_files_under = AsyncMock(
            return_value=Result.ok(
                [
                    {"file_path": str(alive), "entity_uid": "ku.keep"},
                    {"file_path": str(gone), "entity_uid": "ku.gone"},
                ]
            )
        )

        result = await reconciler.preview(VaultKind.PERSONAL, "user_owner")
        assert result.is_ok
        for text in _walk_strings(list(asdict(result.value).values())):
            assert str(tmp_path) not in text


# ---------------------------------------------------------------------------
# Route fragment — /settings/vault/preview
# ---------------------------------------------------------------------------


class _RouteRegistry:
    """Capture handlers registered via @rt(path, methods=...)."""

    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], object] = {}

    def __call__(self, path: str, methods: list[str] | None = None):
        method = (methods[0] if methods else "GET").upper()

        def decorator(func):
            self.handlers[(path, method)] = func
            return func

        return decorator

    def get(self, path: str, method: str = "POST"):
        return self.handlers[(path, method.upper())]


def _request():
    request = SimpleNamespace()
    request.session = {"user_uid": "user_owner"}
    request.method = "POST"
    request.url = SimpleNamespace(path="/settings/vault/preview")
    return attach_csrf(request)


class TestPreviewRoute:
    @pytest.mark.asyncio
    async def test_preview_fragment_reports_counts_and_sync_button(self) -> None:
        registry = _RouteRegistry()
        reconciler = MagicMock()
        reconciler.preview = AsyncMock(
            return_value=Result.ok(
                VaultSyncPreview(
                    would_ingest_count=2,
                    would_ingest_new=1,
                    would_ingest_changed=1,
                    would_ingest_examples=(
                        "periodic_notes/a.md (new)",
                        "periodic_notes/b.md (changed)",
                    ),
                    would_delete_entities=1,
                    would_delete_entity_examples=("periodic_notes/gone.md",),
                    stale_cleanup_count=1,
                )
            )
        )
        create_vault_routes(
            app=None, rt=registry, vault_reconciler=reconciler, user_service=MagicMock()
        )

        handler = registry.get("/settings/vault/preview", "POST")
        html = to_xml(await handler(_request()))

        assert "nothing has been changed" in html
        assert "This sync would" in html
        assert "periodic_notes/a.md (new)" in html
        assert "periodic_notes/gone.md" in html
        assert "Run sync now" in html
        # The run-sync button posts to the REAL sync endpoint.
        assert 'hx-post="/settings/vault/sync"' in html

    @pytest.mark.asyncio
    async def test_preview_first_run_notice_renders_consent_form(self) -> None:
        registry = _RouteRegistry()
        reconciler = MagicMock()
        reconciler.preview = AsyncMock(
            return_value=Result.ok(VaultSyncPreview(first_run_notice=True))
        )
        reconciler.describe = AsyncMock(
            return_value=Result.ok(
                VaultDescription(vault_configured=True, allowed_folders=("periodic_notes",))
            )
        )
        create_vault_routes(
            app=None, rt=registry, vault_reconciler=reconciler, user_service=MagicMock()
        )

        handler = registry.get("/settings/vault/preview", "POST")
        html = to_xml(await handler(_request()))

        assert "Allow SKUEL to sync" in html
        assert "periodic_notes/" in html
        # Kody #527: consent reached from Preview must continue into a
        # PREVIEW, never a real sync.
        assert 'hx-post="/settings/vault/preview/consent"' in html
        assert "Allow and preview" in html
        assert 'hx-post="/settings/vault/consent"' not in html

    @pytest.mark.asyncio
    async def test_preview_consent_route_reruns_preview_not_sync(self) -> None:
        # Kody #527: the preview-consent door grants consent then re-runs the
        # DRY-RUN preview; the real sync is never invoked.
        registry = _RouteRegistry()
        reconciler = MagicMock()
        reconciler.grant_consent = AsyncMock(return_value=Result.ok(None))
        reconciler.preview = AsyncMock(
            return_value=Result.ok(VaultSyncPreview(would_ingest_count=1, would_ingest_new=1))
        )
        reconciler.sync = AsyncMock()
        create_vault_routes(
            app=None, rt=registry, vault_reconciler=reconciler, user_service=MagicMock()
        )

        handler = registry.get("/settings/vault/preview/consent", "POST")
        html = to_xml(await handler(_request()))

        reconciler.grant_consent.assert_awaited_once()
        reconciler.preview.assert_awaited_once()
        reconciler.sync.assert_not_called()
        assert "nothing has been changed" in html

    @pytest.mark.asyncio
    async def test_zero_count_preview_with_warnings_is_not_in_sync(self) -> None:
        # Kody #527: a refused mass deletion must never hide behind an
        # "already in sync" header just because every count is zero.
        registry = _RouteRegistry()
        reconciler = MagicMock()
        reconciler.preview = AsyncMock(
            return_value=Result.ok(
                VaultSyncPreview(
                    refusal_warning=(
                        "Deletion reconciliation refused: 12 of 15 tracked files "
                        "would be deleted in one sync."
                    )
                )
            )
        )
        create_vault_routes(
            app=None, rt=registry, vault_reconciler=reconciler, user_service=MagicMock()
        )

        handler = registry.get("/settings/vault/preview", "POST")
        html = to_xml(await handler(_request()))

        assert "already in sync" not in html
        assert "warning" in html.lower()
        assert "Deletion reconciliation refused" in html

    def test_preview_button_posts_to_preview_door(self) -> None:
        # The sync page composes preview_button next to sync_button (page-level
        # render is covered in test_vault_sync_privacy_wall_route.py); assert
        # the button wiring directly — the fragment posts to the preview door.
        from ui.vault.sync_fragments import preview_button

        html = to_xml(preview_button())
        assert 'hx-post="/settings/vault/preview"' in html
        assert "Preview sync" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
