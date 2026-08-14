"""System API security/wiring pins (adapters/inbound/system_api.py).

Testing-gap roadmap item 6 (tranche 2, system/infra cluster): PIN tests over
the system monitoring surface — the January-2026 hardening (every /api/*
system endpoint is ADMIN-only: 401/403), the deliberately-public load-balancer
probes (/health, /health/ready), CSRF on mutations, and the readiness probe's
degraded contract (Errors.integration → HTTP 502 — the docstrings say 503;
pinned as-is, divergence noted). Harness mirrors
``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.system_api import create_system_api_routes
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


def _healthy_status() -> dict[str, object]:
    return {
        "status": "healthy",
        "timestamp": "2026-07-18T00:00:00+00:00",
        "healthy": True,
        "components": {},
    }


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    system: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.ADMIN,
    healthy: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    status = _healthy_status()
    if not healthy:
        status["healthy"] = False
        status["status"] = "degraded"

    system = MagicMock()
    system.get_health_status = AsyncMock(return_value=Result.ok(status))
    system.get_health_summary = AsyncMock(
        return_value=Result.ok(
            {
                "healthy": True,
                "timestamp": "2026-07-18T00:00:00+00:00",
                "components_total": 1,
                "components_healthy": 1,
                "components_unhealthy": 0,
            }
        )
    )
    system.get_system_info = AsyncMock(
        return_value=Result.ok({"version": "2.0.0", "service": "SKUEL", "components_registered": 3})
    )

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_system_api_routes(app, rt, system, user_service=user_service)
    return _Harness(client=TestClient(app), system=system)


class TestPublicProbes:
    def test_liveness_needs_no_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Deliberately public — load-balancers and k8s probes carry no session.
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_readiness_ok_when_healthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/health/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_readiness_sheds_traffic_when_degraded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Pinned as-is: Errors.integration maps to 502 (docstring says 503).
        # Either way the LB sheds traffic; the pin is "not 200".
        harness = _make_harness(monkeypatch, authenticated=False, healthy=False)

        response = harness.client.get("/health/ready")

        assert response.status_code == 502


class TestAdminGate:
    def test_api_health_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/health")

        assert response.status_code == 401
        harness.system.get_health_status.assert_not_awaited()

    def test_api_health_as_member_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # January-2026 hardening: system internals are admin-only.
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = harness.client.get("/api/health")

        assert response.status_code == 403
        harness.system.get_health_status.assert_not_awaited()

    def test_api_diagnostics_as_teacher_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = harness.client.get("/api/diagnostics")

        assert response.status_code == 403


class TestAdminReads:
    def test_api_health_happy_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/health")

        assert response.status_code == 200
        payload = response.json()
        assert payload["healthy"] is True
        assert payload["service"] == "SKUEL"

    def test_api_health_degraded_is_502(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, healthy=False)

        response = harness.client.get("/api/health")

        assert response.status_code == 502

    def test_version_happy_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/version")

        assert response.status_code == 200
        assert response.json()["version"] == "2.0.0"


class TestCsrfEnforcement:
    def test_register_service_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/services/register", json={"name": "x"})

        assert response.status_code == 403
