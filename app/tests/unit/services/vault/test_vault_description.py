"""VaultReconciler.describe — the read-only door behind the sync page's privacy wall.

The sync page and consent form show users exactly what a sync may read; that
list must come from the LIVE allowlist, vault-relative (#525 — no absolute host
paths in UI-facing data), and a user without a personal vault must get a normal
``vault_configured=False`` description, never an error.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.config import SyncAllowlist, build_sync_allowlist
from core.services.vault.vault_descriptor import (
    VaultDescriptor,
    VaultKind,
    VaultRegistry,
)
from core.services.vault.vault_reconciler import VaultReconciler

OWNER = UserUID("user_owner")
STRANGER = UserUID("user_stranger")


def _descriptor(root: Path, allowlist: SyncAllowlist) -> VaultDescriptor:
    return VaultDescriptor(
        kind=VaultKind.PERSONAL,
        root=root,
        owner_uid=OWNER,
        allowlist=allowlist,
        bridge=cast("VaultBridgePort", object()),
        supports_task_round_trip=True,
    )


def _reconciler(personal: VaultDescriptor | None) -> VaultReconciler:
    registry = VaultRegistry(content=None, personal=personal)
    return VaultReconciler(
        registry=registry,
        unified_ingestion=Mock(),
        user_entry_service=Mock(),
        tasks_service=Mock(),
        user_service=Mock(),
    )


@pytest.mark.asyncio
async def test_personal_vault_yields_relative_sorted_doorway_folders(tmp_path: Path) -> None:
    """Default doorway wall → sorted vault-relative names, no absolute prefixes."""
    root = tmp_path / "personal"
    allowlist = build_sync_allowlist(root)  # distinct personal vault → doorway defaults
    reconciler = _reconciler(_descriptor(root, allowlist))

    result = await reconciler.describe(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    description = result.value
    assert description.vault_configured is True
    assert description.whole_vault_open is False
    assert description.allowed_folders == (
        "activity_notes",
        "je_pro",
        "knowledge",
        "periodic_notes",
        "personal_notes",
    )
    assert description.allowed_folders == tuple(sorted(description.allowed_folders))
    for folder in description.allowed_folders:
        assert not folder.startswith("/"), f"absolute path leaked: {folder}"
        assert str(tmp_path) not in folder


@pytest.mark.asyncio
async def test_nested_allowed_dir_stays_vault_relative(tmp_path: Path) -> None:
    root = tmp_path / "personal"
    allowlist = SyncAllowlist(
        governed_root=root.resolve(),
        allowed_dirs=frozenset({root.resolve() / "notes" / "deep"}),
    )
    reconciler = _reconciler(_descriptor(root, allowlist))

    description = (await reconciler.describe(VaultKind.PERSONAL, OWNER)).value

    assert description.allowed_folders == ("notes/deep",)


@pytest.mark.asyncio
async def test_user_without_vault_is_unconfigured_not_error(tmp_path: Path) -> None:
    """resolve() fails for a stranger — describe reports it as a normal state."""
    root = tmp_path / "personal"
    reconciler = _reconciler(_descriptor(root, build_sync_allowlist(root)))

    result = await reconciler.describe(VaultKind.PERSONAL, STRANGER)

    assert result.is_ok
    assert result.value.vault_configured is False
    assert result.value.allowed_folders == ()
    assert result.value.whole_vault_open is False


@pytest.mark.asyncio
async def test_combined_single_vault_reports_whole_vault_open(tmp_path: Path) -> None:
    """allowed_dirs == {governed_root} (single-vault case) → whole vault, no folder list."""
    root = tmp_path / "combined"
    allowlist = build_sync_allowlist(root, content_root=root / "0vault")
    reconciler = _reconciler(_descriptor(root, allowlist))

    description = (await reconciler.describe(VaultKind.PERSONAL, OWNER)).value

    assert description.vault_configured is True
    assert description.whole_vault_open is True
    assert description.allowed_folders == ()


@pytest.mark.asyncio
async def test_empty_allowlist_is_fail_closed_not_whole_vault(tmp_path: Path) -> None:
    """Empty allowed_dirs on a personal vault = wall everything — never 'everything syncs'."""
    root = tmp_path / "personal"
    allowlist = SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset())
    reconciler = _reconciler(_descriptor(root, allowlist))

    description = (await reconciler.describe(VaultKind.PERSONAL, OWNER)).value

    assert description.vault_configured is True
    assert description.whole_vault_open is False
    assert description.allowed_folders == ()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
