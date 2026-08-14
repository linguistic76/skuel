"""Goals API security/wiring pins (adapters/inbound/goals_api.py).

Testing-gap roadmap item 6, first tranche: the per-domain ``*_api.py``
mutation modules had zero TestClient coverage — PR #702 proved this class of
gap ships real bugs (12 admin/teacher routes 400'd from the day they were
written). These are PIN tests, not exhaustive route coverage: auth gate,
CSRF gate, ownership verification (including the cross-service principle
check), one happy-path mutation with exact service args, one malformed-body
guard, and one field-update-factory route. Harness mirrors
``test_admin_api_security.py`` — real ``fast_app`` + CSRF minting + mocked
services.

Auth seam: ``goals_api`` imports ``require_authenticated_user`` at module
level and ``activity_field_api_factory`` imports its own copy, but both
function objects resolve ``get_current_user`` through
``adapters.inbound.auth.session`` module globals at call time — so patching
``adapters.inbound.auth.session.get_current_user`` authenticates every seam
at once while keeping the real 401-raising ``require_authenticated_user``
in the loop.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.goals_api import create_goals_api_routes
from core.models.enums.relationship_enums import ProficiencyLevel
from core.models.goal.goal import Goal
from core.utils.result_simplified import Errors, Result

_OWNER_UID = "user_owner"
_GOAL_UID = "goal_1"
_CHILD_UID = "goal_2"
_KU_UID = "ku_math_abc123"
_PRINCIPLE_UID = "principle_1"


def _fake_session_user(request: object) -> str:
    return _OWNER_UID


def _owned_goal() -> Goal:
    return Goal(uid=_GOAL_UID, title="Pinned goal", user_uid=_OWNER_UID)


def _make_services() -> tuple[MagicMock, MagicMock]:
    goals_service = MagicMock()
    goals_service.verify_ownership = AsyncMock(return_value=Result.ok(_owned_goal()))
    goals_service.get_subgoals = AsyncMock(return_value=Result.ok([]))
    goals_service.get_parent_goal = AsyncMock(return_value=Result.ok(None))
    goals_service.remove_subgoal_relationship = AsyncMock(return_value=Result.ok(True))
    goals_service.create_subgoal_relationship = AsyncMock(return_value=Result.ok(True))
    goals_service.link_goal_to_knowledge = AsyncMock(return_value=Result.ok(True))
    goals_service.link_goal_to_principle = AsyncMock(return_value=Result.ok(True))
    # set_status is captured into the FieldUpdateSpec at registration time,
    # so it must be an AsyncMock BEFORE create_goals_api_routes runs.
    goals_service.set_status = AsyncMock(return_value=Result.ok(_owned_goal()))
    goals_service.update_goal = AsyncMock(return_value=Result.ok(_owned_goal()))

    principles_service = MagicMock()
    principles_service.verify_ownership = AsyncMock(return_value=Result.ok(MagicMock()))
    return goals_service, principles_service


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> tuple[TestClient, MagicMock, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)
    goals_service, principles_service = _make_services()

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.auth.session.get_current_user",
            _fake_session_user,
        )

    # user_service is asserted at wiring time (fail-fast) — a mock satisfies it;
    # these tests only exercise the field/hierarchy/link routes.
    create_goals_api_routes(app, rt, goals_service, principles_service, user_service=MagicMock())
    return TestClient(app), goals_service, principles_service


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


def _post_form(client: TestClient, path: str, data: dict[str, str]):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, data=data, headers={CSRF_HEADER_NAME: token})


class TestAuthGate:
    def test_children_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch, authenticated=False)

        response = client.get(f"/api/goals/children?uid={_GOAL_UID}")

        assert response.status_code == 401
        goals_service.verify_ownership.assert_not_awaited()
        goals_service.get_subgoals.assert_not_awaited()


class TestCsrfGate:
    def test_remove_child_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = client.post(
            "/api/goals/remove-child",
            json={"parent_uid": _GOAL_UID, "child_uid": _CHILD_UID},
        )

        assert response.status_code == 403
        goals_service.verify_ownership.assert_not_awaited()
        goals_service.remove_subgoal_relationship.assert_not_awaited()


class TestOwnership:
    def test_children_of_foreign_goal_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # verify_entity_ownership surfaces the service's NotFound Result —
        # entities owned by ANOTHER user must read as "not found", never 403.
        client, goals_service, _principles = _make_client(monkeypatch)
        goals_service.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found("goal", _GOAL_UID))
        )

        response = client.get(f"/api/goals/children?uid={_GOAL_UID}")

        assert response.status_code == 404
        goals_service.get_subgoals.assert_not_awaited()

    def test_link_principle_refuses_foreign_principle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Cross-service pin: goal ownership passes, principle belongs to
        # another user — the link must not be created.
        client, goals_service, principles_service = _make_client(monkeypatch)
        principles_service.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found("principle", _PRINCIPLE_UID))
        )

        response = _post_json(
            client,
            "/api/goals/link-principle",
            {"goal_uid": _GOAL_UID, "principle_uid": _PRINCIPLE_UID},
        )

        assert response.status_code == 404
        goals_service.link_goal_to_principle.assert_not_awaited()


class TestMutations:
    def test_link_knowledge_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_json(
            client,
            "/api/goals/link-knowledge",
            {"goal_uid": _GOAL_UID, "knowledge_uid": _KU_UID},
        )

        assert response.status_code == 200
        assert response.json() == {"linked": True}
        goals_service.link_goal_to_knowledge.assert_awaited_once_with(
            _GOAL_UID, _KU_UID, ProficiencyLevel.INTERMEDIATE, 1
        )


class TestInputGuards:
    def test_non_json_body_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # text/plain so the malformed body reaches parse_json_body's own guard —
        # FastHTML pre-parses application/json bodies during param extraction.
        client, goals_service, _principles = _make_client(monkeypatch)

        token = mint_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)
        response = client.post(
            "/api/goals/link-knowledge",
            content=b"not json",
            headers={CSRF_HEADER_NAME: token, "content-type": "text/plain"},
        )

        assert response.status_code == 400
        goals_service.verify_ownership.assert_not_awaited()
        goals_service.link_goal_to_knowledge.assert_not_awaited()

    def test_children_missing_uid_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = client.get("/api/goals/children")

        assert response.status_code == 400
        goals_service.verify_ownership.assert_not_awaited()
        goals_service.get_subgoals.assert_not_awaited()


class TestFieldUpdateRoutes:
    """Routes registered via create_activity_field_api_routes (status/priority)."""

    def test_status_update_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Goals wire set_status directly as the FieldUpdateSpec apply — the
        # transition dispatch (activate/complete/archive side effects) lives
        # in the service, so the route must pass the raw value through.
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_form(client, f"/api/goals/{_GOAL_UID}/status", {"status": "active"})

        assert response.status_code == 200
        goals_service.set_status.assert_awaited_once_with(_GOAL_UID, "active")

    def test_invalid_priority_value_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_form(client, f"/api/goals/{_GOAL_UID}/priority", {"priority": "bananas"})

        assert "Invalid priority value" in response.text
        goals_service.update_goal.assert_not_awaited()
