"""Events API security/wiring pins (adapters/inbound/events_api.py).

Testing-gap roadmap item 6, first tranche: the per-domain ``*_api.py``
mutation modules had no TestClient coverage — PR #702 proved this class of
gap ships real bugs (12 admin/teacher routes 400'd since they were written).
These are PIN tests, not exhaustive coverage:

- auth gate: unauthenticated GET → 401, service never touched
- CSRF gate: mutating POST without token → 403 before the handler body
- ownership semantics: another user's event → 404; cross-domain link-goal
  also 404s on a goal the user does not own (goals_service seam)
- happy-path mutation: ``POST /api/events/link-goal`` → 200 with the service
  awaited on the exact positional args from the parsed request
- invalid-input guard: ``add-child`` with parent == child → 400 before any
  ownership check or service call
- factory-registered field-update route (``create_activity_field_api_routes``)

Harness mirrors ``test_admin_api_security.py`` — real
``fast_app(pico=False, default_hdrs=False)`` + TestClient + CSRF minting +
mocked services. Auth is faked by patching ``require_authenticated_user`` at
the name each consuming module actually resolves at call time.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.events_api import create_events_api_routes
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_owner"
_EVENT_UID = "event_1"
_GOAL_UID = "goal_1"

# The handlers resolve require_authenticated_user as a module global at call
# time — patch the name in the module that actually uses it (events_api for
# the hand-written routes, the field factory for the factory-made routes).
_EVENTS_AUTH_SEAM = "adapters.inbound.events_api.require_authenticated_user"
_FIELD_FACTORY_AUTH_SEAM = (
    "adapters.inbound.route_factories.activity_field_api_factory.require_authenticated_user"
)


def _fake_auth(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _csrf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


def _make_services() -> tuple[MagicMock, MagicMock]:
    events_service = MagicMock()
    events_service.verify_ownership = AsyncMock(return_value=Result.ok(True))
    events_service.get_subevents = AsyncMock(return_value=Result.ok([]))
    events_service.get_parent_event = AsyncMock(return_value=Result.ok(None))
    events_service.create_subevent_relationship = AsyncMock(return_value=Result.ok(True))
    events_service.remove_subevent_relationship = AsyncMock(return_value=Result.ok(True))
    events_service.link_event_to_goal = AsyncMock(return_value=Result.ok(True))
    events_service.update_event = AsyncMock(return_value=Result.ok(MagicMock()))

    goals_service = MagicMock()
    goals_service.verify_ownership = AsyncMock(return_value=Result.ok(True))
    return events_service, goals_service


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> tuple[TestClient, MagicMock, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)
    events_service, goals_service = _make_services()

    if authenticated:
        monkeypatch.setattr(_EVENTS_AUTH_SEAM, _fake_auth)
        monkeypatch.setattr(_FIELD_FACTORY_AUTH_SEAM, _fake_auth)

    create_events_api_routes(app, rt, events_service, goals_service)
    return TestClient(app), events_service, goals_service


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


class TestAuthGate:
    def test_unauthenticated_children_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, events_service, _goals = _make_client(monkeypatch, authenticated=False)

        response = client.get(f"/api/events/children?uid={_EVENT_UID}")

        assert response.status_code == 401
        events_service.verify_ownership.assert_not_awaited()
        events_service.get_subevents.assert_not_awaited()


class TestCsrfGate:
    def test_remove_child_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, events_service, _goals = _make_client(monkeypatch)

        response = client.post(
            "/api/events/remove-child",
            json={"parent_uid": _EVENT_UID, "child_uid": "event_2"},
        )

        assert response.status_code == 403
        events_service.verify_ownership.assert_not_awaited()
        events_service.remove_subevent_relationship.assert_not_awaited()


class TestOwnership:
    def test_children_of_another_users_event_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, events_service, _goals = _make_client(monkeypatch)
        events_service.verify_ownership.return_value = Result.fail(
            Errors.not_found("event", _EVENT_UID)
        )

        response = client.get(f"/api/events/children?uid={_EVENT_UID}")

        assert response.status_code == 404
        events_service.verify_ownership.assert_awaited_once_with(_EVENT_UID, _USER_UID)
        events_service.get_subevents.assert_not_awaited()

    def test_link_goal_with_foreign_goal_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Event is owned, goal is not: the cross-domain goals_service ownership
        # seam must refuse with not-found before the link is written.
        client, events_service, goals_service = _make_client(monkeypatch)
        goals_service.verify_ownership.return_value = Result.fail(
            Errors.not_found("goal", _GOAL_UID)
        )

        response = client.post(
            "/api/events/link-goal",
            json={"event_uid": _EVENT_UID, "goal_uid": _GOAL_UID},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 404
        goals_service.verify_ownership.assert_awaited_once_with(_GOAL_UID, _USER_UID)
        events_service.link_event_to_goal.assert_not_awaited()


class TestLinkGoal:
    def test_valid_link_is_200_with_exact_service_args(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, events_service, goals_service = _make_client(monkeypatch)

        response = client.post(
            "/api/events/link-goal",
            json={"event_uid": _EVENT_UID, "goal_uid": _GOAL_UID, "contribution_weight": 0.75},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 200
        events_service.verify_ownership.assert_awaited_once_with(_EVENT_UID, _USER_UID)
        goals_service.verify_ownership.assert_awaited_once_with(_GOAL_UID, _USER_UID)
        events_service.link_event_to_goal.assert_awaited_once_with(_EVENT_UID, _GOAL_UID, 0.75)
        assert response.json() == {"linked": True}


class TestAddChildGuards:
    def test_self_parenting_is_400_before_ownership(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, events_service, _goals = _make_client(monkeypatch)

        response = client.post(
            "/api/events/add-child",
            json={"parent_uid": _EVENT_UID, "child_uid": _EVENT_UID},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 400
        events_service.verify_ownership.assert_not_awaited()
        events_service.create_subevent_relationship.assert_not_awaited()


class TestFieldUpdateRoutes:
    """Pins for the create_activity_field_api_routes-registered routes."""

    def test_priority_route_rejects_unknown_value_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, events_service, _goals = _make_client(monkeypatch)

        response = client.post(
            f"/api/events/{_EVENT_UID}/priority",
            data={"priority": "not-a-priority"},
            headers=_csrf_headers(client),
        )

        # HTMX error-banner fragment renders with 200; the load-bearing pins
        # are the ownership check firing and the service never being touched.
        assert response.status_code == 200
        events_service.verify_ownership.assert_awaited_once_with(_EVENT_UID, _USER_UID)
        events_service.update_event.assert_not_awaited()
