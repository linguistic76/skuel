"""Auth debug API security pins (adapters/inbound/auth_api.py).

Testing-gap roadmap item 6 (tranche 2, system/infra cluster): PIN tests over
the two admin-only diagnostic pages (/debug-session, /whoami) — they expose
session internals and user identity, so the whole surface is the ADMIN gate
(401/403) plus a rendered-page smoke check. Harness mirrors
``test_choices_api_routes.py``. Complements the handler-level smoke tests in
``test_auth_api_debug_routes.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.auth_api import create_auth_api_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Result

_USER_UID = "user_admin"


def _fake_auth(request: object) -> str:
    return _USER_UID


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = _USER_UID
    user.role = role
    # Role decorators check user.has_permission(required) on the entity —
    # bind the real hierarchy-aware enum method.
    user.has_permission = role.has_permission
    return user


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.ADMIN,
) -> TestClient:
    app, rt = fast_app(pico=False, default_hdrs=False)

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_auth_api_routes(app, rt, graph_auth=MagicMock(), user_service=user_service)
    return TestClient(app)


class TestAdminGate:
    def test_debug_session_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _make_client(monkeypatch, authenticated=False)

        response = client.get("/debug-session")

        assert response.status_code == 401

    def test_debug_session_as_member_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _make_client(monkeypatch, role=UserRole.MEMBER)

        response = client.get("/debug-session")

        assert response.status_code == 403

    def test_whoami_as_teacher_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _make_client(monkeypatch, role=UserRole.TEACHER)

        response = client.get("/whoami")

        assert response.status_code == 403


class TestAdminAccess:
    def test_debug_session_renders_for_admin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _make_client(monkeypatch)

        response = client.get("/debug-session")

        assert response.status_code == 200
        assert "Session Debug" in response.text

    def test_whoami_renders_for_admin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _make_client(monkeypatch)

        response = client.get("/whoami")

        assert response.status_code == 200
        assert "Current User" in response.text
