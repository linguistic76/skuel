"""Revised Exercises API security/wiring pins (adapters/inbound/revised_exercises_api.py).

Testing-gap roadmap item 6 (tranche 2, learning-loop cluster): PIN tests over
the four-phase learning-loop revision routes — teacher-role gate on the
teacher-scoped listings (401/403), the student-facing auth gate, the
view-route ownership rule (student_uid OR user_uid, 404 otherwise so UIDs
don't leak), input guards refusing before the service, and exact service args
on the happy paths. Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.revised_exercises_api import create_revised_exercises_api_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_STUDENT_UID = "user_student"
_RE_UID = "revised_exercise_1"


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


def _make_revised_exercise(*, student_uid: str, user_uid: str) -> MagicMock:
    entity = MagicMock()
    entity.student_uid = student_uid
    entity.user_uid = user_uid
    return entity


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    service: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.MEMBER,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    service = MagicMock()
    service.list_for_student = AsyncMock(return_value=Result.ok([]))
    service.get_revision_chain = AsyncMock(return_value=Result.ok([]))
    service.get = AsyncMock(
        return_value=Result.ok(
            _make_revised_exercise(student_uid=_STUDENT_UID, user_uid="user_teacher")
        )
    )

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.revised_exercises_api.require_authenticated_user", _fake_auth
        )
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_revised_exercises_api_routes(app, rt, service, user_service=user_service)
    return _Harness(client=TestClient(app), service=service)


class TestAuthGate:
    def test_my_revisions_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/revised-exercises/my-revisions")

        assert response.status_code == 401
        harness.service.list_for_student.assert_not_awaited()


class TestTeacherRoleGate:
    def test_for_student_as_member_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = harness.client.get(
            f"/api/revised-exercises/for-student?student_uid={_STUDENT_UID}"
        )

        assert response.status_code == 403
        harness.service.list_for_student.assert_not_awaited()

    def test_for_student_scopes_to_requesting_teacher(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = harness.client.get(
            f"/api/revised-exercises/for-student?student_uid={_STUDENT_UID}"
        )

        assert response.status_code == 200
        harness.service.list_for_student.assert_awaited_once_with(
            _STUDENT_UID, teacher_uid=_USER_UID
        )


class TestInputGuards:
    def test_for_student_missing_student_uid_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.TEACHER)

        response = harness.client.get("/api/revised-exercises/for-student")

        assert response.status_code == 400
        harness.service.list_for_student.assert_not_awaited()

    def test_view_missing_uid_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/revised-exercises/view")

        assert response.status_code == 400
        harness.service.get.assert_not_awaited()


class TestMyRevisions:
    def test_lists_for_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/revised-exercises/my-revisions")

        assert response.status_code == 200
        harness.service.list_for_student.assert_awaited_once_with(_USER_UID)


class TestViewOwnership:
    def test_unrelated_user_gets_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Caller is neither the targeted student nor the owning teacher.
        harness = _make_harness(monkeypatch)

        response = harness.client.get(f"/api/revised-exercises/view?uid={_RE_UID}")

        assert response.status_code == 404

    def test_missing_entity_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.service.get.return_value = Result.ok(None)

        response = harness.client.get(f"/api/revised-exercises/view?uid={_RE_UID}")

        assert response.status_code == 404
