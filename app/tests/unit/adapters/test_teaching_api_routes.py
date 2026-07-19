"""Teaching API security/wiring pins (adapters/inbound/teaching_api.py).

Testing-gap roadmap item 6 (tranche 2, learning-loop cluster): PIN tests over
the ADR-040 teacher review workflow — the TEACHER role gate on every route
(401/403), CSRF enforcement on mutations, teacher-scoped service kwargs, and
the tranche-1 harness gotcha this module shares with the field-update
factories: several mutating routes return error BANNERS with HTTP 200 (the
FT-fragment convention), so the pin is "service never awaited", not the
status code. Harness mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.teaching_api import create_teaching_api_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Result

_TEACHER_UID = "user_teacher"
_SUBMISSION_UID = "entry_1"


def _fake_auth(request: object) -> str:
    return _TEACHER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = _TEACHER_UID
    user.role = role
    # Role decorators check user.has_permission(required) on the entity —
    # bind the real hierarchy-aware enum method.
    user.has_permission = role.has_permission
    return user


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    review: MagicMock
    entries: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.TEACHER,
    user_entry_service: MagicMock | None = None,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    review_service = MagicMock()
    review_service.get_review_queue = AsyncMock(return_value=Result.ok([]))
    review_service.submit_report = AsyncMock(return_value=Result.ok(True))
    review_service.request_revision = AsyncMock(return_value=Result.ok(True))
    review_service.request_revision_with_exercise = AsyncMock(
        return_value=Result.ok({"revised_exercise_uid": "revised_exercise_1"})
    )
    review_service.approve_report = AsyncMock(return_value=Result.ok(True))
    review_service.get_exercises_with_submission_counts = AsyncMock(return_value=Result.ok([]))
    review_service.get_students_summary = AsyncMock(return_value=Result.ok([]))

    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))

    entries = user_entry_service if user_entry_service is not None else MagicMock()
    if user_entry_service is None:
        entries.delete_entry_as_teacher = AsyncMock(return_value=Result.ok(True))

    # Keep teacher feedback files out of the real data/reports tree.
    monkeypatch.setattr(
        "adapters.inbound.teaching_api._save_report_file",
        lambda teacher_uid, submission_uid, content: "/tmp/feedback.md",  # noqa: ARG005
    )

    if authenticated:
        monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    create_teaching_api_routes(
        app,
        rt,
        review_service,
        user_service,
        exercises_service=MagicMock(),
        user_entry_service=entries,
    )
    return _Harness(client=TestClient(app), review=review_service, entries=entries)


def _csrf(client: TestClient) -> dict[str, str]:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


class TestTeacherRoleGate:
    def test_review_queue_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/teaching/review-queue")

        assert response.status_code == 401
        harness.review.get_review_queue.assert_not_awaited()

    def test_review_queue_as_member_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = harness.client.get("/api/teaching/review-queue")

        assert response.status_code == 403
        harness.review.get_review_queue.assert_not_awaited()

    def test_member_cannot_approve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, role=UserRole.MEMBER)

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/approve",
            headers=_csrf(harness.client),
        )

        assert response.status_code == 403
        harness.review.approve_report.assert_not_awaited()


class TestCsrfEnforcement:
    def test_approve_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(f"/api/teaching/review/{_SUBMISSION_UID}/approve")

        assert response.status_code == 403
        harness.review.approve_report.assert_not_awaited()


class TestReviewQueue:
    def test_scopes_to_requesting_teacher(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/teaching/review-queue?status=pending")

        assert response.status_code == 200
        harness.review.get_review_queue.assert_awaited_once_with(
            teacher_uid=_TEACHER_UID, status_filter="pending"
        )


class TestApprove:
    def test_approve_awaited_with_exact_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/approve",
            headers=_csrf(harness.client),
        )

        assert response.status_code == 200
        assert "approved" in response.text
        harness.review.approve_report.assert_awaited_once_with(
            report_uid=_SUBMISSION_UID, teacher_uid=_TEACHER_UID
        )


class TestSubmitFeedback:
    def test_missing_file_banners_without_touching_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # HTTP 200 error banner (FT fragment) — pin service-not-awaited, not status.
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/report",
            headers=_csrf(harness.client),
            data={},
        )

        assert response.status_code == 200
        assert "No file uploaded" in response.text
        harness.review.submit_report.assert_not_awaited()

    def test_uploaded_file_submitted_with_exact_kwargs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/report",
            headers=_csrf(harness.client),
            files={"feedback_file": ("feedback.md", b"Good work.", "text/markdown")},
        )

        assert response.status_code == 200
        assert "submitted successfully" in response.text
        harness.review.submit_report.assert_awaited_once_with(
            report_uid=_SUBMISSION_UID,
            teacher_uid=_TEACHER_UID,
            feedback="Good work.",
            file_path="/tmp/feedback.md",
        )


class TestRequestRevision:
    def test_report_only_fallback_without_exercise_uid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/revision",
            headers=_csrf(harness.client),
            data={"instructions": "Cite your sources."},
        )

        assert response.status_code == 200
        assert "Revision requested" in response.text
        harness.review.request_revision.assert_awaited_once_with(
            report_uid=_SUBMISSION_UID,
            teacher_uid=_TEACHER_UID,
            notes="Cite your sources.",
        )
        harness.review.request_revision_with_exercise.assert_not_awaited()


def _make_harness_without_entry_service(
    monkeypatch: pytest.MonkeyPatch,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    review_service = MagicMock()
    user_service = MagicMock()
    user_service.get_user = AsyncMock(return_value=Result.ok(_caller(UserRole.TEACHER)))
    monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)
    create_teaching_api_routes(
        app,
        rt,
        review_service,
        user_service,
        exercises_service=MagicMock(),
        user_entry_service=None,
    )
    return _Harness(client=TestClient(app), review=review_service, entries=MagicMock())


class TestDeleteSubmissionUnwired:
    def test_unwired_entry_service_banners_gracefully(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # HTTP 200 error banner — the deletion seam is optional wiring.
        harness = _make_harness_without_entry_service(monkeypatch)

        response = harness.client.post(
            f"/api/teaching/submissions/{_SUBMISSION_UID}/delete",
            headers=_csrf(harness.client),
        )

        assert response.status_code == 200
        assert "not available" in response.text


class TestDeleteSubmissionWired:
    def test_delete_awaited_with_exact_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            f"/api/teaching/submissions/{_SUBMISSION_UID}/delete",
            headers=_csrf(harness.client),
        )

        assert response.status_code == 200
        harness.entries.delete_entry_as_teacher.assert_awaited_once_with(
            _SUBMISSION_UID, _TEACHER_UID
        )
