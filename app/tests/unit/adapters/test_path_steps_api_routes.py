"""Path Steps API security/wiring pins (adapters/inbound/path_steps_api.py).

Testing-gap roadmap item 6 (tranche 2, learning-loop cluster): PIN tests over
the domain-specific PathStep routes — the ADMIN role gate on every curriculum
write (401/403; SHARED-scope domain, reads are public), CSRF enforcement on
mutations, exact service args on the ORGANIZES-hierarchy and step-path happy
paths, the SEL-category input guard refusing before the service, and the
unwired-user-service seam on my-context. Harness mirrors
``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.path_steps_api import create_path_steps_api_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Result

_USER_UID = "user_admin"
_PARENT_UID = "ps.core.parent"
_CHILD_UID = "ps.core.child"
_PATH_UID = "lp.core.stoicism"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


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
    ps: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.ADMIN,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    ps_service = MagicMock()
    ps_service.attach_step_to_path = AsyncMock(return_value=Result.ok(True))
    ps_service.detach_step_from_path = AsyncMock(return_value=Result.ok(True))
    ps_service.update_step_content = AsyncMock(return_value=Result.ok({"uid": _CHILD_UID}))
    ps_service.organize = AsyncMock(return_value=Result.ok(True))
    ps_service.unorganize = AsyncMock(return_value=Result.ok(True))
    ps_service.reorder = AsyncMock(return_value=Result.ok(True))
    ps_service.get_personalized_curriculum = AsyncMock(return_value=Result.ok([]))
    ps_service.relationships.get_related_uids = AsyncMock(return_value=Result.ok([]))

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.path_steps_api.require_authenticated_user", _fake_auth
        )
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_path_steps_api_routes(app, rt, ps_service, user_service=user_service)
    return _Harness(client=TestClient(app), ps=ps_service)


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


_ORGANIZE_BODY = {"parent_uid": _PARENT_UID, "child_uid": _CHILD_UID, "order": 2}


class TestAdminGate:
    def test_organize_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = _post_json(harness.client, "/api/path-steps/organize", _ORGANIZE_BODY)

        assert response.status_code == 401
        harness.ps.organize.assert_not_awaited()

    def test_organize_as_teacher_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Curriculum writes are ADMIN-only; TEACHER is not enough here.
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = _post_json(harness.client, "/api/path-steps/organize", _ORGANIZE_BODY)

        assert response.status_code == 403
        harness.ps.organize.assert_not_awaited()

    def test_attach_to_path_as_member_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = _post_json(
            harness.client,
            f"/api/path-steps/attach-to-path?step_uid={_CHILD_UID}",
            {"path_uid": _PATH_UID, "sequence": 3},
        )

        assert response.status_code == 403
        harness.ps.attach_step_to_path.assert_not_awaited()


class TestCsrfEnforcement:
    def test_organize_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/path-steps/organize", json=_ORGANIZE_BODY)

        assert response.status_code == 403
        harness.ps.organize.assert_not_awaited()


class TestOrganizesHierarchy:
    def test_organize_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/path-steps/organize", _ORGANIZE_BODY)

        assert response.status_code == 201
        payload = response.json()
        assert payload["parent_uid"] == _PARENT_UID
        assert payload["child_uid"] == _CHILD_UID
        harness.ps.organize.assert_awaited_once_with(_PARENT_UID, _CHILD_UID, 2)

    def test_reorder_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            "/api/path-steps/reorder",
            {"parent_uid": _PARENT_UID, "child_uid": _CHILD_UID, "new_order": 5},
        )

        assert response.status_code == 200
        harness.ps.reorder.assert_awaited_once_with(_PARENT_UID, _CHILD_UID, 5)


class TestStepPathRelationships:
    # These six admin write routes (attach/detach, relationships POST, content,
    # tags POST/DELETE) 400'd unconditionally until this tranche: non-defaulted
    # ``current_user: Any`` made FastHTML treat it as a required request field
    # (the PR #702 bug class — these *_api.py sites were missed there). The
    # happy paths below pin the restored wiring.

    def test_attach_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            f"/api/path-steps/attach-to-path?step_uid={_CHILD_UID}",
            {"path_uid": _PATH_UID, "sequence": 3},
        )

        assert response.status_code == 200
        harness.ps.attach_step_to_path.assert_awaited_once_with(_CHILD_UID, _PATH_UID, 3)

    def test_detach_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            f"/api/path-steps/detach-from-path?step_uid={_CHILD_UID}",
            {"path_uid": _PATH_UID},
        )

        assert response.status_code == 200
        harness.ps.detach_step_from_path.assert_awaited_once_with(_CHILD_UID, _PATH_UID)

    def test_update_content_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            f"/api/path-steps/content?uid={_CHILD_UID}",
            {"content": "New lesson body", "title": "New title"},
        )

        assert response.status_code == 200
        harness.ps.update_step_content.assert_awaited_once_with(
            _CHILD_UID, "New lesson body", "New title"
        )


class TestInputGuards:
    def test_invalid_sel_category_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/path-steps/curriculum/not-a-category")

        assert response.status_code == 400
        harness.ps.get_personalized_curriculum.assert_not_awaited()


class TestUserContextSeam:
    def test_my_context_without_user_service_is_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.ps.user_service = None

        response = harness.client.get("/api/path-steps/my-context?uid=" + _CHILD_UID)

        assert response.status_code == 500


class TestPublicReads:
    def test_prerequisites_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(f"/api/path-steps/prerequisites?step_uid={_CHILD_UID}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["step_uid"] == _CHILD_UID
        assert payload["has_prerequisites"] is False
