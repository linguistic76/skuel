"""The review queue answers in its sidebar shell (adapters/inbound/activity_review_ui.py).

``/activity-review/queue`` is an admin sidebar page. Its queue, a failed read and a
crash all render inside ``activity_review_sidebar_page("queue", ...)``: one
``<main id="main-content">`` and the sidebar's Queue row lit. A failed read is a
banner, never the empty queue's "No pending review requests". The role gate stands in
front of the boundary, so a non-admin is still refused with 403.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

import adapters.inbound.activity_review_ui as activity_review_ui
from adapters.inbound import boundary
from core.models.enums import UserRole
from core.ports.query_types import PendingReviewItem
from core.utils.auth_context import AuthState, auth_state_var
from core.utils.result_simplified import Errors, Result
from tests.helpers.settings_stub import settings_stub

ADMIN_UID = "user_admin"
QUEUE = "/activity-review/queue"
EMPTY_QUEUE = "No pending review requests"
#: A ``PendingReviewItem``, keyed as ``ReviewQueueService.get_pending_reviews`` builds it.
PENDING = [
    {
        "uid": "review_0123456789abcdef",
        "user_uid": "user_learner",
        "time_period": "30d",
        "domains": ["tasks"],
        "message": "",
        "created_at": "2026-10-29T09:00:00Z",
        "username": "Learner",
    }
]


class _SignedInAdminChrome:
    """Sets the auth state the chrome reads, as ``AuthContextMiddleware`` does."""

    def __init__(self, app: object) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        token = auth_state_var.set(AuthState(user_uid=ADMIN_UID, is_admin=True))
        try:
            await self.app(scope, receive, send)  # type: ignore[operator]
        finally:
            auth_state_var.reset(token)


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = ADMIN_UID
    user.role = role
    user.has_permission = role.has_permission
    return user


def _client(
    monkeypatch: pytest.MonkeyPatch,
    orchestrator: MagicMock,
    role: UserRole = UserRole.ADMIN,
) -> TestClient:
    def signed_in(_request: object) -> str:
        return ADMIN_UID

    monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", signed_in)
    monkeypatch.setattr(activity_review_ui, "get_settings", settings_stub(debug=False))
    monkeypatch.setattr(boundary, "get_settings", settings_stub(debug=False))
    orchestrator.user_service.get_user = AsyncMock(return_value=Result.ok(_caller(role)))
    app, rt = fast_app(pico=False, default_hdrs=False)
    activity_review_ui.create_activity_review_ui_routes(app, rt, orchestrator)
    return TestClient(_SignedInAdminChrome(app))


def _orchestrator(pending: object) -> MagicMock:
    orchestrator = MagicMock()
    orchestrator.get_pending_reviews = (
        AsyncMock(side_effect=pending)
        if isinstance(pending, Exception)
        else AsyncMock(return_value=pending)
    )
    return orchestrator


def _assert_in_queue_shell(page: str) -> str:
    """The sidebar shell with its Queue row lit; answers what ``<main>`` holds."""
    assert page.count('id="main-content"') == 1, "the page is not the shell's"
    lit = re.findall(r'<a[^>]*aria-current="page"[^>]*>', page)
    hrefs = {re.search(r'href="([^"]*)"', tag).group(1) for tag in lit}  # type: ignore[union-attr]
    assert QUEUE in hrefs, f"the sidebar's Queue row is not lit: {hrefs}"
    return page[page.index('id="main-content"') :]


def test_the_queue_answers_in_its_sidebar_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = _orchestrator(Result.ok(PENDING))
    response = _client(monkeypatch, orchestrator).get(QUEUE)

    assert response.status_code == 200
    main = _assert_in_queue_shell(response.text)
    assert "Learner" in main
    orchestrator.get_pending_reviews.assert_awaited_once_with(ADMIN_UID)


def test_a_queued_request_opens_its_learners_review(monkeypatch: pytest.MonkeyPatch) -> None:
    """The card's door names the learner who asked, and the period they asked about."""
    page = _client(monkeypatch, _orchestrator(Result.ok(PENDING))).get(QUEUE).text

    assert 'href="/activity-review/new?subject_uid=user_learner&amp;time_period=30d"' in page


def test_an_empty_queue_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch, _orchestrator(Result.ok([]))).get(QUEUE)

    assert EMPTY_QUEUE in _assert_in_queue_shell(response.text)


def test_a_failed_read_is_a_banner_in_the_shell_not_an_empty_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed: Result[list[PendingReviewItem]] = Result.fail(
        Errors.database("get_pending_reviews", "read failed")
    )
    response = _client(monkeypatch, _orchestrator(failed)).get(QUEUE)

    assert response.status_code == 200
    main = _assert_in_queue_shell(response.text)
    assert "Could not load the review queue" in main
    assert 'role="alert"' in main
    assert EMPTY_QUEUE not in response.text
    assert "read failed" not in response.text  # the detail renders only in debug


def test_a_crash_is_a_banner_in_the_shell_not_an_empty_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch, _orchestrator(RuntimeError("socket closed"))).get(QUEUE)

    assert response.status_code == 200
    main = _assert_in_queue_shell(response.text)
    assert "Could not load the review queue" in main
    assert EMPTY_QUEUE not in response.text
    assert "socket closed" not in response.text


def test_a_non_admin_is_refused_before_the_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = _orchestrator(Result.ok(PENDING))
    response = _client(monkeypatch, orchestrator, role=UserRole.MEMBER).get(QUEUE)

    assert response.status_code == 403
    orchestrator.get_pending_reviews.assert_not_awaited()
