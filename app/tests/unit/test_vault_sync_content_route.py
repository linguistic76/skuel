"""Unit tests for POST /api/vault/sync/content (ADR-070 Decision 9).

The content-vault sync endpoint is the admin door onto the reconciler — the single
directory-ingest path that replaced the retired POST /api/ingest/directory. It is
admin-only and forwards to VaultReconciler.sync(VaultKind.CONTENT, ...), returning
the VaultSyncStats dict.

Mirrors the fake-rt registry pattern from the former test_ingest_directory_mode.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.exceptions import HTTPException

from adapters.inbound.vault_routes import create_vault_routes
from core.models.enums import UserRole
from core.ports.vault_bridge_protocol import VaultSyncStats
from core.services.vault.vault_descriptor import VaultKind
from core.utils.result_simplified import Result
from tests.fixtures.csrf import attach_csrf


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


def _user_service(is_admin: bool) -> MagicMock:
    role = UserRole.ADMIN if is_admin else UserRole.MEMBER
    user = SimpleNamespace(role=role, uid="user_admin")
    user.has_permission = lambda _required: is_admin
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


def _request(body: bytes = b""):
    request = SimpleNamespace()
    request.session = {"user_uid": "user_admin"}
    request.method = "POST"
    request.url = SimpleNamespace(path="/api/vault/sync/content")
    request.body = AsyncMock(return_value=body)
    return attach_csrf(request)


def _routes(is_admin: bool) -> tuple[_RouteRegistry, MagicMock]:
    registry = _RouteRegistry()
    reconciler = MagicMock()
    create_vault_routes(
        app=None,
        rt=registry,
        vault_reconciler=reconciler,
        user_service=_user_service(is_admin),
    )
    return registry, reconciler


class TestVaultSyncContentRoute:
    @pytest.mark.asyncio
    async def test_admin_syncs_content_vault_via_reconciler(self) -> None:
        registry, reconciler = _routes(is_admin=True)
        reconciler.sync = AsyncMock(return_value=Result.ok(VaultSyncStats(entries_ingested=3)))

        handler = registry.get("/api/vault/sync/content", "POST")
        response = await handler(_request())

        assert response.status_code == 200
        # Scoped to CONTENT; sync ignores the acting user for the content vault,
        # but the handler forwards current_user.uid all the same. An empty body
        # defaults to a normal (non-force) sync.
        reconciler.sync.assert_awaited_once_with(VaultKind.CONTENT, "user_admin", force=False)
        body = json.loads(response.body)
        assert body["entries_ingested"] == 3

    @pytest.mark.asyncio
    async def test_force_body_flag_threads_to_reconciler(self) -> None:
        registry, reconciler = _routes(is_admin=True)
        reconciler.sync = AsyncMock(return_value=Result.ok(VaultSyncStats(entries_ingested=5)))

        handler = registry.get("/api/vault/sync/content", "POST")
        response = await handler(_request(body=b'{"force": true}'))

        assert response.status_code == 200
        reconciler.sync.assert_awaited_once_with(VaultKind.CONTENT, "user_admin", force=True)

    @pytest.mark.asyncio
    async def test_malformed_body_is_rejected_before_reconciler(self) -> None:
        registry, reconciler = _routes(is_admin=True)
        reconciler.sync = AsyncMock()

        handler = registry.get("/api/vault/sync/content", "POST")
        response = await handler(_request(body=b"{not json"))

        assert response.status_code == 400
        reconciler.sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_force_value_is_rejected_before_reconciler(self) -> None:
        """StrictBool: a truthy STRING must be rejected, not coerced — lax bool
        would accept '"true"'/'"yes"' and silently trigger a force campaign."""
        registry, reconciler = _routes(is_admin=True)
        reconciler.sync = AsyncMock()

        handler = registry.get("/api/vault/sync/content", "POST")
        for body in (b'{"force": "true"}', b'{"force": "yes"}', b'{"force": 1}'):
            response = await handler(_request(body=body))
            assert response.status_code == 400, f"body {body!r} must be rejected"
        reconciler.sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_admin_is_denied_before_reconciler(self) -> None:
        registry, reconciler = _routes(is_admin=False)
        reconciler.sync = AsyncMock()

        handler = registry.get("/api/vault/sync/content", "POST")
        with pytest.raises(HTTPException) as exc_info:
            await handler(_request())

        assert exc_info.value.status_code == 403
        reconciler.sync.assert_not_called()
