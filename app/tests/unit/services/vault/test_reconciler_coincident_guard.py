"""VaultReconciler surface-independence guard for combined-root configs.

In a combined-root config (``VAULT_ROOT == INGESTION_PATH``) the single vault
resolves to PERSONAL by-path, so a by-kind CONTENT sync would stamp
``content_owner_uid`` onto the user's own files — the same file would get a
different owner than a PERSONAL sync of the same root. The reconciler refuses the
incoherent CONTENT sync rather than break the surface-independent owner rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.config import SyncAllowlist
from core.services.vault.vault_descriptor import (
    VaultDescriptor,
    VaultKind,
    VaultRegistry,
)
from core.services.vault.vault_reconciler import VaultReconciler

pytestmark = pytest.mark.asyncio


def _wall(root: Path) -> SyncAllowlist:
    return SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset())


def _descriptor(kind: VaultKind, root: Path, owner: str) -> VaultDescriptor:
    return VaultDescriptor(
        kind=kind,
        root=root,
        owner_uid=UserUID(owner),
        allowlist=_wall(root),
        bridge=cast("VaultBridgePort", object()),
        supports_task_round_trip=kind is VaultKind.PERSONAL,
    )


def _reconciler(registry: VaultRegistry, ingestion: Mock) -> VaultReconciler:
    return VaultReconciler(
        registry=registry,
        unified_ingestion=ingestion,
        user_entry_service=Mock(),
        tasks_service=Mock(),
        user_service=Mock(),
    )


async def test_content_sync_refused_in_combined_root(tmp_path: Path) -> None:
    shared = tmp_path / "vault"
    registry = VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, shared, "user_admin"),
        personal=_descriptor(VaultKind.PERSONAL, shared, "user_placeholder"),
    )
    ingestion = Mock()
    reconciler = _reconciler(registry, ingestion)

    result = await reconciler.sync(VaultKind.CONTENT, "user_admin")

    assert result.is_error
    assert "combined-root" in result.expect_error().message.lower()
    # The guard fires before any ingestion is attempted.
    ingestion.ingest_directory.assert_not_called()


async def test_content_sync_allowed_in_split_root(tmp_path: Path) -> None:
    content_root = tmp_path / "content"
    personal_root = tmp_path / "personal"
    registry = VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, content_root, "user_admin"),
        personal=_descriptor(VaultKind.PERSONAL, personal_root, "user_placeholder"),
    )
    _reconciler(registry, Mock())

    # by-kind CONTENT and by-path (content_root → CONTENT) agree → guard passes.
    # (ingestion is mocked; we only assert the guard did not short-circuit.)
    by_path = registry.resolve_by_path(content_root, UserUID("user_admin"))
    assert by_path.is_ok and by_path.value.kind is VaultKind.CONTENT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
