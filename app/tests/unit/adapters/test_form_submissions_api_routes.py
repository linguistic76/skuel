"""Form Submissions API security/wiring pins (adapters/inbound/form_submissions_api.py).

Testing-gap roadmap item 6 (tranche 2, content/entry cluster): PIN tests over
the user-facing form-response routes — auth gate (401), CSRF enforcement on
mutations (403), input guards refusing before the service (400), and exact
service kwargs on submit/share happy paths (201 on submit). Harness mirrors
``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.form_submissions_api import create_form_submissions_api_routes
from core.models.forms.form_submission import FormSubmission
from core.utils.result_simplified import Result

_USER_UID = "user_owner"
_TEMPLATE_UID = "form_template_1"
_SUBMISSION_UID = "form_submission_1"


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    submissions: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    submission = FormSubmission(uid=_SUBMISSION_UID, title="Response", user_uid=_USER_UID)

    service = MagicMock()
    service.submit_form = AsyncMock(return_value=Result.ok(submission))
    service.get_my_submissions = AsyncMock(return_value=Result.ok([]))
    service.get_submission = AsyncMock(return_value=Result.ok(submission))
    service.delete_submission = AsyncMock(return_value=Result.ok(True))
    service.share_submission = AsyncMock(return_value=Result.ok(True))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.form_submissions_api.require_authenticated_user", _fake_auth
        )

    create_form_submissions_api_routes(app, rt, service)
    return _Harness(client=TestClient(app), submissions=service)


def _csrf(client: TestClient) -> dict[str, str]:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


_SUBMIT_BODY = {
    "form_template_uid": _TEMPLATE_UID,
    "form_data": {"q1": "answer"},
    "title": "Weekly check-in",
}


class TestAuthGate:
    def test_submit_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.post(
            "/api/form-submissions/submit", json=_SUBMIT_BODY, headers=_csrf(harness.client)
        )

        assert response.status_code == 401
        harness.submissions.submit_form.assert_not_awaited()


class TestCsrfEnforcement:
    def test_submit_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post("/api/form-submissions/submit", json=_SUBMIT_BODY)

        assert response.status_code == 403
        harness.submissions.submit_form.assert_not_awaited()


class TestSubmit:
    def test_submit_created_with_exact_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/form-submissions/submit", json=_SUBMIT_BODY, headers=_csrf(harness.client)
        )

        assert response.status_code == 201
        assert response.json()["submission"]["uid"] == _SUBMISSION_UID
        harness.submissions.submit_form.assert_awaited_once_with(
            user_uid=_USER_UID,
            form_template_uid=_TEMPLATE_UID,
            form_data={"q1": "answer"},
            title="Weekly check-in",
            group_uid=None,
            recipient_uids=None,
            share_with_admin=False,
        )

    def test_submit_missing_template_uid_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/form-submissions/submit",
            json={"form_data": {"q1": "a"}},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 400
        harness.submissions.submit_form.assert_not_awaited()


class TestInputGuards:
    def test_get_missing_uid_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/form-submissions/get")

        assert response.status_code == 400
        harness.submissions.get_submission.assert_not_awaited()

    def test_delete_missing_uid_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.delete(
            "/api/form-submissions/delete", headers=_csrf(harness.client)
        )

        assert response.status_code == 400
        harness.submissions.delete_submission.assert_not_awaited()


class TestOwnershipScoping:
    def test_get_forwards_owner_uid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(f"/api/form-submissions/get?uid={_SUBMISSION_UID}")

        assert response.status_code == 200
        harness.submissions.get_submission.assert_awaited_once_with(_SUBMISSION_UID, _USER_UID)

    def test_list_scopes_to_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/form-submissions")

        assert response.status_code == 200
        harness.submissions.get_my_submissions.assert_awaited_once_with(_USER_UID, limit=50)


class TestShare:
    def test_share_awaited_with_exact_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/form-submissions/share",
            json={"uid": _SUBMISSION_UID, "group_uid": "group_1", "share_with_admin": True},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 200
        harness.submissions.share_submission.assert_awaited_once_with(
            uid=_SUBMISSION_UID,
            user_uid=_USER_UID,
            group_uid="group_1",
            recipient_uids=None,
            share_with_admin=True,
        )

    def test_share_missing_uid_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/form-submissions/share",
            json={"group_uid": "group_1"},
            headers=_csrf(harness.client),
        )

        assert response.status_code == 400
        harness.submissions.share_submission.assert_not_awaited()
