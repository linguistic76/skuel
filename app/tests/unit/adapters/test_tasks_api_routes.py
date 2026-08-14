"""Tasks API security/wiring pins (adapters/inbound/tasks_api.py).

Testing-gap roadmap item 6, first tranche: the per-domain ``*_api.py``
mutation modules had zero TestClient coverage — PR #702 proved this class of
gap ships real bugs (12 admin/teacher routes 400'd from the day they were
written). These are PIN tests, not exhaustive route coverage: auth gate,
CSRF gate, ownership verification, one happy-path mutation with exact
service kwargs, one malformed-body guard, and one field-update-factory
route. Harness mirrors ``test_admin_api_security.py`` — real ``fast_app`` +
CSRF minting + mocked services.

Auth seam: ``tasks_api`` imports ``require_authenticated_user`` at module
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
from adapters.inbound.tasks_api import create_tasks_api_routes
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent
from core.utils.result_simplified import Errors, Result

_OWNER_UID = "user_owner"
_TASK_UID = "task_1"
_CHILD_UID = "task_2"
_GOAL_UID = "goal_1"


def _fake_session_user(request: object) -> str:
    return _OWNER_UID


def _owned_task() -> Task:
    return Task(uid=_TASK_UID, title="Pinned task", user_uid=_OWNER_UID)


def _make_services() -> tuple[MagicMock, MagicMock]:
    tasks_service = MagicMock()
    tasks_service.verify_ownership = AsyncMock(return_value=Result.ok(_owned_task()))
    tasks_service.get_subtasks = AsyncMock(return_value=Result.ok([]))
    tasks_service.get_parent_task = AsyncMock(return_value=Result.ok(None))
    tasks_service.remove_subtask_relationship = AsyncMock(return_value=Result.ok(True))
    tasks_service.create_subtask_relationship = AsyncMock(return_value=Result.ok(True))
    tasks_service.link_task_to_goal = AsyncMock(return_value=Result.ok(True))
    tasks_service.update_task = AsyncMock(return_value=Result.ok(_owned_task()))

    goals_service = MagicMock()
    goals_service.verify_ownership = AsyncMock(return_value=Result.ok(MagicMock()))
    return tasks_service, goals_service


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> tuple[TestClient, MagicMock, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)
    tasks_service, goals_service = _make_services()

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.auth.session.get_current_user",
            _fake_session_user,
        )

    create_tasks_api_routes(app, rt, tasks_service, goals_service)
    return TestClient(app), tasks_service, goals_service


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
        client, tasks_service, _goals = _make_client(monkeypatch, authenticated=False)

        response = client.get(f"/api/tasks/children?uid={_TASK_UID}")

        assert response.status_code == 401
        tasks_service.verify_ownership.assert_not_awaited()
        tasks_service.get_subtasks.assert_not_awaited()


class TestCsrfGate:
    def test_remove_child_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, tasks_service, _goals = _make_client(monkeypatch)

        response = client.post(
            "/api/tasks/remove-child",
            json={"parent_uid": _TASK_UID, "child_uid": _CHILD_UID},
        )

        assert response.status_code == 403
        tasks_service.verify_ownership.assert_not_awaited()
        tasks_service.remove_subtask_relationship.assert_not_awaited()


class TestOwnership:
    def test_children_of_foreign_task_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # verify_entity_ownership surfaces the service's NotFound Result —
        # entities owned by ANOTHER user must read as "not found", never 403.
        client, tasks_service, _goals = _make_client(monkeypatch)
        tasks_service.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found("task", _TASK_UID))
        )

        response = client.get(f"/api/tasks/children?uid={_TASK_UID}")

        assert response.status_code == 404
        tasks_service.get_subtasks.assert_not_awaited()

    def test_link_goal_refuses_foreign_goal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Cross-service pin: task ownership passes, goal belongs to another
        # user — the link must not be created.
        client, tasks_service, goals_service = _make_client(monkeypatch)
        goals_service.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found("goal", _GOAL_UID))
        )

        response = _post_json(
            client,
            "/api/tasks/link-goal",
            {"task_uid": _TASK_UID, "goal_uid": _GOAL_UID},
        )

        assert response.status_code == 404
        tasks_service.link_task_to_goal.assert_not_awaited()


class TestMutations:
    def test_remove_child_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, tasks_service, _goals = _make_client(monkeypatch)

        response = _post_json(
            client,
            "/api/tasks/remove-child",
            {"parent_uid": _TASK_UID, "child_uid": _CHILD_UID},
        )

        assert response.status_code == 200
        assert response.json() == {"removed": True}
        tasks_service.remove_subtask_relationship.assert_awaited_once_with(_TASK_UID, _CHILD_UID)


class TestInputGuards:
    def test_non_json_body_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # text/plain so the malformed body reaches parse_json_body's own guard —
        # FastHTML pre-parses application/json bodies during param extraction.
        client, tasks_service, _goals = _make_client(monkeypatch)

        token = mint_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)
        response = client.post(
            "/api/tasks/remove-child",
            content=b"not json",
            headers={CSRF_HEADER_NAME: token, "content-type": "text/plain"},
        )

        assert response.status_code == 400
        tasks_service.verify_ownership.assert_not_awaited()
        tasks_service.remove_subtask_relationship.assert_not_awaited()

    def test_children_missing_uid_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, tasks_service, _goals = _make_client(monkeypatch)

        response = client.get("/api/tasks/children")

        assert response.status_code == 400
        tasks_service.verify_ownership.assert_not_awaited()
        tasks_service.get_subtasks.assert_not_awaited()


class TestFieldUpdateRoutes:
    """Routes registered via create_activity_field_api_routes (status/priority)."""

    def test_status_update_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, tasks_service, _goals = _make_client(monkeypatch)

        response = _post_form(client, f"/api/tasks/{_TASK_UID}/status", {"status": "completed"})

        assert response.status_code == 200
        tasks_service.update_task.assert_awaited_once_with(
            _TASK_UID, TaskUpdateIntent(status="completed")
        )

    def test_invalid_priority_value_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, tasks_service, _goals = _make_client(monkeypatch)

        response = _post_form(client, f"/api/tasks/{_TASK_UID}/priority", {"priority": "bananas"})

        assert "Invalid priority value" in response.text
        tasks_service.update_task.assert_not_awaited()
