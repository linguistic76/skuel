"""Admin API security pins (adapters/inbound/admin_api.py).

Pins the highest-blast-radius wiring in the inbound surface: every admin route
sits behind ``@require_admin`` (401 unauthenticated / 403 non-admin), the
hard-delete confirm/reason guards refuse BEFORE the service is touched, CSRF is
enforced on the mutating routes, and the admin-initiated reset-token route only
works with a wired graph_auth. Harness mirrors
``test_journals_discussion_routes.py`` — real ``fast_app`` + CSRF minting.

``TestAccountActionsFromTheDetailPage`` drives the three account actions the
way the admin user detail page does — its form's encoding, its ``HX-Request``
header, the registered ``?uid=`` door — and reads back what the page swaps in.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.admin_api import create_admin_api_routes
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.route_factories.route_helpers import REFUSAL_HEADER, REFUSAL_RENDERED
from core.models.enums import UserRole
from core.models.user.user import User
from core.utils.result_simplified import Errors, Result
from ui.admin.views import account_card_id, user_status_badges_id

_ADMIN_UID = "user_admin"
_TARGET_UID = "user_target"


def _target(role: UserRole = UserRole.MEMBER, *, is_active: bool = True) -> User:
    """The user the action lands on — a real model, since the response renders it."""
    return User(
        uid=_TARGET_UID, title="target", email="t@example.com", role=role, is_active=is_active
    )


def _fake_admin_auth(request: object) -> str:
    return _ADMIN_UID


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = _ADMIN_UID
    user.role = role
    user.title = "admin"
    user.has_permission = MagicMock(return_value=role == UserRole.ADMIN)
    return user


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    role: UserRole = UserRole.ADMIN,
    authenticated: bool = True,
    graph_auth: MagicMock | None = None,
) -> tuple[TestClient, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))
    user_service.list_users = AsyncMock(return_value=Result.ok([]))
    user_service.hard_delete_user = AsyncMock(return_value=Result.ok(42))
    user_service.update_role = AsyncMock(return_value=Result.ok(_target(UserRole.TEACHER)))
    user_service.deactivate_user = AsyncMock(return_value=Result.ok(_target(is_active=False)))
    user_service.activate_user = AsyncMock(return_value=Result.ok(_target(is_active=True)))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.auth.roles.require_authenticated_user",
            _fake_admin_auth,
        )

    create_admin_api_routes(app, rt, user_service, graph_auth=graph_auth)
    return TestClient(app), user_service


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


def _post_form(client: TestClient, path: str, fields: dict[str, str] | None = None):
    """What the detail page sends, with the CSRF header ``skuel.js`` attaches and
    htmx's ``HX-Request``: the role form posts multipart (FastHTML's ``Form`` default
    enctype); a bare button posts an empty url-encoded body."""
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    headers = {CSRF_HEADER_NAME: token, "HX-Request": "true"}
    if fields:
        # httpx builds a multipart body from ``files`` alone; a (None, value) tuple is a
        # plain field.
        return client.post(path, files={k: (None, v) for k, v in fields.items()}, headers=headers)
    return client.post(
        path,
        content=b"",
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    )


class TestAdminGate:
    def test_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch, authenticated=False)

        response = client.get("/api/admin/users")

        assert response.status_code == 401
        service.list_users.assert_not_awaited()

    def test_non_admin_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch, role=UserRole.MEMBER)

        response = client.get("/api/admin/users")

        assert response.status_code == 403
        service.list_users.assert_not_awaited()

    def test_non_admin_cannot_hard_delete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch, role=UserRole.TEACHER)

        response = _post_json(
            client,
            f"/api/admin/users/hard-delete?uid={_TARGET_UID}",
            {"confirm": "erase", "reason": "gdpr request"},
        )

        assert response.status_code == 403
        service.hard_delete_user.assert_not_awaited()

    def test_admin_can_list_users(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = client.get("/api/admin/users")

        assert response.status_code == 200
        service.list_users.assert_awaited_once()


class TestHardDeleteGuards:
    def test_missing_confirm_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = _post_json(
            client,
            f"/api/admin/users/hard-delete?uid={_TARGET_UID}",
            {"reason": "gdpr request"},
        )

        assert response.status_code == 400
        service.hard_delete_user.assert_not_awaited()

    def test_wrong_confirm_string_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        # Close-but-wrong confirmations must not pass the typo guard.
        for confirm in ("Erase", "ERASE", "yes", "delete"):
            response = _post_json(
                client,
                f"/api/admin/users/hard-delete?uid={_TARGET_UID}",
                {"confirm": confirm, "reason": "gdpr request"},
            )
            assert response.status_code == 400, confirm

        service.hard_delete_user.assert_not_awaited()

    def test_blank_reason_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        for reason in ("", "   "):
            response = _post_json(
                client,
                f"/api/admin/users/hard-delete?uid={_TARGET_UID}",
                {"confirm": "erase", "reason": reason},
            )
            assert response.status_code == 400, repr(reason)

        service.hard_delete_user.assert_not_awaited()

    def test_non_json_body_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # text/plain so the malformed body reaches the route's own guard —
        # FastHTML pre-parses application/json bodies during param extraction,
        # where malformed JSON is handled by the app-wide 400 chokepoint
        # instead (install_malformed_json_guard, wired in bootstrap; pinned by
        # test_malformed_json_guard.py), never by handler code.
        client, service = _make_client(monkeypatch)

        token = mint_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)
        response = client.post(
            f"/api/admin/users/hard-delete?uid={_TARGET_UID}",
            content=b"not json",
            headers={CSRF_HEADER_NAME: token, "content-type": "text/plain"},
        )

        assert response.status_code == 400
        service.hard_delete_user.assert_not_awaited()

    def test_missing_csrf_token_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = client.post(
            f"/api/admin/users/hard-delete?uid={_TARGET_UID}",
            json={"confirm": "erase", "reason": "gdpr request"},
        )

        assert response.status_code == 403
        service.hard_delete_user.assert_not_awaited()

    def test_valid_request_erases_with_audit_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = _post_json(
            client,
            f"/api/admin/users/hard-delete?uid={_TARGET_UID}",
            {"confirm": "erase", "reason": "gdpr request"},
        )

        assert response.status_code == 200
        service.hard_delete_user.assert_awaited_once_with(
            target_user_uid=_TARGET_UID,
            admin_user_uid=_ADMIN_UID,
            reason="gdpr request",
        )
        body = response.json()
        assert body["deleted_count"] == 42


class TestChangeRole:
    def test_invalid_role_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = _post_json(
            client,
            f"/api/admin/users/role?uid={_TARGET_UID}",
            {"role": "superuser"},
        )

        assert response.status_code == 400
        service.update_role.assert_not_awaited()

    def test_valid_role_change_passes_enum_and_audit_uid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch)

        response = _post_json(
            client,
            f"/api/admin/users/role?uid={_TARGET_UID}",
            {"role": "teacher"},
        )

        assert response.status_code == 200
        service.update_role.assert_awaited_once_with(
            target_user_uid=_TARGET_UID,
            new_role=UserRole.TEACHER,
            admin_user_uid=_ADMIN_UID,
        )


class TestAdminResetToken:
    def test_missing_graph_auth_is_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, _service = _make_client(monkeypatch, graph_auth=None)

        response = client.get(f"/api/admin/users/reset-password?uid={_TARGET_UID}")

        assert response.status_code == 500

    def test_token_generated_with_audit_trail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        graph_auth = MagicMock()
        graph_auth.admin_generate_reset_token = AsyncMock(return_value=Result.ok("tok_secret"))
        client, _service = _make_client(monkeypatch, graph_auth=graph_auth)

        response = client.get(f"/api/admin/users/reset-password?uid={_TARGET_UID}")

        assert response.status_code == 200
        assert response.json()["reset_token"] == "tok_secret"
        kwargs = graph_auth.admin_generate_reset_token.await_args.kwargs
        assert kwargs["user_uid"] == _TARGET_UID
        assert kwargs["admin_uid"] == _ADMIN_UID


class TestAccountActionsFromTheDetailPage:
    """The doors the admin user detail page posts to, driven the way it posts."""

    def test_role_form_swaps_the_account_card_and_the_header_badges(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch)

        response = _post_form(
            client, f"/api/admin/users/role?uid={_TARGET_UID}", {"role": "teacher"}
        )

        assert response.status_code == 200, response.text
        assert "text/html" in response.headers["content-type"]
        assert f'id="{account_card_id(_TARGET_UID)}"' in response.text
        assert f'id="{user_status_badges_id(_TARGET_UID)}"' in response.text
        assert 'hx-swap-oob="true"' in response.text
        assert "<html" not in response.text  # a fragment, not a page
        assert response.headers["X-Toast-Type"] == "success"
        service.update_role.assert_awaited_once_with(
            target_user_uid=_TARGET_UID, new_role=UserRole.TEACHER, admin_user_uid=_ADMIN_UID
        )

    def test_the_swapped_card_describes_the_stored_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After a deactivation the card's button flips to Activate — from the result,
        not from what was posted."""
        client, service = _make_client(monkeypatch)

        response = _post_form(client, f"/api/admin/users/deactivate?uid={_TARGET_UID}")

        assert response.status_code == 200, response.text
        assert "Activate account" in response.text
        assert "Deactivate account" not in response.text
        service.deactivate_user.assert_awaited_once_with(
            target_user_uid=_TARGET_UID, admin_user_uid=_ADMIN_UID, reason=""
        )

    def test_activate_button_reaches_the_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = _post_form(client, f"/api/admin/users/activate?uid={_TARGET_UID}")

        assert response.status_code == 200, response.text
        assert "Deactivate account" in response.text
        service.activate_user.assert_awaited_once_with(
            target_user_uid=_TARGET_UID, admin_user_uid=_ADMIN_UID
        )

    def test_activate_is_csrf_protected_like_its_siblings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch)

        response = client.post(f"/api/admin/users/activate?uid={_TARGET_UID}")

        assert response.status_code == 403
        service.activate_user.assert_not_awaited()

    def test_unknown_uid_renders_the_refusal_at_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)
        service.update_role = AsyncMock(
            return_value=Result.fail(Errors.not_found("User", "user_ghost"))
        )

        response = _post_form(client, "/api/admin/users/role?uid=user_ghost", {"role": "member"})

        assert response.status_code == 404
        assert response.headers[REFUSAL_HEADER] == REFUSAL_RENDERED
        assert "User not found" in response.text

    def test_a_write_failure_stays_a_json_error_the_toast_surfaces(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not a not-found: the card is left in place to retry, the error rides the
        toast headers of the JSON envelope."""
        client, service = _make_client(monkeypatch)
        service.deactivate_user = AsyncMock(
            return_value=Result.fail(Errors.database("deactivate", "write failed"))
        )

        response = _post_form(client, f"/api/admin/users/deactivate?uid={_TARGET_UID}")

        assert response.status_code >= 500
        assert REFUSAL_HEADER not in response.headers
        assert response.headers["X-Toast-Type"] == "error"
        assert response.json()["category"] == "database"

    def test_a_json_client_may_omit_the_optional_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zero bytes under a JSON content type is the empty field set, not malformed JSON."""
        client, service = _make_client(monkeypatch)
        token = mint_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)

        response = client.post(
            f"/api/admin/users/deactivate?uid={_TARGET_UID}",
            content=b"",
            headers={CSRF_HEADER_NAME: token, "Content-Type": "application/json"},
        )

        assert response.status_code == 200, response.text
        service.deactivate_user.assert_awaited_once_with(
            target_user_uid=_TARGET_UID, admin_user_uid=_ADMIN_UID, reason=""
        )

    def test_json_clients_still_read_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, _service = _make_client(monkeypatch)

        response = _post_json(
            client, f"/api/admin/users/deactivate?uid={_TARGET_UID}", {"reason": "spam"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["uid"] == _TARGET_UID and body["is_active"] is False
        _service.deactivate_user.assert_awaited_once_with(
            target_user_uid=_TARGET_UID, admin_user_uid=_ADMIN_UID, reason="spam"
        )
