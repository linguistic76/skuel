"""``POST /api/user/display-name``: the Account card's save on ``/settings``.

Real requests through a FastHTML app: the session gate (401), CSRF (403), each
name the door refuses (400, nothing written), the trim, and the two answers: the
card re-rendered for HTMX, ``{display_name}`` for a JSON caller.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.settings_routes import create_settings_routes
from core.models.user import create_user
from core.models.user.user import DISPLAY_NAME_MAX_LENGTH
from core.utils.auth_context import AuthState, auth_state_var
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_namer"
_DOOR = "/api/user/display-name"
_HTMX = {"HX-Request": "true"}


def _fake_auth(request: object) -> str:
    return _USER_UID


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    user_service: MagicMock


def _make_harness(monkeypatch: pytest.MonkeyPatch, *, authenticated: bool = True) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)
    stored = create_user(username="namer", email="namer@example.com", display_name="Old Name")

    async def update_display_name(_user_uid: str, name: str) -> Result:
        return Result.ok(dataclasses.replace(stored, display_name=name))

    user_service = MagicMock()
    user_service.update_display_name = AsyncMock(side_effect=update_display_name)
    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.settings_routes.require_authenticated_user", _fake_auth
        )
    create_settings_routes(rt, SimpleNamespace(user=user_service))
    return _Harness(client=TestClient(app), user_service=user_service)


def _csrf(client: TestClient) -> dict[str, str]:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


@pytest.fixture
def signed_in_as_old_name():
    """The request's auth context, as the middleware sets it: the stored name."""
    token = auth_state_var.set(AuthState(user_uid=_USER_UID, display_name="Old Name"))
    yield
    auth_state_var.reset(token)


class TestGates:
    def test_no_session_is_401_and_writes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)
        response = harness.client.post(
            _DOOR, json={"display_name": "New"}, headers=_csrf(harness.client)
        )
        assert response.status_code == 401
        harness.user_service.update_display_name.assert_not_awaited()

    def test_no_csrf_token_is_403_and_writes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        response = harness.client.post(_DOOR, json={"display_name": "New"})
        assert response.status_code == 403
        harness.user_service.update_display_name.assert_not_awaited()

    def test_get_is_405(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        assert harness.client.get(_DOOR).status_code == 405


class TestJsonCaller:
    def test_the_name_is_trimmed_and_answered_as_stored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)
        response = harness.client.post(
            _DOOR, json={"display_name": "  Ana María  "}, headers=_csrf(harness.client)
        )
        assert response.status_code == 200
        assert response.json() == {"display_name": "Ana María"}
        harness.user_service.update_display_name.assert_awaited_once_with(_USER_UID, "Ana María")

    @pytest.mark.parametrize(
        "body",
        [
            {"display_name": ""},
            {"display_name": "   "},
            {"display_name": "x" * (DISPLAY_NAME_MAX_LENGTH + 1)},
            {"display_name": "two\nlines"},
            {"display_name": "a\ttab"},
            {"display_name": None},
            {},
        ],
        ids=["blank", "spaces", "too-long", "newline", "tab", "null", "absent"],
    )
    def test_a_name_that_is_not_one_is_400_and_writes_nothing(
        self, monkeypatch: pytest.MonkeyPatch, body: dict
    ) -> None:
        harness = _make_harness(monkeypatch)
        response = harness.client.post(_DOOR, json=body, headers=_csrf(harness.client))
        assert response.status_code == 400
        harness.user_service.update_display_name.assert_not_awaited()

    def test_the_longest_name_is_taken(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        name = "x" * DISPLAY_NAME_MAX_LENGTH
        response = harness.client.post(
            _DOOR, json={"display_name": name}, headers=_csrf(harness.client)
        )
        assert response.status_code == 200
        assert response.json() == {"display_name": name}

    def test_a_failed_write_answers_its_own_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.user_service.update_display_name = AsyncMock(
            return_value=Result.fail(Errors.database("set_display_name", "graph down"))
        )
        response = harness.client.post(
            _DOOR, json={"display_name": "New"}, headers=_csrf(harness.client)
        )
        assert response.status_code == 503


@pytest.mark.usefixtures("signed_in_as_old_name")
class TestHtmxForm:
    def test_a_save_answers_the_card_holding_the_stored_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)
        response = harness.client.post(
            _DOOR, data={"display_name": " Bo "}, headers={**_csrf(harness.client), **_HTMX}
        )
        assert response.status_code == 200
        assert "X-SKUEL-Refusal" not in response.headers
        assert 'id="account-card"' in response.text
        assert 'value="Bo"' in response.text
        assert "Saved" in response.text
        harness.user_service.update_display_name.assert_awaited_once_with(_USER_UID, "Bo")

    @pytest.mark.parametrize(
        "typed",
        ["", "   ", "x" * (DISPLAY_NAME_MAX_LENGTH + 1), "two\nlines"],
        ids=["blank", "spaces", "too-long", "newline"],
    )
    def test_a_refusal_renders_into_the_card_with_the_name_the_account_still_has(
        self, monkeypatch: pytest.MonkeyPatch, typed: str
    ) -> None:
        harness = _make_harness(monkeypatch)
        response = harness.client.post(
            _DOOR, data={"display_name": typed}, headers={**_csrf(harness.client), **_HTMX}
        )
        assert response.status_code == 400
        assert response.headers["X-SKUEL-Refusal"] == "rendered"
        assert 'id="account-card"' in response.text
        assert 'value="Old Name"' in response.text
        assert 'role="alert"' in response.text
        assert "Saved" not in response.text
        harness.user_service.update_display_name.assert_not_awaited()

    def test_a_failed_write_renders_into_the_card_at_its_own_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)
        harness.user_service.update_display_name = AsyncMock(
            return_value=Result.fail(Errors.database("set_display_name", "graph down"))
        )
        response = harness.client.post(
            _DOOR, data={"display_name": "New"}, headers={**_csrf(harness.client), **_HTMX}
        )
        assert response.status_code == 503
        assert response.headers["X-SKUEL-Refusal"] == "rendered"
        assert "could not be saved" in response.text
        assert 'value="Old Name"' in response.text
