"""Groups API security/wiring pins (adapters/inbound/groups_api.py).

Testing-gap roadmap item 6 (tranche 2, system/infra cluster): PIN tests over
the ADR-040 membership routes — auth gate (401), the TEACHER role gate on
add/remove, owner-only enforcement via verify_entity_ownership (non-owner
teacher → 404, service untouched — no group-UID enumeration), CSRF, and exact
service kwargs. Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.groups_api import create_groups_api_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_teacher"
_GROUP_UID = "group_1"
_STUDENT_UID = "user_student"


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
    groups: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.TEACHER,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    groups = MagicMock()
    groups.get_user_groups = AsyncMock(return_value=Result.ok([]))
    groups.verify_ownership = AsyncMock(return_value=Result.ok(True))
    groups.add_member = AsyncMock(return_value=Result.ok(True))
    groups.remove_member = AsyncMock(return_value=Result.ok(True))
    groups.get_members = AsyncMock(return_value=Result.ok([]))
    # Owner-OR-member read gate on the roster; default harness caller passes.
    groups.get_for_user = AsyncMock(return_value=Result.ok(True))

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr("adapters.inbound.groups_api.require_authenticated_user", _fake_auth)
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_groups_api_routes(app, rt, groups, user_service)
    return _Harness(client=TestClient(app), groups=groups)


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


_MEMBER_BODY = {"user_uid": _STUDENT_UID, "role": "member"}


class TestAuthGate:
    def test_my_groups_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/groups/mine")

        assert response.status_code == 401
        harness.groups.get_user_groups.assert_not_awaited()


class TestTeacherRoleGate:
    def test_add_member_as_member_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = _post_json(harness.client, f"/api/groups/{_GROUP_UID}/members/add", _MEMBER_BODY)

        assert response.status_code == 403
        harness.groups.add_member.assert_not_awaited()


class TestCsrfEnforcement:
    def test_add_member_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(f"/api/groups/{_GROUP_UID}/members/add", json=_MEMBER_BODY)

        assert response.status_code == 403
        harness.groups.add_member.assert_not_awaited()


class TestOwnerOnlyMembership:
    def test_non_owner_teacher_gets_404_without_touching_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Ownership failure surfaces as not-found (never 403) so group UIDs
        # can't be enumerated by other teachers.
        harness = _make_harness(monkeypatch)
        harness.groups.verify_ownership.return_value = Result.fail(
            Errors.not_found("group", _GROUP_UID)
        )

        response = _post_json(harness.client, f"/api/groups/{_GROUP_UID}/members/add", _MEMBER_BODY)

        assert response.status_code == 404
        harness.groups.add_member.assert_not_awaited()

    def test_add_member_awaited_with_exact_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, f"/api/groups/{_GROUP_UID}/members/add", _MEMBER_BODY)

        assert response.status_code == 200
        harness.groups.verify_ownership.assert_awaited_once_with(_GROUP_UID, _USER_UID)
        harness.groups.add_member.assert_awaited_once_with(
            group_uid=_GROUP_UID, user_uid=_STUDENT_UID, role="member"
        )

    def test_remove_member_awaited_with_exact_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client, f"/api/groups/{_GROUP_UID}/members/remove", _MEMBER_BODY
        )

        assert response.status_code == 200
        harness.groups.remove_member.assert_awaited_once_with(
            group_uid=_GROUP_UID, user_uid=_STUDENT_UID
        )


class TestReads:
    def test_my_groups_scopes_to_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = harness.client.get("/api/groups/mine")

        assert response.status_code == 200
        harness.groups.get_user_groups.assert_awaited_once_with(_USER_UID)

    def test_list_members_requires_owner_or_member(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The roster is owner-OR-member, not auth-only.

        This test previously pinned ``requires_auth_only`` — the vulnerable
        contract, where any authenticated user could enumerate any group's
        membership. The gate is now asserted, not just the read.
        """
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = harness.client.get(f"/api/groups/{_GROUP_UID}/members")

        assert response.status_code == 200
        harness.groups.get_for_user.assert_awaited_once_with(_GROUP_UID, _USER_UID)
        harness.groups.get_members.assert_awaited_once_with(_GROUP_UID)

    def test_list_members_non_member_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A caller who is neither owner nor member gets the not-found a
        nonexistent group returns — and the roster is never read."""
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)
        harness.groups.get_for_user = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Group", identifier=_GROUP_UID))
        )

        response = harness.client.get(f"/api/groups/{_GROUP_UID}/members")

        assert response.status_code == 404
        harness.groups.get_members.assert_not_awaited()
