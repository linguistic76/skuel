"""Form Templates API security/wiring pins (adapters/inbound/form_templates_api.py).

Testing-gap roadmap item 6 (tranche 2, content/entry cluster): PIN tests over
the FormTemplate PathStep-linking routes — ADMIN role gate (401/403; TEACHER
is not enough for curriculum-side linking), CSRF enforcement, and exact
service args on link/unlink. Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.form_templates_api import create_form_templates_api_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Result

_USER_UID = "user_admin"
_FORM_UID = "form_template_1"
_PS_UID = "ps.core.premeditatio"


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


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    templates: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.ADMIN,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    template_service = MagicMock()
    template_service.link_to_path_step = AsyncMock(return_value=Result.ok(True))
    template_service.unlink_from_path_step = AsyncMock(return_value=Result.ok(True))

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_form_templates_api_routes(app, rt, template_service, user_service=user_service)
    return _Harness(client=TestClient(app), templates=template_service)


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


_LINK_BODY = {"form_template_uid": _FORM_UID, "ps_uid": _PS_UID}


class TestAdminGate:
    def test_link_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = _post_json(harness.client, "/api/form-templates/link-path-step", _LINK_BODY)

        assert response.status_code == 401
        harness.templates.link_to_path_step.assert_not_awaited()

    def test_link_as_teacher_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = _post_json(harness.client, "/api/form-templates/link-path-step", _LINK_BODY)

        assert response.status_code == 403
        harness.templates.link_to_path_step.assert_not_awaited()


class TestCsrfEnforcement:
    def test_link_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/form-templates/link-path-step", json=_LINK_BODY)

        assert response.status_code == 403
        harness.templates.link_to_path_step.assert_not_awaited()


class TestLinking:
    def test_link_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/form-templates/link-path-step", _LINK_BODY)

        assert response.status_code == 200
        harness.templates.link_to_path_step.assert_awaited_once_with(_FORM_UID, _PS_UID)

    def test_unlink_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/form-templates/unlink-path-step", _LINK_BODY)

        assert response.status_code == 200
        harness.templates.unlink_from_path_step.assert_awaited_once_with(_FORM_UID, _PS_UID)


class TestInputGuards:
    def test_link_missing_ps_uid_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            "/api/form-templates/link-path-step",
            {"form_template_uid": _FORM_UID},
        )

        assert response.status_code == 400
        harness.templates.link_to_path_step.assert_not_awaited()
