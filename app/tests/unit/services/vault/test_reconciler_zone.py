"""A vault sync runs in the vault's zone (UTC arc, PR 2b).

Every calendar value a sync writes — the ``✅`` date on a completed task's line,
the completion date a vault check stamps, an undated event's day — is read deep
in the ingest from ``current_zone()``. The sync resolves the zone once: the
personal vault's owner's (``UserService.get_user_zone``), whichever door started
it — the Sync button (a request, possibly for a user on another zone) or
``./dev vault-sync`` (no request at all); the app default for the content vault,
whose curriculum is no one user's calendar. The zone in force before the sync
is restored after it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.ingestion.config import SyncAllowlist
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler
from core.utils.result_simplified import Result
from core.utils.zone_context import current_zone, zone_scope

pytestmark = pytest.mark.asyncio

OWNER = UserUID("user_owner")
ADMIN = UserUID("user_admin")
BANGKOK = ZoneInfo("Asia/Bangkok")
PARIS = ZoneInfo("Europe/Paris")


def _descriptor(kind: VaultKind, root: Path, owner: UserUID) -> VaultDescriptor:
    return VaultDescriptor(
        kind=kind,
        root=root,
        owner_uid=owner,
        allowlist=SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset()),
        bridge=cast("VaultBridgePort", object()),
        supports_task_round_trip=kind is VaultKind.PERSONAL,
    )


def _reconciler(tmp_path: Path, zones_seen: list[ZoneInfo]) -> tuple[VaultReconciler, Mock]:
    async def ingest(*_args: object, **_kwargs: object) -> Result[None]:
        zones_seen.append(current_zone())
        return Result.ok(None)

    ingestion = Mock()
    ingestion.ingest_directory = AsyncMock(side_effect=ingest)
    owner = Mock()
    owner.preferences.vault_write_consent = True
    user_service = Mock()
    user_service.get_user = AsyncMock(return_value=Result.ok(owner))
    user_service.get_user_zone = AsyncMock(return_value=Result.ok(BANGKOK))
    user_entry = Mock()
    user_entry.list_for_user = AsyncMock(return_value=Result.ok([]))
    user_entry.read_graph_clock = AsyncMock(return_value=Result.ok(datetime.now(UTC)))
    user_entry.list_vault_retired_tasks = AsyncMock(return_value=Result.ok([]))
    registry = VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, tmp_path / "content", ADMIN),
        personal=_descriptor(VaultKind.PERSONAL, tmp_path / "personal", OWNER),
    )
    reconciler = VaultReconciler(
        registry=registry,
        unified_ingestion=ingestion,
        user_entry_service=user_entry,
        tasks_service=Mock(),
        user_service=user_service,
    )
    return reconciler, user_service


async def test_a_personal_sync_ingests_in_the_owners_zone(tmp_path: Path) -> None:
    zones_seen: list[ZoneInfo] = []
    reconciler, user_service = _reconciler(tmp_path, zones_seen)

    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    user_service.get_user_zone.assert_awaited_once_with(OWNER)
    assert zones_seen == [BANGKOK]


async def test_the_owners_zone_wins_over_the_requests_and_is_restored_after(
    tmp_path: Path,
) -> None:
    zones_seen: list[ZoneInfo] = []
    reconciler, _ = _reconciler(tmp_path, zones_seen)

    with zone_scope(PARIS):  # the zone the request's middleware set
        result = await reconciler.sync(VaultKind.PERSONAL, OWNER)
        assert current_zone() == PARIS

    assert result.is_ok
    assert zones_seen == [BANGKOK]


async def test_the_content_vault_syncs_in_the_app_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SKUEL_TIMEZONE", raising=False)
    zones_seen: list[ZoneInfo] = []
    reconciler, user_service = _reconciler(tmp_path, zones_seen)

    with zone_scope(PARIS):  # an admin on another zone pressed "Sync content vault"
        result = await reconciler.sync(VaultKind.CONTENT, ADMIN)

    assert result.is_ok
    user_service.get_user_zone.assert_not_awaited()
    assert zones_seen == [ZoneInfo("America/Vancouver")]
