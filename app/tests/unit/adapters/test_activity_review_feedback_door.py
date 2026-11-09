"""The admin review form's doors (adapters/inbound/activity_review_ui.py).

``POST /activity-review/submit-feedback`` reads ``ActivityFeedbackSubmitRequest``
through ``parse_body`` and passes the snapshot and the learner's request on to the
orchestrator. Each refusal renders into the form's status slot at the status it
earns, with the ``X-SKUEL-Refusal`` header that lets HTMX swap it; a non-admin is
refused by the role gate. ``GET /activity-review/snapshot-fragment`` renders each
domain from the snapshot's ``domains`` section and carries the snapshot as the
hidden field the feedback form posts.
"""

from __future__ import annotations

import json
from html import unescape
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlencode

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

import adapters.inbound.activity_review_ui as activity_review_ui
from adapters.inbound import boundary
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from core.models.enums import UserRole
from core.orchestrator.activity_review_orchestrator import SubmittedReview
from core.utils.result_simplified import Errors, Result
from tests.helpers.settings_stub import settings_stub

ADMIN_UID = "user_admin"
FEEDBACK = "/activity-review/submit-feedback"
SNAPSHOT_DOOR = "/activity-review/snapshot-fragment"
SNAPSHOT = {
    "subject_uid": "user_learner",
    "time_period": "7d",
    "domains": {
        "tasks": {
            "count": 12,
            "completed": 3,
            "items": [{"title": 'Write Mike\'s "big" essay', "status": "completed"}],
        },
        "habits": {"count": 0, "items": []},
    },
}


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = ADMIN_UID
    user.role = role
    user.has_permission = role.has_permission
    return user


def _client(
    monkeypatch: pytest.MonkeyPatch, orchestrator: MagicMock, role: UserRole = UserRole.ADMIN
) -> TestClient:
    def signed_in(_request: object) -> str:
        return ADMIN_UID

    monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", signed_in)
    monkeypatch.setattr(activity_review_ui, "get_settings", settings_stub(debug=False))
    monkeypatch.setattr(boundary, "get_settings", settings_stub(debug=False))
    orchestrator.user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))
    app, rt = fast_app(pico=False, default_hdrs=False)
    activity_review_ui.create_activity_review_ui_routes(rt, orchestrator)
    client = TestClient(app)
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    client.headers.update({CSRF_HEADER_NAME: token, "HX-Request": "true"})
    return client


def _report() -> MagicMock:
    report = MagicMock()
    report.uid = "ar_0123456789abcdef"
    return report


def _orchestrator(submitted: Result[SubmittedReview] | None = None) -> MagicMock:
    orchestrator = MagicMock()
    orchestrator.submit_report = AsyncMock(
        return_value=submitted or Result.ok(SubmittedReview(_report()))
    )
    return orchestrator


FORM = {
    "subject_uid": "user_learner",
    "feedback_text": "A steady week.",
    "time_period": "7d",
}


class TestFeedbackDoor:
    def test_the_snapshot_domains_and_request_reach_the_orchestrator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        orchestrator = _orchestrator(Result.ok(SubmittedReview(_report(), request_closed=True)))
        body = [
            *FORM.items(),
            ("domains", "tasks"),
            ("domains", "habits"),
            ("snapshot_context", json.dumps(SNAPSHOT)),
            ("review_request_uid", "rr_0123456789abcdef"),
        ]

        response = _client(monkeypatch, orchestrator).post(
            FEEDBACK,
            content=urlencode(body),
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200
        assert "Report sent to user_learner" in response.text
        assert "answered and leaves the queue" in response.text
        orchestrator.submit_report.assert_awaited_once_with(
            admin_uid=ADMIN_UID,
            subject_uid="user_learner",
            feedback_text="A steady week.",
            time_period="7d",
            domains=["tasks", "habits"],
            snapshot_context=SNAPSHOT,
            review_request_uid="rr_0123456789abcdef",
        )

    def test_a_review_with_no_request_says_nothing_of_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        response = _client(monkeypatch, _orchestrator()).post(FEEDBACK, data=FORM)

        assert response.status_code == 200
        assert "review request" not in response.text

    def test_a_request_that_could_not_be_closed_is_said_plainly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        orchestrator = _orchestrator(Result.ok(SubmittedReview(_report(), request_closed=False)))

        response = _client(monkeypatch, orchestrator).post(
            FEEDBACK, data={**FORM, "review_request_uid": "rr_0123456789abcdef"}
        )

        assert response.status_code == 200
        assert "could not be closed; it is still in the queue" in response.text

    @pytest.mark.parametrize(
        "body",
        [
            {**FORM, "feedback_text": ""},
            {**FORM, "subject_uid": ""},
            {**FORM, "time_period": "45d"},
            {**FORM, "domains": "knowledge"},
            {**FORM, "snapshot_context": "{not json"},
            {**FORM, "snapshot_context": "[1, 2]"},
        ],
        ids=[
            "no feedback",
            "no subject",
            "period outside the vocabulary",
            "domain outside the six",
            "snapshot not JSON",
            "snapshot not an object",
        ],
    )
    def test_a_body_the_model_refuses_is_a_rendered_400(
        self, monkeypatch: pytest.MonkeyPatch, body: dict[str, str]
    ) -> None:
        orchestrator = _orchestrator()

        response = _client(monkeypatch, orchestrator).post(FEEDBACK, data=body)

        assert response.status_code == 400
        assert response.headers["X-SKUEL-Refusal"] == "rendered"
        assert "Load a user's snapshot and write feedback" in response.text
        orchestrator.submit_report.assert_not_awaited()

    def test_a_refusal_from_the_orchestrator_renders_its_reason_at_400(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        refused: Result[SubmittedReview] = Result.fail(
            Errors.validation(
                message="That review request is no longer pending for this user",
                field="review_request_uid",
            )
        )

        response = _client(monkeypatch, _orchestrator(refused)).post(FEEDBACK, data=FORM)

        assert response.status_code == 400
        assert response.headers["X-SKUEL-Refusal"] == "rendered"
        assert "no longer pending" in response.text

    def test_a_failed_write_answers_its_own_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        failed: Result[SubmittedReview] = Result.fail(
            Errors.database("submit_report", "connection lost")
        )

        response = _client(monkeypatch, _orchestrator(failed)).post(FEEDBACK, data=FORM)

        assert response.status_code == 503
        assert response.headers["X-SKUEL-Refusal"] == "rendered"

    def test_a_non_admin_is_refused_and_nothing_is_written(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        orchestrator = _orchestrator()

        response = _client(monkeypatch, orchestrator, role=UserRole.TEACHER).post(
            FEEDBACK, data=FORM
        )

        assert response.status_code == 403
        orchestrator.submit_report.assert_not_awaited()


def _hidden_value(page: str, name: str) -> str:
    """The ``value`` of the input named ``name``, as an HTML parser reads it."""
    values: list[str] = []

    class _Inputs(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            fields = dict(attrs)
            if tag == "input" and fields.get("name") == name:
                values.append(fields.get("value") or "")

    _Inputs().feed(page)
    assert len(values) == 1, f"{len(values)} inputs named {name}"
    return values[0]


class TestSnapshotFragment:
    def _fragment(self, monkeypatch: pytest.MonkeyPatch, query: str) -> tuple[MagicMock, str]:
        orchestrator = MagicMock()
        orchestrator.build_rich_context = AsyncMock(return_value=Result.ok(MagicMock()))
        orchestrator.create_snapshot = AsyncMock(return_value=Result.ok(SNAPSHOT))
        response = _client(monkeypatch, orchestrator).get(f"{SNAPSHOT_DOOR}?{query}")
        assert response.status_code == 200
        return orchestrator, response.text

    def test_each_domain_renders_from_its_section_with_the_periods_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, page = self._fragment(
            monkeypatch, "subject_uid=user_learner&time_period=7d&domains=tasks&domains=habits"
        )

        assert "Tasks (12)" in page
        assert 'Write Mike\'s "big" essay' in unescape(page)
        assert "No recent activity." in page  # habits, empty this period

    def test_the_snapshot_rides_as_the_hidden_field_the_feedback_form_posts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, page = self._fragment(monkeypatch, "subject_uid=user_learner&time_period=7d")

        # Read the attribute as a browser does: a title's quotes must survive the trip.
        assert json.loads(_hidden_value(page, "snapshot_context")) == SNAPSHOT

    def test_the_access_audit_names_the_admin_who_looked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        orchestrator, _ = self._fragment(monkeypatch, "subject_uid=user_learner&time_period=7d")

        assert orchestrator.create_snapshot.await_args.kwargs["admin_uid"] == ADMIN_UID
