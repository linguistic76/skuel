"""
Device route tests (ADR-075 B2) — fake-rt pattern (see test_vault_sync_preview.py).

Covers: the one-time pairing-code fragment, HTMX revocation (including
closing the live agent session), and the code-authenticated enrollment API's
status shapes — happy 201, uniform 404 for invalid codes (no oracle), 400 for
malformed bodies.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from adapters.inbound.agent_channel_registry import (
    AgentSession,
    agent_channel_registry,
)
from adapters.inbound.device_routes import create_device_routes
from core.models.auth.device import Device, PairingCodeIssued
from core.utils.result_simplified import Errors, Result
from tests.fixtures.csrf import attach_csrf


@pytest.fixture(autouse=True)
def _enforce_csrf(monkeypatch) -> None:
    """csrf_protected reads env at call time — pin enforcement ON; the
    request stubs carry a real minted token pair (attach_csrf)."""
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


@pytest.fixture(autouse=True)
def _clean_registry():
    """The routes use the module-level registry singleton — keep tests isolated."""
    agent_channel_registry._sessions.clear()
    yield
    agent_channel_registry._sessions.clear()


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


def _request(body: bytes = b"", form: dict | None = None):
    request = SimpleNamespace()
    request.session = {"user_uid": "user_mike"}
    request.method = "POST"
    request.url = SimpleNamespace(path="/settings/devices")
    request.body = AsyncMock(return_value=body)
    request.form = AsyncMock(return_value=form or {})
    return attach_csrf(request)


def _device(uid: str = "device_ab12cd34", revoked: bool = False) -> Device:
    return Device(
        uid=uid,
        user_uid="user_mike",
        pubkey="pk",
        name="mike-laptop",
        enrolled_at=datetime.now(UTC),
        revoked_at=datetime.now(UTC) if revoked else None,
    )


def _routes(user_service) -> _RouteRegistry:
    registry = _RouteRegistry()
    # app=None: the WS route mounts on the real starlette router only.
    create_device_routes(app=None, rt=registry, user_service=user_service)
    return registry


class FakeWS:
    def __init__(self) -> None:
        self.closed: tuple[int, str | None] | None = None

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = (code, reason)


class TestPairingCodeFragment:
    @pytest.mark.asyncio
    async def test_fragment_shows_code_once_with_expiry(self) -> None:
        user_service = MagicMock()
        user_service.create_device_pairing_code = AsyncMock(
            return_value=Result.ok(
                PairingCodeIssued(
                    code="KAR3MWCS",
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
            )
        )
        handler = _routes(user_service).get("/settings/devices/pairing-code")

        html = to_xml(await handler(_request()))

        assert "KAR3MWCS" in html
        assert "Shown once" in html
        assert "single-use" in html

    @pytest.mark.asyncio
    async def test_failure_offers_retry_without_leaking_details(self) -> None:
        user_service = MagicMock()
        user_service.create_device_pairing_code = AsyncMock(
            return_value=Result.fail(Errors.system("boom", operation="devices"))
        )
        handler = _routes(user_service).get("/settings/devices/pairing-code")

        html = to_xml(await handler(_request()))

        assert "Failed to generate" in html
        assert "boom" not in html


class TestRevokeFragment:
    @pytest.mark.asyncio
    async def test_revoke_closes_live_session_and_refreshes_list(self) -> None:
        user_service = MagicMock()
        user_service.revoke_device = AsyncMock(return_value=Result.ok(True))
        user_service.list_devices = AsyncMock(return_value=Result.ok([_device(revoked=True)]))
        ws = FakeWS()
        session = AgentSession(ws, user_uid="user_mike", device_uid="device_ab12cd34")  # type: ignore[arg-type]
        agent_channel_registry.register(session)

        handler = _routes(user_service).get("/settings/devices/revoke")
        html = to_xml(await handler(_request(form={"device_uid": "device_ab12cd34"})))

        user_service.revoke_device.assert_awaited_once_with("user_mike", "device_ab12cd34")
        assert ws.closed is not None  # live channel closed at revocation time
        assert agent_channel_registry.get("user_mike") is None
        assert "Revoked" in html
        assert 'id="devices-list"' in html

    @pytest.mark.asyncio
    async def test_missing_device_uid_is_rejected(self) -> None:
        user_service = MagicMock()
        user_service.revoke_device = AsyncMock()
        handler = _routes(user_service).get("/settings/devices/revoke")

        html = to_xml(await handler(_request(form={})))

        assert "Missing device" in html
        user_service.revoke_device.assert_not_awaited()


class TestEnrollApi:
    @pytest.mark.asyncio
    async def test_happy_path_returns_201_with_device_uid(self) -> None:
        user_service = MagicMock()
        user_service.enroll_device = AsyncMock(return_value=Result.ok(_device()))
        handler = _routes(user_service).get("/api/devices/enroll")

        body = json.dumps(
            {"code": "KAR3MWCS", "device_pubkey": "pk", "device_name": "mike-laptop"}
        ).encode()
        response = await handler(_request(body=body))

        assert response.status_code == 201
        payload = json.loads(response.body)
        assert payload["device_uid"] == "device_ab12cd34"
        user_service.enroll_device.assert_awaited_once_with("KAR3MWCS", "pk", "mike-laptop")

    @pytest.mark.asyncio
    async def test_invalid_code_returns_uniform_404(self) -> None:
        user_service = MagicMock()
        user_service.enroll_device = AsyncMock(
            return_value=Result.fail(Errors.not_found("Pairing code"))
        )
        handler = _routes(user_service).get("/api/devices/enroll")

        body = json.dumps(
            {"code": "WRONGCOD", "device_pubkey": "pk", "device_name": "laptop"}
        ).encode()
        response = await handler(_request(body=body))

        assert response.status_code == 404
        # No oracle: the body names the pairing code, never enrollment state.
        assert b"pubkey" not in response.body.lower()

    @pytest.mark.asyncio
    async def test_malformed_body_returns_400_without_touching_the_service(self) -> None:
        user_service = MagicMock()
        user_service.enroll_device = AsyncMock()
        handler = _routes(user_service).get("/api/devices/enroll")

        response = await handler(_request(body=b"not-json"))

        assert response.status_code == 400
        user_service.enroll_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_fields_return_400(self) -> None:
        user_service = MagicMock()
        user_service.enroll_device = AsyncMock()
        handler = _routes(user_service).get("/api/devices/enroll")

        response = await handler(_request(body=json.dumps({"code": "X"}).encode()))

        assert response.status_code == 400
        user_service.enroll_device.assert_not_awaited()


class TestRevokeApi:
    @pytest.mark.asyncio
    async def test_unowned_device_returns_404_not_403(self) -> None:
        user_service = MagicMock()
        user_service.revoke_device = AsyncMock(return_value=Result.ok(False))
        handler = _routes(user_service).get("/api/devices/{uid}/revoke")

        response = await handler(_request(), uid="device_someone1")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_returns_200_and_closes_session(self) -> None:
        user_service = MagicMock()
        user_service.revoke_device = AsyncMock(return_value=Result.ok(True))
        ws = FakeWS()
        session = AgentSession(ws, user_uid="user_mike", device_uid="device_ab12cd34")  # type: ignore[arg-type]
        agent_channel_registry.register(session)

        handler = _routes(user_service).get("/api/devices/{uid}/revoke")
        response = await handler(_request(), uid="device_ab12cd34")

        assert response.status_code == 200
        assert json.loads(response.body)["revoked"] is True
        assert ws.closed is not None
