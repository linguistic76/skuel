"""Admin gate pins for the auth debug routes (adapters/inbound/auth_api.py).

``/debug-session`` dumps raw session internals and ``/whoami`` exposes user
identity — both are safe ONLY because ``@require_admin`` is wired on them.
These tests pin that wiring: 401 unauthenticated, 403 below admin, content for
admins.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.auth_api import create_auth_api_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Result

_ADMIN_UID = "user_admin"


def _fake_admin_auth(request: object) -> str:
    return _ADMIN_UID


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    role: UserRole = UserRole.ADMIN,
    authenticated: bool = True,
) -> TestClient:
    app, rt = fast_app(pico=False, default_hdrs=False)

    user = MagicMock()
    user.uid = _ADMIN_UID
    user.role = role
    user.has_permission = MagicMock(return_value=role == UserRole.ADMIN)
    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(user))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.auth.roles.require_authenticated_user",
            _fake_admin_auth,
        )

    create_auth_api_routes(app, rt, graph_auth=MagicMock(), user_service=user_service)
    return TestClient(app)


@pytest.mark.parametrize("path", ["/debug-session", "/whoami"])
class TestDebugRoutesAdminGate:
    def test_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
        client = _make_client(monkeypatch, authenticated=False)

        assert client.get(path).status_code == 401

    def test_member_is_403(self, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
        client = _make_client(monkeypatch, role=UserRole.MEMBER)

        assert client.get(path).status_code == 403

    def test_teacher_is_403(self, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
        client = _make_client(monkeypatch, role=UserRole.TEACHER)

        assert client.get(path).status_code == 403

    def test_admin_sees_page(self, monkeypatch: pytest.MonkeyPatch, path: str) -> None:
        client = _make_client(monkeypatch)

        response = client.get(path)

        assert response.status_code == 200
        assert "Admin" in response.text
