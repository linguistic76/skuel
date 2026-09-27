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
from adapters.inbound.teaching_api import _save_report_file as _real_save_report_file
from adapters.inbound.teaching_api import create_teaching_api_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Errors, Result

_TEACHER_UID = "user_teacher"
_SUBMISSION_UID = "entry_1"


def _fake_auth(request: object) -> str:
    return _TEACHER_UID


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
    # The gated detail read the revision and panel doors make first; by default
    # a submission with no exercise (the report-only path).
    review_service.get_submission_detail = AsyncMock(
        return_value=Result.ok({"uid": _SUBMISSION_UID, "status": "submitted"})
    )
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

    def test_service_rejection_removes_saved_feedback_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """The file is written before the service validates status — a refusal
        (e.g. entry no longer reviewable) must not leave an orphan on disk."""
        harness = _make_harness(monkeypatch)

        saved = tmp_path / "feedback.md"

        def _write_report_file(teacher_uid: str, submission_uid: str, content: str) -> str:
            saved.write_text(content, encoding="utf-8")
            return str(saved)

        monkeypatch.setattr("adapters.inbound.teaching_api._save_report_file", _write_report_file)
        harness.review.submit_report.return_value = Result.fail(
            Errors.validation("not in a reviewable status", field="status")
        )

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/report",
            headers=_csrf(harness.client),
            files={"feedback_file": ("feedback.md", b"Good work.", "text/markdown")},
        )

        assert response.status_code == 200
        assert "not in a reviewable status" in response.text
        assert not saved.exists(), "rejected submit must clean up the report file it wrote"

    def test_rejected_retry_never_touches_previously_persisted_feedback(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Feedback filenames are unique per submit: a retried submit against a
        completed submission writes (then cleans up) its OWN file — never
        overwriting or deleting the file an earlier persisted EntryReport
        references, whose Download link must keep working."""
        harness = _make_harness(monkeypatch)
        # This test exercises the real writer against a temp reports tree.
        monkeypatch.setattr(
            "adapters.inbound.teaching_api._save_report_file", _real_save_report_file
        )
        monkeypatch.setattr("adapters.inbound.teaching_api._REPORTS_DIR", tmp_path)
        report_dir = tmp_path / _TEACHER_UID / _SUBMISSION_UID

        first = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/report",
            headers=_csrf(harness.client),
            files={"feedback_file": ("feedback.md", b"Round one.", "text/markdown")},
        )
        assert "submitted successfully" in first.text
        persisted = list(report_dir.glob("*.md"))
        assert len(persisted) == 1

        harness.review.submit_report.return_value = Result.fail(
            Errors.validation("not in a reviewable status", field="status")
        )
        retry = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/report",
            headers=_csrf(harness.client),
            files={"feedback_file": ("feedback.md", b"Round two.", "text/markdown")},
        )
        assert "not in a reviewable status" in retry.text

        assert list(report_dir.glob("*.md")) == persisted, (
            "the rejected retry must clean up only its own uniquely-named file"
        )
        assert persisted[0].read_text(encoding="utf-8") == "Round one.", (
            "the persisted report's file content must survive the retry untouched"
        )


def _multipart(fields: dict[str, str]) -> dict[str, tuple[None, str]]:
    """A FastHTML ``Form`` posts multipart by default — drive the door that way."""
    return {name: (None, value) for name, value in fields.items()}


class TestRequestRevision:
    def test_report_only_when_the_detail_has_no_exercise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/revision",
            headers=_csrf(harness.client),
            files=_multipart({"instructions": "Cite your sources."}),
        )

        assert response.status_code == 200
        assert "Revision requested" in response.text
        harness.review.get_submission_detail.assert_awaited_once_with(
            submission_uid=_SUBMISSION_UID, teacher_uid=_TEACHER_UID
        )
        harness.review.request_revision.assert_awaited_once_with(
            report_uid=_SUBMISSION_UID,
            teacher_uid=_TEACHER_UID,
            notes="Cite your sources.",
        )
        harness.review.request_revision_with_exercise.assert_not_awaited()

    def test_the_exercise_comes_from_the_detail_never_the_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A forged ``exercise_uid`` in the post is ignored: the RevisedExercise
        revises the exercise the submission turned in, read under the gate."""
        harness = _make_harness(monkeypatch)
        harness.review.get_submission_detail = AsyncMock(
            return_value=Result.ok(
                {"uid": _SUBMISSION_UID, "status": "submitted", "exercise_uid": "ex.root"}
            )
        )

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/revision",
            headers=_csrf(harness.client),
            files=_multipart(
                {
                    "instructions": "Tighten the argument.",
                    "exercise_uid": "ex.other",
                    "fp_count": "1",
                    "fp_category_0": "accuracy",
                    "fp_detail_0": "The date is wrong.",
                    "revision_rationale": "One fix away.",
                }
            ),
        )

        assert response.status_code == 200
        assert "/revised-exercises/detail?uid=revised_exercise_1" in response.text
        harness.review.request_revision_with_exercise.assert_awaited_once_with(
            submission_uid=_SUBMISSION_UID,
            teacher_uid=_TEACHER_UID,
            notes="Tighten the argument.",
            original_exercise_uid="ex.root",
            feedback_points=[{"category": "accuracy", "detail": "The date is wrong."}],
            revision_rationale="One fix away.",
        )
        harness.review.request_revision.assert_not_awaited()

    def test_a_denied_detail_touches_neither_writer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.review.get_submission_detail = AsyncMock(
            return_value=Result.fail(Errors.not_found("Submission entry_1 not found"))
        )

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/revision",
            headers=_csrf(harness.client),
            files=_multipart({"instructions": "Anything."}),
        )

        assert response.status_code == 200
        assert "Submission not found." in response.text
        harness.review.request_revision.assert_not_awaited()
        harness.review.request_revision_with_exercise.assert_not_awaited()

    def test_a_backend_fault_is_not_reported_as_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)
        harness.review.get_submission_detail = AsyncMock(
            return_value=Result.fail(
                Errors.database(
                    operation="get_entry_detail_for_teacher", message="Neo4j unavailable"
                )
            )
        )

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/revision",
            headers=_csrf(harness.client),
            files=_multipart({"instructions": "Anything."}),
        )

        assert response.status_code == 200
        assert "not found" not in response.text.lower()
        harness.review.request_revision.assert_not_awaited()
        harness.review.request_revision_with_exercise.assert_not_awaited()

    def test_missing_instructions_is_refused_before_any_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A body without ``instructions`` (``notes`` is no alias) is refused at
        parse, before the gated detail read — the rendered form's names are
        pinned in ``tests/unit/ui/test_teacher_review_actions.py``."""
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            f"/api/teaching/review/{_SUBMISSION_UID}/revision",
            headers=_csrf(harness.client),
            files=_multipart({"notes": "Posted under the wrong name."}),
        )

        assert response.status_code == 200
        assert "instructions" in response.text and "Field required" in response.text
        harness.review.get_submission_detail.assert_not_awaited()
        harness.review.request_revision.assert_not_awaited()


class TestReviewPanel:
    """``/api/teaching/review/{uid}/panel`` renders the review page's own body."""

    def _panel(self, monkeypatch: pytest.MonkeyPatch, detail: dict[str, object]) -> str:
        harness = _make_harness(monkeypatch)
        harness.review.get_submission_detail = AsyncMock(return_value=Result.ok(detail))
        response = harness.client.get(f"/api/teaching/review/{_SUBMISSION_UID}/panel")
        assert response.status_code == 200
        return response.text

    def test_a_reviewable_turn_in_shows_the_work_and_the_forms(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = self._panel(
            monkeypatch,
            {
                "uid": _SUBMISSION_UID,
                "title": "Essay",
                "status": "submitted",
                "content": "The student's own paragraph.",
                "exercise_uid": "ex.root",
                "exercise_title": "The Gentle Return",
                "revision": 2,
            },
        )
        assert "The student's own paragraph." in body
        assert "The Gentle Return · v2" in body
        assert 'name="instructions"' in body
        assert 'name="fp_count"' in body
        assert f"/api/teaching/review/{_SUBMISSION_UID}/approve" not in body

    def test_a_revision_requested_row_offers_approve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = self._panel(
            monkeypatch,
            {"uid": _SUBMISSION_UID, "status": "revision_requested", "content": "x"},
        )
        assert f"/api/teaching/review/{_SUBMISSION_UID}/approve" in body
        assert 'name="instructions"' not in body

    def test_a_superseded_copy_offers_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = self._panel(
            monkeypatch,
            {
                "uid": _SUBMISSION_UID,
                "status": "revision_requested",
                "content": "x",
                "superseded": True,
            },
        )
        assert "this copy is history" in body
        assert "hx-post" not in body


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
