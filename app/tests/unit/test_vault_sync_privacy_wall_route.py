"""Privacy-wall fragments on the vault sync surfaces (vault security arc PR 6).

The consent form and the sync page's "What SKUEL can see" panel must render the
folder wall from the LIVE ``VaultReconciler.describe`` data — never hardcoded
prose — so what the user consents to is what the allowlist actually enforces.

Handlers come from ``tests/helpers/route_collector.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from adapters.inbound.vault_routes import create_vault_routes
from core.ports.vault_bridge_protocol import VaultSyncStats
from core.services.vault.vault_reconciler import VaultDescription
from core.utils.result_simplified import Result
from tests.fixtures.csrf import attach_csrf
from tests.helpers.route_collector import route_collector
from ui.vault.sync_fragments import privacy_wall_panel


def _request(method: str = "POST", path: str = "/settings/vault/sync"):
    request = SimpleNamespace()
    request.session = {"user_uid": "user_owner"}
    request.method = method
    request.url = SimpleNamespace(path=path)
    return attach_csrf(request)


_DOORWAYS = VaultDescription(
    vault_configured=True,
    allowed_folders=("activity_notes", "knowledge", "periodic_notes", "personal_notes"),
)


class TestConsentFormShowsLiveWall:
    @pytest.mark.asyncio
    async def test_first_run_consent_form_lists_described_folders(self) -> None:
        rt, registry = route_collector()
        reconciler = MagicMock()
        reconciler.sync = AsyncMock(return_value=Result.ok(VaultSyncStats(first_run_notice=True)))
        reconciler.describe = AsyncMock(return_value=Result.ok(_DOORWAYS))
        create_vault_routes(rt=rt, vault_reconciler=reconciler, user_service=MagicMock())

        handler = registry["/settings/vault/sync", "POST"]
        html = to_xml(await handler(_request()))

        reconciler.describe.assert_called_once()
        assert "Allow SKUEL to sync" in html
        for folder in _DOORWAYS.allowed_folders:
            assert f"{folder}/" in html
        assert "nothing else" in html


class TestSyncPageRender:
    """Full-page render of /submissions/sync — NOT covered by the render smoke."""

    @pytest.mark.asyncio
    async def test_configured_vault_page_shows_wall_and_both_doors(self) -> None:
        rt, registry = route_collector()
        reconciler = MagicMock()
        reconciler.describe = AsyncMock(return_value=Result.ok(_DOORWAYS))
        create_vault_routes(rt=rt, vault_reconciler=reconciler, user_service=MagicMock())

        handler = registry["/submissions/sync", "GET"]
        html = to_xml(await handler(_request(method="GET", path="/submissions/sync")))

        assert "Obsidian Sync" in html
        assert "What SKUEL can see" in html
        for folder in _DOORWAYS.allowed_folders:
            assert f"{folder}/" in html
        # Both HTMX doors plus the swap target the fragments post into.
        assert 'hx-post="/settings/vault/sync"' in html
        assert 'hx-post="/settings/vault/preview"' in html
        assert 'id="vault-results"' in html

    @pytest.mark.asyncio
    async def test_unconfigured_vault_page_says_nothing_is_read(self) -> None:
        rt, registry = route_collector()
        reconciler = MagicMock()
        reconciler.describe = AsyncMock(
            return_value=Result.ok(VaultDescription(vault_configured=False))
        )
        create_vault_routes(rt=rt, vault_reconciler=reconciler, user_service=MagicMock())

        handler = registry["/submissions/sync", "GET"]
        html = to_xml(await handler(_request(method="GET", path="/submissions/sync")))

        assert "No personal vault is configured" in html
        assert 'hx-post="/settings/vault/sync"' not in html


class TestPrivacyWallFragments:
    def test_folder_wall_lists_each_folder_as_mono_dir(self) -> None:
        html = to_xml(privacy_wall_panel(_DOORWAYS))

        assert "What SKUEL can see" in html
        for folder in _DOORWAYS.allowed_folders:
            assert f"{folder}/" in html
        assert "never read, never searched" in html

    def test_empty_personal_wall_is_honest_not_everything(self) -> None:
        """Fail-closed empty allowlist → 'nothing is synced', never 'everything'."""
        html = to_xml(privacy_wall_panel(VaultDescription(vault_configured=True)))

        assert "No folders are currently synced" in html
        assert "whole vault" not in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
