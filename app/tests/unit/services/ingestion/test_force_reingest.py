"""Force re-ingestion — the sanctioned re-chunk/migration path (force ≠ full).

``force=True`` must re-process files whose IngestionMetadata hash/mtime still
match (which smart mode would skip) while KEEPING tracked-mode semantics:
metadata rows are re-stamped and deletion reconciliation still runs. Full mode
also processes everything but skips reconciliation — on a walled vault that
would leave now-private rows — so force is defined on top of smart, never full.

This productizes the ADR-074 migration workaround (manual
``SET s.content_hash='force'`` tracker-row invalidation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.batch import ingest_directory
from core.services.ingestion.config import SyncAllowlist
from core.services.ingestion.types import IncrementalStats
from core.services.vault.vault_descriptor import (
    VaultDescriptor,
    VaultKind,
    VaultRegistry,
)
from core.services.vault.vault_reconciler import VaultReconciler
from core.utils.result_simplified import Result

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeBulkBackend:
    """Records what reaches the bulk upsert (per-type), succeeding always."""

    def __init__(self) -> None:
        self.upserted: dict[str, list[dict[str, Any]]] = {}

    async def ensure_constraints(self, entity_label: str) -> None:
        return None

    async def upsert_nodes(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, Any],
        batch_size: int = 500,
    ) -> Any:
        from core.ingestion.ingestion_types import IngestionResult

        self.upserted.setdefault(entity_label, []).extend(dict(e) for e in entities)
        return Result.ok(
            IngestionResult(
                total_processed=len(entities),
                nodes_created=len(entities),
                nodes_updated=0,
                relationships_created=0,
                errors=[],
            )
        )

    async def create_relationships(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, Any],
        batch_size: int = 500,
    ) -> Any:
        from core.ingestion.ingestion_types import IngestionResult

        return Result.ok(
            IngestionResult(
                total_processed=len(entities),
                nodes_created=0,
                nodes_updated=0,
                relationships_created=0,
                errors=[],
            )
        )


class _FakeIngestionBackend:
    """In-memory IngestionBackendOperations double for tracker interaction.

    Seed ``metadata`` with rows keyed by canonical path string; the fake records
    every metadata re-stamp and entity deletion so tests can assert the tracked
    side effects of a force run.
    """

    def __init__(self) -> None:
        self.metadata: dict[str, dict[str, Any]] = {}
        self.batch_updates: list[dict[str, Any]] = []
        self.deleted_entities: list[dict[str, Any]] = []
        self.deleted_metadata_paths: list[str] = []

    def seed(self, file_path: Path, entity_uid: str, content_hash: str) -> None:
        key = str(file_path.resolve())
        self.metadata[key] = {
            "file_path": key,
            "content_hash": content_hash,
            "file_mtime": file_path.stat().st_mtime if file_path.exists() else 0.0,
            "last_ingested_at": None,
            "entity_uid": entity_uid,
        }

    async def ensure_tracker_constraints(self) -> Result[None]:
        return Result.ok(None)

    async def get_ingestion_metadata(self, path_strings: list[str]) -> Result[list[dict[str, Any]]]:
        return Result.ok([self.metadata[p] for p in path_strings if p in self.metadata])

    async def update_ingestion_metadata(self, item: dict[str, Any]) -> Result[list[dict[str, Any]]]:
        self.batch_updates.append(item)
        return Result.ok([{"updated": 1}])

    async def update_ingestion_metadata_batch(
        self, items: list[dict[str, Any]]
    ) -> Result[list[dict[str, Any]]]:
        self.batch_updates.extend(items)
        return Result.ok([{"updated": len(items)}])

    async def get_tracked_files_under(self, prefix: str) -> Result[list[dict[str, Any]]]:
        return Result.ok(
            [
                {
                    "file_path": row["file_path"],
                    "entity_uid": row["entity_uid"],
                    "content_hash": row.get("content_hash"),
                }
                for row in self.metadata.values()
                if row["file_path"].startswith(prefix)
            ]
        )

    async def get_live_entity_uids(self, uids: list[str]) -> Result[list[dict[str, Any]]]:
        # Every tracked uid is "live" in this double — the move-detection
        # pre-pass live-node guard is exercised in test_move_detection.py.
        return Result.ok([{"uid": uid} for uid in uids])

    async def delete_entities_with_metadata(
        self, items: list[dict[str, Any]]
    ) -> Result[list[dict[str, Any]]]:
        self.deleted_entities.extend(items)
        return Result.ok(items)

    async def delete_edge_with_metadata(
        self, file_path: str, from_uid: str, to_uid: str, rel_type: Any
    ) -> Result[None]:
        return Result.ok(None)

    async def delete_ingestion_metadata(
        self, path_strings: list[str]
    ) -> Result[list[dict[str, Any]]]:
        self.deleted_metadata_paths.extend(path_strings)
        return Result.ok([{"deleted": len(path_strings)}])


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_ku(directory: Path, slug: str) -> Path:
    file = directory / f"{slug}.md"
    file.write_text(f"---\ntype: ku\nuid: ku:{slug}\ntitle: {slug}\n---\nBody.\n", encoding="utf-8")
    return file


# ---------------------------------------------------------------------------
# Batch engine — force predicate / tracker interaction
# ---------------------------------------------------------------------------


async def test_smart_mode_skips_unchanged_file(tmp_path: Path) -> None:
    """Baseline control: a hash+mtime match is skipped without force."""
    ku_file = _write_ku(tmp_path, "unchanged")
    backend = _FakeIngestionBackend()
    backend.seed(ku_file, "ku.unchanged", _sha256(ku_file))
    bulk = _FakeBulkBackend()

    result = await ingest_directory(
        directory=tmp_path,
        bulk_backend=bulk,
        ingestion_backend=backend,
        ingestion_mode="smart",
    )

    assert result.is_ok, f"smart ingest failed: {result}"
    stats = cast("IncrementalStats", result.value)
    assert stats.files_ingested == 0
    assert stats.files_skipped == 1
    assert "Ku" not in bulk.upserted


async def test_force_reprocesses_unchanged_file_and_restamps_metadata(tmp_path: Path) -> None:
    """Force bypasses the hash/mtime skip: the unchanged file re-processes
    through the bulk engine and its tracker row is re-stamped."""
    ku_file = _write_ku(tmp_path, "unchanged")
    backend = _FakeIngestionBackend()
    backend.seed(ku_file, "ku.unchanged", _sha256(ku_file))
    bulk = _FakeBulkBackend()

    result = await ingest_directory(
        directory=tmp_path,
        bulk_backend=bulk,
        ingestion_backend=backend,
        ingestion_mode="smart",
        force=True,
    )

    assert result.is_ok, f"force ingest failed: {result}"
    stats = cast("IncrementalStats", result.value)
    assert stats.files_ingested == 1
    assert stats.files_skipped == 0
    assert [e["uid"] for e in bulk.upserted["Ku"]] == ["ku.unchanged"]
    # Tracked-mode semantics kept: the metadata row was re-stamped.
    assert [u["file_path"] for u in backend.batch_updates] == [str(ku_file.resolve())]


async def test_force_still_runs_deletion_reconciliation(tmp_path: Path) -> None:
    """Force ≠ full: deletion propagation still fires on a force run — a
    tracked file deleted from the vault loses its graph entity."""
    survivor = _write_ku(tmp_path, "survivor")
    deleted = tmp_path / "deleted.md"  # tracked but no longer on disk
    backend = _FakeIngestionBackend()
    backend.seed(survivor, "ku.survivor", _sha256(survivor))
    backend.metadata[str(deleted.resolve())] = {
        "file_path": str(deleted.resolve()),
        "content_hash": "old-hash",
        "file_mtime": 0.0,
        "last_ingested_at": None,
        "entity_uid": "ku.deleted",
    }

    result = await ingest_directory(
        directory=tmp_path,
        bulk_backend=_FakeBulkBackend(),
        ingestion_backend=backend,
        ingestion_mode="smart",
        force=True,
    )

    assert result.is_ok, f"force ingest failed: {result}"
    stats = cast("IncrementalStats", result.value)
    assert stats.entities_deleted == 1
    assert [d["entity_uid"] for d in backend.deleted_entities] == ["ku.deleted"]


async def test_force_respects_allowlist_wall(tmp_path: Path) -> None:
    """Force never widens the wall: a walled file is not collected, and its
    previously-tracked row is retracted by reconciliation (fail-closed)."""
    root = tmp_path / "vault"
    allowed_dir = root / "allowed"
    allowed_dir.mkdir(parents=True)
    walled_dir = root / "walled"
    walled_dir.mkdir()
    allowed = _write_ku(allowed_dir, "allowed")
    walled = _write_ku(walled_dir, "walled")

    backend = _FakeIngestionBackend()
    backend.seed(allowed, "ku.allowed", _sha256(allowed))
    backend.seed(walled, "ku.walled", _sha256(walled))
    bulk = _FakeBulkBackend()
    wall = SyncAllowlist(
        governed_root=root.resolve(), allowed_dirs=frozenset({allowed_dir.resolve()})
    )

    result = await ingest_directory(
        directory=root,
        bulk_backend=bulk,
        ingestion_backend=backend,
        ingestion_mode="smart",
        force=True,
        allowlist=wall,
    )

    assert result.is_ok, f"force ingest failed: {result}"
    # Only the allowed file re-processed; the walled one never reached the engine.
    assert [e["uid"] for e in bulk.upserted["Ku"]] == ["ku.allowed"]
    # Fail-closed retraction of the now-walled row still ran.
    stats = cast("IncrementalStats", result.value)
    assert stats.entities_deleted == 1
    assert [d["entity_uid"] for d in backend.deleted_entities] == ["ku.walled"]


async def test_force_with_full_mode_rejected_at_engine(tmp_path: Path) -> None:
    """A full-mode force at the engine is a contradiction (full skips
    reconciliation) — the facade coerces; a direct mis-call fails validation."""
    _write_ku(tmp_path, "any")

    result = await ingest_directory(
        directory=tmp_path,
        bulk_backend=_FakeBulkBackend(),
        ingestion_backend=_FakeIngestionBackend(),
        ingestion_mode="full",
        force=True,
    )

    assert result.is_error
    assert "force" in str(result.expect_error()).lower()


# ---------------------------------------------------------------------------
# Facade — full → smart coercion under force
# ---------------------------------------------------------------------------


async def test_facade_coerces_full_to_smart_and_threads_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.services.ingestion import unified_ingestion_service as mod
    from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService

    captured: dict[str, object] = {}

    async def _fake_batch(**kwargs: object) -> Result[IncrementalStats]:
        captured["mode"] = kwargs["ingestion_mode"]
        captured["force"] = kwargs["force"]
        return Result.ok(IncrementalStats(total_files=0, duration_seconds=0))

    monkeypatch.setattr(mod, "ingest_directory", _fake_batch)

    svc = UnifiedIngestionService(write_backend=Mock(), bulk_backend=Mock())
    svc.ingestion_backend = object()  # type: ignore[assignment]  # non-None enables tracked modes

    root = tmp_path / "content"
    root.mkdir()
    await svc.ingest_directory(root, ingestion_mode="full", force=True)
    assert captured == {"mode": "smart", "force": True}

    # Without force, an ungoverned full request stays full (existing behavior).
    captured.clear()
    await svc.ingest_directory(root, ingestion_mode="full")
    assert captured == {"mode": "full", "force": False}


# ---------------------------------------------------------------------------
# Reconciler — force threads through sync()
# ---------------------------------------------------------------------------


async def test_reconciler_threads_force_to_ingest_directory(tmp_path: Path) -> None:
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"

    def _descriptor(kind: VaultKind, root: Path, owner: str) -> VaultDescriptor:
        return VaultDescriptor(
            kind=kind,
            root=root,
            owner_uid=UserUID(owner),
            allowlist=SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset()),
            bridge=cast("VaultBridgePort", object()),
            supports_task_round_trip=kind is VaultKind.PERSONAL,
        )

    registry = VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, content_root, "user_admin"),
        personal=_descriptor(VaultKind.PERSONAL, personal_root, "user_placeholder"),
    )
    ingestion = Mock()
    ingestion.ingest_directory = AsyncMock(
        return_value=Result.ok(IncrementalStats(total_files=0, duration_seconds=0))
    )
    reconciler = VaultReconciler(
        registry=registry,
        unified_ingestion=ingestion,
        user_entry_service=Mock(),
        tasks_service=Mock(),
        user_service=Mock(),
    )

    result = await reconciler.sync(VaultKind.CONTENT, UserUID("user_admin"), force=True)

    assert result.is_ok, f"sync failed: {result}"
    kwargs = ingestion.ingest_directory.await_args.kwargs
    assert kwargs["ingestion_mode"] == "smart"
    assert kwargs["force"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
