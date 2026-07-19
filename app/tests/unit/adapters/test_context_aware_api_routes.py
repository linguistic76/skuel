"""Context-Aware API security/wiring pins (adapters/inbound/context_aware_api.py).

Testing-gap roadmap item 6 (tranche 2, analytics/insight cluster): PIN tests
over the UserContext routes — auth gate (401), CSRF on the mutating context
integrations (403), the time_window whitelist guard (400 before the service),
and exact service kwargs on dashboard and contextual task completion. Harness
mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.context_aware_api import create_context_aware_api_routes
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from core.models.task.task import Task
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_TASK_UID = "task_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    context: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    service = MagicMock()
    service.get_context_dashboard = AsyncMock(return_value=Result.ok({"widgets": []}))
    service.get_context_summary = AsyncMock(return_value=Result.ok({"insights": []}))
    service.get_next_action = AsyncMock(return_value=Result.ok({"action": "rest"}))
    service.complete_task_with_context = AsyncMock(
        return_value=Result.ok(Task(uid=_TASK_UID, title="T", user_uid=_USER_UID))
    )
    service.get_at_risk_habits = AsyncMock(return_value=Result.ok({"habits": []}))
    service.get_context_health = AsyncMock(return_value=Result.ok({"score": 1.0}))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.context_aware_api.require_authenticated_user", _fake_auth
        )

    create_context_aware_api_routes(None, rt, service)
    return _Harness(client=TestClient(app), context=service)


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


class TestAuthGate:
    def test_dashboard_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/context/dashboard")

        assert response.status_code == 401
        harness.context.get_context_dashboard.assert_not_awaited()


class TestCsrfEnforcement:
    def test_task_complete_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            f"/api/context/task/complete?task_uid={_TASK_UID}",
            json={"context": {}},
        )

        assert response.status_code == 403
        harness.context.complete_task_with_context.assert_not_awaited()


class TestDashboard:
    def test_defaults_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/context/dashboard")

        assert response.status_code == 200
        harness.context.get_context_dashboard.assert_awaited_once_with(
            user_uid=_USER_UID, include_predictions=True, time_window="7d"
        )

    def test_invalid_time_window_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/context/dashboard?time_window=42d")

        assert response.status_code == 400
        harness.context.get_context_dashboard.assert_not_awaited()


class TestTaskCompletion:
    def test_complete_forwards_exact_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            f"/api/context/task/complete?task_uid={_TASK_UID}",
            {"context": {"energy": "high"}, "reflection": "went well"},
        )

        assert response.status_code == 200
        harness.context.complete_task_with_context.assert_awaited_once_with(
            task_uid=_TASK_UID,
            user_uid=_USER_UID,
            completion_context={"energy": "high"},
            reflection_notes="went well",
        )


class TestAnalyticsReads:
    def test_health_scopes_to_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/context/health")

        assert response.status_code == 200
        harness.context.get_context_health.assert_awaited_once_with(_USER_UID)
