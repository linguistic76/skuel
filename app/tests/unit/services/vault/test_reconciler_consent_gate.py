"""VaultReconciler first-run consent gates the ENTIRE sync — read included.

ADR-070 Decision 6 (amended 2026-07-05, vault security review): the first
"Sync from Obsidian" click used to ingest the user's whole allowed vault tree
BEFORE fetching the user and checking ``vault_write_consent`` — consent only
guarded outbound writes. The gate now fires before the first inbound
``ingest_directory`` call: no consent → ``first_run_notice`` with NOTHING read.

The CONTENT vault (admin, inbound-only, no task round-trip) stays consent-free.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

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
from core.utils.result_simplified import Result

pytestmark = pytest.mark.asyncio

OWNER = UserUID("user_owner")
ADMIN = UserUID("user_admin")


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


def _split_root_registry(tmp_path: Path) -> VaultRegistry:
    """Split-root config: content and personal are sibling directories."""
    return VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, tmp_path / "content", str(ADMIN)),
        personal=_descriptor(VaultKind.PERSONAL, tmp_path / "personal", str(OWNER)),
    )


def _user_service(*, consent: bool) -> Mock:
    user = Mock()
    user.preferences.vault_write_consent = consent
    service = Mock()
    service.get_user = AsyncMock(return_value=Result.ok(user))
    return service


def _ingestion() -> Mock:
    service = Mock()
    service.ingest_directory = AsyncMock(return_value=Result.ok(None))
    return service


def _reconciler(registry: VaultRegistry, ingestion: Mock, user_service: Mock) -> VaultReconciler:
    user_entry = Mock()
    user_entry.list_for_user = AsyncMock(return_value=Result.ok([]))
    return VaultReconciler(
        registry=registry,
        unified_ingestion=ingestion,
        user_entry_service=user_entry,
        tasks_service=Mock(),
        user_service=user_service,
    )


async def test_first_sync_without_consent_reads_nothing(tmp_path: Path) -> None:
    """No consent → first_run_notice AND zero inbound ingest (the security fix)."""
    ingestion = _ingestion()
    reconciler = _reconciler(
        _split_root_registry(tmp_path), ingestion, _user_service(consent=False)
    )

    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    assert result.value.first_run_notice is True
    # The gate fires BEFORE the first inbound read — nothing is ingested.
    ingestion.ingest_directory.assert_not_called()


async def test_sync_with_consent_proceeds_to_ingest(tmp_path: Path) -> None:
    ingestion = _ingestion()
    reconciler = _reconciler(_split_root_registry(tmp_path), ingestion, _user_service(consent=True))

    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    assert result.value.first_run_notice is False
    ingestion.ingest_directory.assert_called_once()


async def test_content_sync_never_checks_consent(tmp_path: Path) -> None:
    """CONTENT is admin inbound-only: consent-free, still ingests."""
    ingestion = _ingestion()
    user_service = _user_service(consent=False)
    reconciler = _reconciler(_split_root_registry(tmp_path), ingestion, user_service)

    result = await reconciler.sync(VaultKind.CONTENT, ADMIN)

    assert result.is_ok
    assert result.value.first_run_notice is False
    user_service.get_user.assert_not_called()
    ingestion.ingest_directory.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
