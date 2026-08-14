"""User Pins API security/wiring pins (adapters/inbound/user_pins_api.py).

Testing-gap roadmap item 6 (tranche 2, analytics/insight cluster): PIN tests
over the pin/bookmark routes — auth gate (401), CSRF enforcement (403), exact
service args, the HTMX PinButton fragment contract on pin/unpin, and the
reorder body guard. Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.user_pins_api import create_user_pins_routes
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_ENTITY_UID = "task_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    relationships: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    service = MagicMock()
    service.get_pinned_entities = AsyncMock(return_value=Result.ok([_ENTITY_UID]))
    service.pin_entity = AsyncMock(return_value=Result.ok(True))
    service.unpin_entity = AsyncMock(return_value=Result.ok(True))
    service.reorder_pins = AsyncMock(return_value=Result.ok(2))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.user_pins_api.require_authenticated_user", _fake_auth)

    create_user_pins_routes(None, rt, service)
    return _Harness(client=TestClient(app), relationships=service)


def _csrf(client: TestClient) -> dict[str, str]:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


class TestAuthGate:
    def test_get_pins_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/user/pins")

        assert response.status_code == 401
        harness.relationships.get_pinned_entities.assert_not_awaited()


class TestCsrfEnforcement:
    def test_pin_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/user/pins", json={"entity_uid": _ENTITY_UID})

        assert response.status_code == 403
        harness.relationships.pin_entity.assert_not_awaited()

    def test_unpin_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.delete(f"/api/user/pins/{_ENTITY_UID}")

        assert response.status_code == 403
        harness.relationships.unpin_entity.assert_not_awaited()


class TestPinning:
    def test_get_pins_scopes_to_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/user/pins")

        assert response.status_code == 200
        assert response.json() == [_ENTITY_UID]
        harness.relationships.get_pinned_entities.assert_awaited_once_with(_USER_UID)

    def test_pin_json_body_returns_pinned_button_fragment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/user/pins", json={"entity_uid": _ENTITY_UID}, headers=_csrf(harness.client)
        )

        assert response.status_code == 200
        harness.relationships.pin_entity.assert_awaited_once_with(_USER_UID, _ENTITY_UID)

    def test_pin_form_body_also_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # HTMX sends form-encoded bodies — the route falls back to form parsing.
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/user/pins", data={"entity_uid": _ENTITY_UID}, headers=_csrf(harness.client)
        )

        assert response.status_code == 200
        harness.relationships.pin_entity.assert_awaited_once_with(_USER_UID, _ENTITY_UID)

    def test_pin_without_entity_uid_never_touches_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        harness.client.post("/api/user/pins", json={}, headers=_csrf(harness.client))

        harness.relationships.pin_entity.assert_not_awaited()

    def test_unpin_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.delete(
            f"/api/user/pins/{_ENTITY_UID}", headers=_csrf(harness.client)
        )

        assert response.status_code == 200
        harness.relationships.unpin_entity.assert_awaited_once_with(_USER_UID, _ENTITY_UID)


class TestReorder:
    def test_reorder_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/user/pins/reorder",
            json={"ordered_entity_uids": ["task_2", "task_1"]},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 200
        harness.relationships.reorder_pins.assert_awaited_once_with(_USER_UID, ["task_2", "task_1"])

    def test_empty_order_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/user/pins/reorder",
            json={"ordered_entity_uids": []},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 400
        harness.relationships.reorder_pins.assert_not_awaited()
