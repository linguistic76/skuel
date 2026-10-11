"""Context-Aware API security/wiring pins (adapters/inbound/context_aware_api.py).

PIN tests over the UserContext routes — auth gate (401), CSRF on the mutating
context integrations (403), the owner check on the goal or habit each
integration names (the route's, before the service — a refusal never reaches
it), the integration bodies bound through ``parse_body`` (400 before the
service, JSON or form), the time_window whitelist guard (400 before the
service), and exact service kwargs. Harness mirrors
``test_choices_api_routes.py``; it installs no app-level exception guard, so
every 400 here is the route's own.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.context_aware_api import create_context_aware_api_routes
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_owner"
# The uids the fake verifiers refuse — another user's entity and one naming nothing
# answer alike.
_REFUSED = frozenset({"goal_foreign", "habit_foreign", "goal_missing", "habit_missing"})


def _fake_auth(request: object) -> str:
    return _USER_UID


class _FakeVerifier:
    """``OwnershipVerifier``: the caller owns every uid but the refused ones."""

    def __init__(self, resource: str) -> None:
        self.resource = resource
        self.checked: list[tuple[str, str]] = []

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[object]:
        self.checked.append((uid, user_uid))
        if uid in _REFUSED or user_uid != _USER_UID:
            return Result.fail(Errors.not_found(resource=self.resource, identifier=uid))
        return Result.ok(object())


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    context: MagicMock
    goals: _FakeVerifier
    habits: _FakeVerifier


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    service = MagicMock()
    service.get_context_dashboard = AsyncMock(return_value=Result.ok({"widgets": []}))
    service.create_tasks_from_goal_context = AsyncMock(return_value=Result.ok([]))
    service.complete_habit_with_context = AsyncMock(return_value=Result.ok({"ok": True}))
    service.get_context_summary = AsyncMock(return_value=Result.ok({"insights": []}))
    service.get_next_action = AsyncMock(return_value=Result.ok({"action": "rest"}))
    service.get_at_risk_habits = AsyncMock(return_value=Result.ok({"habits": []}))
    service.get_context_health = AsyncMock(return_value=Result.ok({"score": 1.0}))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.context_aware_api.require_authenticated_user", _fake_auth
        )

    goals = _FakeVerifier("Goal")
    habits = _FakeVerifier("Habit")
    create_context_aware_api_routes(None, rt, service, goals=goals, habits=habits)
    return _Harness(client=TestClient(app), context=service, goals=goals, habits=habits)


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


class TestAuthGate:
    def test_dashboard_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get("/api/context/dashboard")

        assert response.status_code == 401
        harness.context.get_context_dashboard.assert_not_awaited()


class TestCsrfEnforcement:
    def test_habit_complete_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.post(
            "/api/context/habit/complete?habit_uid=habit_1",
            json={"context": {}},
        )

        assert response.status_code == 403
        harness.context.complete_habit_with_context.assert_not_awaited()


def _post_form(client: TestClient, path: str, data: dict[str, str]):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, data=data, headers={CSRF_HEADER_NAME: token})


_GOAL_TASKS = "/api/context/goal/tasks?goal_uid=goal_1"
_HABIT_COMPLETE = "/api/context/habit/complete?habit_uid=habit_1"


def _masked(response: httpx.Response, word: str) -> str:
    """A refusal body with its per-request timestamp removed and its uid masked."""
    body = dict(response.json())
    body.pop("timestamp", None)
    return str(body).replace(word, "<uid>")


class TestOwnerCheck:
    """Each integration verifies the caller owns the uid it names, before the service:
    another user's goal or habit is answered exactly as a uid that names nothing."""

    @pytest.mark.parametrize(
        ("path", "service_method"),
        [
            ("/api/context/goal/tasks?goal_uid={uid}", "create_tasks_from_goal_context"),
            ("/api/context/habit/complete?habit_uid={uid}", "complete_habit_with_context"),
        ],
        ids=["goal-tasks", "habit-complete"],
    )
    def test_foreign_answers_as_missing_and_never_reaches_the_service(
        self, monkeypatch: pytest.MonkeyPatch, path: str, service_method: str
    ) -> None:
        harness = _make_harness(monkeypatch)
        kind = "goal" if "goal_uid" in path else "habit"

        foreign = _post_json(harness.client, path.format(uid=f"{kind}_foreign"))
        missing = _post_json(harness.client, path.format(uid=f"{kind}_missing"))

        assert foreign.status_code == missing.status_code == 404
        assert _masked(foreign, "foreign") == _masked(missing, "missing")
        getattr(harness.context, service_method).assert_not_awaited()

    def test_own_goal_and_habit_are_checked_then_served(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        assert _post_json(harness.client, _GOAL_TASKS).status_code == 201
        assert _post_json(harness.client, _HABIT_COMPLETE).status_code == 200

        assert harness.goals.checked == [("goal_1", _USER_UID)]
        assert harness.habits.checked == [("habit_1", _USER_UID)]
        harness.context.create_tasks_from_goal_context.assert_awaited_once()
        harness.context.complete_habit_with_context.assert_awaited_once()

    @pytest.mark.parametrize("missing", ["goals", "habits"])
    def test_registration_refuses_without_a_verifier(self, missing: str) -> None:
        _, rt = fast_app(pico=False, default_hdrs=False)
        verifiers = {"goals": _FakeVerifier("Goal"), "habits": _FakeVerifier("Habit")}
        verifiers[missing] = None  # type: ignore[assignment]

        with pytest.raises(ValueError, match="cannot be registered without"):
            create_context_aware_api_routes(None, rt, MagicMock(), **verifiers)


class TestContextIntegrationBodies:
    """Both integration bodies bind through ``parse_body``: a rejected field is a 400
    before the service, JSON or form-encoded, and an empty body takes the defaults."""

    @pytest.mark.parametrize(
        "body",
        [
            {"auto_create": "maybe"},
            {"context_preferences": [1]},
        ],
    )
    def test_goal_tasks_bad_json_field_is_400(
        self, monkeypatch: pytest.MonkeyPatch, body: dict[str, object]
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, _GOAL_TASKS, body)

        assert response.status_code == 400
        harness.context.create_tasks_from_goal_context.assert_not_awaited()

    def test_goal_tasks_bad_form_field_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_form(harness.client, _GOAL_TASKS, {"auto_create": "maybe"})

        assert response.status_code == 400
        harness.context.create_tasks_from_goal_context.assert_not_awaited()

    def test_goal_tasks_form_body_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_form(harness.client, _GOAL_TASKS, {"auto_create": "false"})

        assert response.status_code == 201
        harness.context.create_tasks_from_goal_context.assert_awaited_once_with(
            goal_uid="goal_1", user_uid=_USER_UID, context_preferences={}, auto_create=False
        )

    def test_goal_tasks_empty_body_takes_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, _GOAL_TASKS)

        assert response.status_code == 201
        harness.context.create_tasks_from_goal_context.assert_awaited_once_with(
            goal_uid="goal_1", user_uid=_USER_UID, context_preferences={}, auto_create=True
        )

    @pytest.mark.parametrize(
        "body",
        [
            {"quality": "meh"},
            {"environmental_factors": [1]},
        ],
    )
    def test_habit_complete_bad_json_field_is_400(
        self, monkeypatch: pytest.MonkeyPatch, body: dict[str, object]
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(harness.client, _HABIT_COMPLETE, body)

        assert response.status_code == 400
        harness.context.complete_habit_with_context.assert_not_awaited()

    def test_habit_complete_bad_form_field_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_form(harness.client, _HABIT_COMPLETE, {"quality": "meh"})

        assert response.status_code == 400
        harness.context.complete_habit_with_context.assert_not_awaited()

    def test_habit_complete_json_body_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _post_json(
            harness.client,
            _HABIT_COMPLETE,
            {"quality": "poor", "environmental_factors": {"location": "home"}},
        )

        assert response.status_code == 200
        harness.context.complete_habit_with_context.assert_awaited_once_with(
            habit_uid="habit_1",
            user_uid=_USER_UID,
            completion_quality="poor",
            environmental_factors={"location": "home"},
        )


class TestDashboard:
    def test_defaults_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/context/dashboard")

        assert response.status_code == 200
        harness.context.get_context_dashboard.assert_awaited_once_with(
            user_uid=_USER_UID, include_predictions=True, time_window="7d"
        )

    def test_invalid_time_window_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/context/dashboard?time_window=42d")

        assert response.status_code == 400
        harness.context.get_context_dashboard.assert_not_awaited()


class TestAnalyticsReads:
    def test_health_scopes_to_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/context/health")

        assert response.status_code == 200
        harness.context.get_context_health.assert_awaited_once_with(_USER_UID)
