"""Entry Report assessment API security/wiring pins (adapters/inbound/entry_report_api.py).

Testing-gap roadmap item 6 (tranche 2, content/entry cluster): PIN tests over
the teacher-assessment routes — TEACHER role gate on create (401/403), CSRF
enforcement, 201 on create with exact service kwargs, and the given/received
listings scoped to the current user. Note this factory takes a
``user_service_getter`` (named function), not the service itself. Harness
mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.entry_report_api import create_entry_report_api_routes
from core.models.enums import UserRole
from core.models.report.entry_report import EntryReport
from core.utils.result_simplified import Result

_USER_UID = "user_teacher"
_STUDENT_UID = "user_student"
_REPORT_UID = "entry_report_1"


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
    reports: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.TEACHER,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    report = EntryReport(uid=_REPORT_UID, title="Assessment", user_uid=_USER_UID)

    report_service = MagicMock()
    report_service.create_assessment = AsyncMock(return_value=Result.ok(report))
    report_service.get_assessments_by_teacher = AsyncMock(return_value=Result.ok([report]))
    report_service.get_assessments_for_student = AsyncMock(return_value=Result.ok([]))

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    def _get_user_service() -> MagicMock:
        return user_service

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.entry_report_api.require_authenticated_user", _fake_auth
        )
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_entry_report_api_routes(None, rt, report_service, _get_user_service)
    return _Harness(client=TestClient(app), reports=report_service)


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


_CREATE_BODY = {
    "subject_uid": _STUDENT_UID,
    "title": "Progress assessment",
    "content": "Solid grasp of the fundamentals.",
}


class TestTeacherRoleGate:
    def test_create_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = _post_json(harness.client, "/api/reports/assessments", _CREATE_BODY)

        assert response.status_code == 401
        harness.reports.create_assessment.assert_not_awaited()

    def test_create_as_member_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = _post_json(harness.client, "/api/reports/assessments", _CREATE_BODY)

        assert response.status_code == 403
        harness.reports.create_assessment.assert_not_awaited()


class TestCsrfEnforcement:
    def test_create_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/reports/assessments", json=_CREATE_BODY)

        assert response.status_code == 403
        harness.reports.create_assessment.assert_not_awaited()


class TestCreateAssessment:
    def test_created_with_exact_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, "/api/reports/assessments", _CREATE_BODY)

        assert response.status_code == 201
        payload = response.json()
        assert payload["report"]["uid"] == _REPORT_UID
        harness.reports.create_assessment.assert_awaited_once_with(
            teacher_uid=_USER_UID,
            subject_uid=_STUDENT_UID,
            title="Progress assessment",
            content="Solid grasp of the fundamentals.",
            metadata=None,
        )


class TestListings:
    def test_given_scopes_to_current_teacher(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/reports/assessments/given")

        assert response.status_code == 200
        assert response.json()["count"] == 1
        harness.reports.get_assessments_by_teacher.assert_awaited_once_with(
            teacher_uid=_USER_UID, limit=50
        )

    def test_received_scopes_to_current_student(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/reports/assessments/received")

        assert response.status_code == 200
        assert response.json()["count"] == 0
        harness.reports.get_assessments_for_student.assert_awaited_once_with(
            student_uid=_USER_UID, limit=50
        )
