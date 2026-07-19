"""LifePath API security/wiring pins (adapters/inbound/lifepath_api.py).

Testing-gap roadmap item 6 (tranche 2, learning-loop cluster): PIN tests over
the LifePath JSON API — auth gate (401), CSRF enforcement on the mutating
routes (403), Pydantic body validation refusing before the service (400 — the
tranche-1 divergence note: JSON-body validation errors surface as 400 here,
not the documented 422), and exact service args on the happy paths. Harness
mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.lifepath_api import create_lifepath_api_routes
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_LP_UID = "lp.core.stoicism"
_VISION = "Become a person who lives deliberately."


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    service: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    service = MagicMock()
    service.get_full_status = AsyncMock(return_value=Result.ok({"has_life_path": False}))
    service.capture_and_recommend = AsyncMock(return_value=Result.ok({"recommendations": []}))
    service.designate_and_calculate = AsyncMock(return_value=Result.ok({"designated": True}))
    service.get_alignment = AsyncMock(return_value=Result.ok({"alignment_score": 0.0}))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.lifepath_api.require_authenticated_user", _fake_auth)

    create_lifepath_api_routes(app, rt, service)
    return _Harness(client=TestClient(app), service=service)


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


class TestAuthGate:
    def test_status_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/lifepath/status")

        assert response.status_code == 401
        harness.service.get_full_status.assert_not_awaited()


class TestCsrfEnforcement:
    def test_vision_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/lifepath/vision", json={"vision_statement": _VISION})

        assert response.status_code == 403
        harness.service.capture_and_recommend.assert_not_awaited()


class TestInputGuards:
    def test_vision_too_short_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # CaptureVisionRequest requires >= 10 chars; body validation errors
        # surface as 400 (parse_json_body → Errors.validation), not 422.
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/lifepath/vision", {"vision_statement": "x"})

        assert response.status_code == 400
        harness.service.capture_and_recommend.assert_not_awaited()


class TestHappyPaths:
    def test_capture_vision_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/lifepath/vision", {"vision_statement": _VISION})

        assert response.status_code == 200
        harness.service.capture_and_recommend.assert_awaited_once_with(_USER_UID, _VISION)

    def test_designate_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/lifepath/designate", {"life_path_uid": _LP_UID})

        assert response.status_code == 200
        harness.service.designate_and_calculate.assert_awaited_once_with(_USER_UID, _LP_UID)

    def test_alignment_scopes_to_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/lifepath/alignment")

        assert response.status_code == 200
        harness.service.get_alignment.assert_awaited_once_with(_USER_UID)
