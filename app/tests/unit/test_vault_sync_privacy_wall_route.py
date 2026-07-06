"""Privacy-wall fragments on the vault sync surfaces (vault security arc PR 6).

The consent form and the sync page's "What SKUEL can see" panel must render the
folder wall from the LIVE ``VaultReconciler.describe`` data — never hardcoded
prose — so what the user consents to is what the allowlist actually enforces.

Mirrors the fake-rt registry pattern from test_vault_sync_content_route.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from adapters.inbound.vault_routes import (
    _consent_form,
    _privacy_wall_panel,
    create_vault_routes,
)
from core.ports.vault_bridge_protocol import VaultSyncStats
from core.services.vault.vault_reconciler import VaultDescription
from core.utils.result_simplified import Result


@pytest.fixture(autouse=True)
def _disable_csrf(monkeypatch) -> None:
    """csrf_protected reads env at call time — force enforcement off for unit tests."""
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")


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
    request.url = SimpleNamespace(path="/settings/vault/sync")
    return request


_DOORWAYS = VaultDescription(
    vault_configured=True,
    allowed_folders=("activity_notes", "knowledge", "periodic_notes", "personal_notes"),
)


class TestConsentFormShowsLiveWall:
    @pytest.mark.asyncio
    async def test_first_run_consent_form_lists_described_folders(self) -> None:
        registry = _RouteRegistry()
        reconciler = MagicMock()
        reconciler.sync = AsyncMock(return_value=Result.ok(VaultSyncStats(first_run_notice=True)))
        reconciler.describe = MagicMock(return_value=Result.ok(_DOORWAYS))
        create_vault_routes(
            app=None, rt=registry, vault_reconciler=reconciler, user_service=MagicMock()
        )

        handler = registry.get("/settings/vault/sync", "POST")
        html = to_xml(await handler(_request()))

        reconciler.describe.assert_called_once()
        assert "Allow SKUEL to sync" in html
        for folder in _DOORWAYS.allowed_folders:
            assert f"{folder}/" in html
        assert "nothing else" in html


class TestPrivacyWallFragments:
    def test_folder_wall_lists_each_folder_as_mono_dir(self) -> None:
        html = to_xml(_privacy_wall_panel(_DOORWAYS))

        assert "What SKUEL can see" in html
        for folder in _DOORWAYS.allowed_folders:
            assert f"{folder}/" in html
        assert "never read, never searched" in html

    def test_empty_personal_wall_is_honest_not_everything(self) -> None:
        """Fail-closed empty allowlist → 'nothing is synced', never 'everything'."""
        html = to_xml(_privacy_wall_panel(VaultDescription(vault_configured=True)))

        assert "No folders are currently synced" in html
        assert "whole vault" not in html

    def test_combined_vault_says_whole_vault_with_staging_exception(self) -> None:
        description = VaultDescription(vault_configured=True, whole_vault_open=True)

        assert "whole vault" in to_xml(_privacy_wall_panel(description))
        assert "je_*" in to_xml(_consent_form(description))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
