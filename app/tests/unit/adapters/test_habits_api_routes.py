"""Habits API security/wiring pins (adapters/inbound/habits_api.py).

Testing-gap roadmap item 6, first tranche: the per-domain ``*_api.py``
mutation modules had no TestClient coverage — PR #702 proved this class of
gap ships real bugs (12 admin/teacher routes 400'd since they were written).
These are PIN tests, not exhaustive coverage:

- auth gate: unauthenticated GET → 401, service never touched
- CSRF gate: mutating POST without token → 403 before the handler body
- ownership semantics: another user's habit → 404 (not-found, no enumeration)
- happy-path mutation: ``POST /api/habits/track`` (the domain's core
  mutation) → 201 with the service awaited on the exact parsed request
- invalid-input guard: bad payload → 400 before the service is touched
- factory-registered field-update route (``create_activity_field_api_routes``)

Harness mirrors ``test_admin_api_security.py`` — real
``fast_app(pico=False, default_hdrs=False)`` + TestClient + CSRF minting +
mocked services. Auth is faked by patching ``require_authenticated_user`` at
the name each consuming module actually resolves at call time.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.habits_api import create_habits_api_routes
from core.models.habit.habit_request import TrackHabitRequest
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_owner"
_HABIT_UID = "habit_1"

# The handlers resolve require_authenticated_user as a module global at call
# time — patch the name in the module that actually uses it (habits_api for
# the hand-written routes, the field factory for the factory-made routes).
_HABITS_AUTH_SEAM = "adapters.inbound.habits_api.require_authenticated_user"
_FIELD_FACTORY_AUTH_SEAM = (
    "adapters.inbound.route_factories.activity_field_api_factory.require_authenticated_user"
)


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _completion() -> MagicMock:
    completion = MagicMock()
    completion.uid = "hc_1"
    completion.habit_uid = _HABIT_UID
    completion.completed_at = datetime(2026, 7, 18, 8, 30)
    completion.quality = 3
    return completion


def _make_services() -> tuple[MagicMock, MagicMock]:
    habits_service = MagicMock()
    habits_service.verify_ownership = AsyncMock(return_value=Result.ok(True))
    habits_service.track_habit = AsyncMock(return_value=Result.ok(_completion()))
    habits_service.get_habit_streak = AsyncMock(
        return_value=Result.ok({"current_streak": 3, "best_streak": 7})
    )
    habits_service.update_habit = AsyncMock(return_value=Result.ok(MagicMock()))

    principles_service = MagicMock()
    principles_service.verify_ownership = AsyncMock(return_value=Result.ok(True))
    return habits_service, principles_service


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> tuple[TestClient, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)
    habits_service, principles_service = _make_services()

    if authenticated:
        monkeypatch.setattr(_HABITS_AUTH_SEAM, _fake_auth)
        monkeypatch.setattr(_FIELD_FACTORY_AUTH_SEAM, _fake_auth)

    create_habits_api_routes(app, rt, habits_service, principles_service)
    return TestClient(app), habits_service


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


class TestAuthGate:
    def test_unauthenticated_streak_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch, authenticated=False)

        response = client.get(f"/api/habits/streak?uid={_HABIT_UID}")

        assert response.status_code == 401
        service.verify_ownership.assert_not_awaited()
        service.get_habit_streak.assert_not_awaited()


class TestCsrfGate:
    def test_track_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = client.post("/api/habits/track", json={"habit_uid": _HABIT_UID})

        assert response.status_code == 403
        service.verify_ownership.assert_not_awaited()
        service.track_habit.assert_not_awaited()


class TestOwnership:
    def test_streak_for_another_users_habit_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)
        service.verify_ownership.return_value = Result.fail(Errors.not_found("habit", _HABIT_UID))

        response = client.get(f"/api/habits/streak?uid={_HABIT_UID}")

        assert response.status_code == 404
        service.verify_ownership.assert_awaited_once_with(_HABIT_UID, _USER_UID)
        service.get_habit_streak.assert_not_awaited()


class TestTrackHabit:
    def test_valid_track_is_201_with_exact_service_args(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch)

        response = client.post(
            "/api/habits/track",
            json={"habit_uid": _HABIT_UID, "value": 3, "notes": "morning run"},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 201
        service.verify_ownership.assert_awaited_once_with(_HABIT_UID, _USER_UID)
        service.track_habit.assert_awaited_once_with(
            TrackHabitRequest(habit_uid=_HABIT_UID, value=3, notes="morning run")
        )
        body = response.json()
        assert body["uid"] == "hc_1"
        assert body["habit_uid"] == _HABIT_UID
        assert body["completed_at"] == "2026-07-18T08:30:00"
        assert body["quality"] == 3

    def test_out_of_range_value_is_400_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TrackHabitRequest.value is 1..5; 99 must die in Pydantic validation.
        client, service = _make_client(monkeypatch)

        response = client.post(
            "/api/habits/track",
            json={"habit_uid": _HABIT_UID, "value": 99},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 400
        service.verify_ownership.assert_not_awaited()
        service.track_habit.assert_not_awaited()

    def test_streak_missing_uid_is_400_before_ownership(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch)

        response = client.get("/api/habits/streak")

        assert response.status_code == 400
        service.verify_ownership.assert_not_awaited()
        service.get_habit_streak.assert_not_awaited()


class TestFieldUpdateRoutes:
    """Pins for the create_activity_field_api_routes-registered routes."""

    def test_priority_route_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, service = _make_client(monkeypatch)

        response = client.post(f"/api/habits/{_HABIT_UID}/priority", data={"priority": "high"})

        assert response.status_code == 403
        service.verify_ownership.assert_not_awaited()
        service.update_habit.assert_not_awaited()

    def test_priority_route_rejects_unknown_value_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, service = _make_client(monkeypatch)

        response = client.post(
            f"/api/habits/{_HABIT_UID}/priority",
            data={"priority": "not-a-priority"},
            headers=_csrf_headers(client),
        )

        # HTMX error-banner fragment renders with 200; the load-bearing pins
        # are the ownership check firing and the service never being touched.
        assert response.status_code == 200
        service.verify_ownership.assert_awaited_once_with(_HABIT_UID, _USER_UID)
        service.update_habit.assert_not_awaited()
