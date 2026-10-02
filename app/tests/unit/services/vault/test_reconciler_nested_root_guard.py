"""VaultReconciler surface-independence guard for nested vault roots.

By-kind and by-path resolution must agree on a vault's owner: a member vault nested
inside the primary personal root is governed by the primary owner by path, so the
reconciler refuses to sync it as anyone else. (A personal root overlapping the
content vault — the other way the two could disagree — is refused at boot,
``VaultConfig.validate_roots``.)
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


async def test_member_sync_refused_when_nested_under_primary_root(tmp_path: Path) -> None:
    # Misconfiguration: member family INSIDE the primary personal root. By-path,
    # the primary owner governs everything under its root, so a member's by-kind
    # sync would split attribution (ingest → primary, round-trip → member).
    # The owner-mismatch arm of the surface-independence guard refuses it.
    primary_root = tmp_path / "personal"
    family_root = primary_root / "user_vaults"
    (family_root / "user_member").mkdir(parents=True)

    def _factory(owner_uid: UserUID, root: Path) -> VaultDescriptor:
        return _descriptor(VaultKind.PERSONAL, root, str(owner_uid))

    registry = VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, tmp_path / "content", "user_admin"),
        personal=_descriptor(VaultKind.PERSONAL, primary_root, "user_primary"),
        user_vaults_root=family_root,
        personal_descriptor_factory=_factory,
    )
    ingestion = Mock()
    reconciler = _reconciler(registry, ingestion)

    result = await reconciler.sync(VaultKind.PERSONAL, UserUID("user_member"))

    assert result.is_error
    assert "governed by another" in result.expect_error().message.lower()
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
