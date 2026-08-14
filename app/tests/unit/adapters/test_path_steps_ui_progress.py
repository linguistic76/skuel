"""Regression tests for the reading-first progress + bookmark POST handlers.

Pins three Arc-Care fixes on the routes registered by
``create_path_steps_ui_routes`` (``adapters/inbound/path_steps_ui.py``):

1. ``POST /explore/ps/{uid}/progress`` with an invalid/missing ``state`` used
   to fall through and return a 200 empty Div — fake success that left the
   caller's optimistic UI stuck. Now: 400 validation error with X-Toast
   headers.
2. Enrollment cap: with 2 PathSteps already in progress, ``state=learning``
   (no review) must return 422 with a toast about the cap and must NOT call
   ``mark_in_progress``.
3. ``POST /explore/ps/{uid}/bookmark``: a failed ``set_bookmark`` Result used
   to be discarded (200 Div). Now: error status with X-Toast headers (G7 —
   no more silent failures).

Harness: a real ``fast_app`` + Starlette TestClient — no Neo4j, no server.
CSRF is satisfied properly (double-submit cookie + X-CSRF-Token header, with
enforcement explicitly ON). Auth is monkeypatched at the handler's import
site (``require_authenticated_user`` reads the SessionMiddleware session,
which this Neo4j-free harness doesn't establish). ``result_to_response``
stays the real one — it is part of the contract under test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.path_steps_ui import create_path_steps_ui_routes
from core.utils.result_simplified import Errors, Result

_PS_UID = "ps.test.progress"
_USER_UID = "user_test"


def _fake_require_authenticated_user(request: object) -> str:
    """Stand-in for the session-reading auth helper (harness has no session)."""
    return _USER_UID


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Auth: the handlers call require_authenticated_user(request), which reads
    # request.session (SessionMiddleware). Patch it at the import site so the
    # harness stays Neo4j/login-free. CSRF is NOT patched — enforced for real.
    monkeypatch.setattr(
        "adapters.inbound.path_steps_ui.require_authenticated_user",
        _fake_require_authenticated_user,
    )


def _mastery_mock(
    *,
    in_progress_count: int = 0,
    mark_in_progress: Result[bool] | None = None,
    mark_as_read: Result[bool] | None = None,
    mark_as_learning: Result[bool] | None = None,
    set_bookmark: Result[bool] | None = None,
) -> MagicMock:
    """Build a PsService.mastery stand-in with AsyncMock operations."""
    mastery = MagicMock()
    mastery.count_in_progress_steps = AsyncMock(return_value=Result.ok(in_progress_count))
    mastery.mark_in_progress = AsyncMock(return_value=mark_in_progress or Result.ok(True))
    mastery.mark_as_read = AsyncMock(return_value=mark_as_read or Result.ok(True))
    mastery.mark_as_learning = AsyncMock(return_value=mark_as_learning or Result.ok(True))
    mastery.set_bookmark = AsyncMock(return_value=set_bookmark or Result.ok(True))
    return mastery


def _client_for(mastery: MagicMock) -> TestClient:
    app, rt = fast_app(pico=False, default_hdrs=False)
    ps_service = MagicMock()
    ps_service.mastery = mastery
    # ps_engagement_service / user_service / tasks_service omitted — those
    # route groups are skipped; only browser + learning-state routes register.
    create_path_steps_ui_routes(app, rt, ps_service)
    return TestClient(app)


def _post(client: TestClient, path: str, data: dict[str, str]) -> httpx2.Response:
    """POST with a valid double-submit CSRF pair (cookie + header)."""
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, data=data, headers={CSRF_HEADER_NAME: token})


# ============================================================================
# Harness sanity — CSRF is genuinely enforced, not bypassed
# ============================================================================


class TestCsrfStillEnforced:
    def test_post_without_token_is_rejected(self) -> None:
        client = _client_for(_mastery_mock())

        response = client.post(f"/explore/ps/{_PS_UID}/progress", data={"state": "read"})

        assert response.status_code == 403


# ============================================================================
# POST /explore/ps/{uid}/progress — invalid state must not fake success
# ============================================================================


class TestProgressInvalidState:
    def test_unknown_state_returns_400_with_toast_headers(self) -> None:
        mastery = _mastery_mock()
        client = _client_for(mastery)

        response = _post(client, f"/explore/ps/{_PS_UID}/progress", {"state": "bogus"})

        assert response.status_code == 400
        assert response.headers["X-Toast-Type"] == "error"
        assert "state" in response.headers["X-Toast-Message"]
        assert response.headers["content-type"].startswith("application/json")
        # No write reached the service.
        mastery.mark_as_read.assert_not_awaited()
        mastery.mark_as_learning.assert_not_awaited()
        mastery.mark_in_progress.assert_not_awaited()

    def test_missing_state_returns_400_not_fake_200(self) -> None:
        # The pre-fix fall-through returned 200 + empty Div here.
        mastery = _mastery_mock()
        client = _client_for(mastery)

        response = _post(client, f"/explore/ps/{_PS_UID}/progress", {})

        assert response.status_code == 400
        assert response.headers["X-Toast-Type"] == "error"
        mastery.mark_in_progress.assert_not_awaited()


# ============================================================================
# POST /explore/ps/{uid}/progress — enrollment cap (max 2 in progress)
# ============================================================================


class TestProgressEnrollmentCap:
    def test_cap_reached_returns_422_and_skips_enrollment(self) -> None:
        mastery = _mastery_mock(in_progress_count=2)
        client = _client_for(mastery)

        response = _post(client, f"/explore/ps/{_PS_UID}/progress", {"state": "learning"})

        assert response.status_code == 422
        assert response.headers["X-Toast-Type"] == "error"
        assert "2 Path Steps" in response.headers["X-Toast-Message"]
        mastery.mark_in_progress.assert_not_awaited()

    def test_learning_under_cap_enrolls_and_returns_200(self) -> None:
        mastery = _mastery_mock(in_progress_count=1)
        client = _client_for(mastery)

        response = _post(client, f"/explore/ps/{_PS_UID}/progress", {"state": "learning"})

        assert response.status_code == 200
        mastery.mark_in_progress.assert_awaited_once_with(_USER_UID, _PS_UID)


# ============================================================================
# POST /explore/ps/{uid}/bookmark — failed writes must reach the user (G7)
# ============================================================================


class TestBookmark:
    def test_failed_set_bookmark_surfaces_error_with_toast_headers(self) -> None:
        # Pre-fix, the failed Result was discarded and the route returned 200.
        failed: Result[bool] = Result.fail(
            Errors.business(rule="bookmark_write", message="Bookmark write failed")
        )
        mastery = _mastery_mock(set_bookmark=failed)
        client = _client_for(mastery)

        response = _post(client, f"/explore/ps/{_PS_UID}/bookmark", {"on": "true"})

        assert response.status_code >= 400
        assert response.headers["X-Toast-Type"] == "error"
        assert "Bookmark write failed" in response.headers["X-Toast-Message"]

    def test_successful_set_bookmark_returns_200(self) -> None:
        mastery = _mastery_mock()
        client = _client_for(mastery)

        response = _post(client, f"/explore/ps/{_PS_UID}/bookmark", {"on": "true"})

        assert response.status_code == 200
        mastery.set_bookmark.assert_awaited_once_with(_USER_UID, _PS_UID, True)
