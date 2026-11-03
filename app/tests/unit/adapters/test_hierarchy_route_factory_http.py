"""The tree-manipulation API (``HierarchyRouteFactory``) answers in JSON with a real status.

``POST /api/{domain}/{uid}/move``, ``PATCH /api/{domain}/{uid}`` and
``POST /api/{domain}/bulk-delete`` are read by ``SKUEL.postJson`` (``static/js/skuel.js``),
which rejects on a non-2xx status and toasts the error body's ``message``. A refusal
must therefore arrive as a 4xx JSON error, never as a 200: FastHTML renders a
returned ``(body, 400)`` tuple as an HTML page with status 200, which the client reads as
success. Real ``fast_app`` + TestClient, the service a fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.hierarchy_route_factory import HierarchyRouteFactory
from core.models.goal.goal_request import GoalUpdateRequest
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_owner"
_NODE_UID = "goal_node"
_PARENT_UID = "goal_parent"


def _fake_auth(request: object) -> str:
    return _USER_UID


def _make_service() -> MagicMock:
    service = MagicMock()
    service.verify_ownership = AsyncMock(return_value=Result.ok(True))
    service.update = AsyncMock(return_value=Result.ok(MagicMock()))
    service.delete = AsyncMock(return_value=Result.ok(True))
    service.get_parent_goal = AsyncMock(return_value=Result.ok(None))
    service.remove_subgoal_relationship = AsyncMock(return_value=Result.ok(True))
    service.create_subgoal_relationship = AsyncMock(return_value=Result.ok(True))
    return service


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    service: MagicMock


def _make_harness(monkeypatch: pytest.MonkeyPatch) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)
    monkeypatch.setattr("adapters.inbound.auth.session.get_current_user", _fake_auth)
    service = _make_service()
    HierarchyRouteFactory(
        rt=rt,
        domain="goals",
        service=service,
        entity_name="Goal",
        update_schema=GoalUpdateRequest,
    ).create_routes()
    return _Harness(client=TestClient(app), service=service)


def _send(client: TestClient, method: str, path: str, json: dict[str, object]) -> httpx2.Response:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.request(method, path, json=json, headers={CSRF_HEADER_NAME: token})


def _move(client: TestClient, json: dict[str, object]) -> httpx2.Response:
    return _send(client, "POST", f"/api/goals/{_NODE_UID}/move", json)


def _update(client: TestClient, json: dict[str, object]) -> httpx2.Response:
    return _send(client, "PATCH", f"/api/goals/{_NODE_UID}", json)


def _bulk_delete(client: TestClient, json: dict[str, object]) -> httpx2.Response:
    return _send(client, "POST", "/api/goals/bulk-delete", json)


def _refused(response: httpx2.Response, status: int) -> str:
    """A refusal as ``SKUEL.postJson`` reads it: the status, JSON, an error message."""
    assert response.status_code == status, response.text[:200]
    assert response.headers["content-type"].startswith("application/json")
    message = response.json()["message"]
    assert isinstance(message, str) and message
    return message


def _not_owned(uid: str, user_uid: str) -> Result[bool]:
    return Result.fail(Errors.not_found("Goal"))


class TestMove:
    def test_a_missing_parent_uid_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        _refused(_move(harness.client, {}), 400)
        harness.service.create_subgoal_relationship.assert_not_awaited()

    def test_an_unowned_node_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.service.verify_ownership.side_effect = _not_owned

        _refused(_move(harness.client, {"new_parent_uid": _PARENT_UID}), 404)
        harness.service.create_subgoal_relationship.assert_not_awaited()

    def test_an_unowned_parent_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        async def _owns_only_the_node(uid: str, user_uid: str) -> Result[bool]:
            return Result.ok(True) if uid == _NODE_UID else _not_owned(uid, user_uid)

        harness.service.verify_ownership.side_effect = _owns_only_the_node

        _refused(_move(harness.client, {"new_parent_uid": _PARENT_UID}), 404)
        harness.service.create_subgoal_relationship.assert_not_awaited()

    def test_a_refused_move_is_a_4xx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.service.create_subgoal_relationship.return_value = Result.fail(
            Errors.validation("A goal cannot be its own ancestor", field="parent_uid")
        )

        _refused(_move(harness.client, {"new_parent_uid": _PARENT_UID}), 400)

    def test_a_move_answers_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.service.get_parent_goal.return_value = Result.ok(SimpleNamespace(uid="goal_old"))

        response = _move(harness.client, {"new_parent_uid": _PARENT_UID})

        assert response.status_code == 200
        assert response.json() == {"success": True, "message": "Goal moved successfully"}
        harness.service.remove_subgoal_relationship.assert_awaited_once_with("goal_old", _NODE_UID)
        harness.service.create_subgoal_relationship.assert_awaited_once_with(_PARENT_UID, _NODE_UID)


class TestUpdate:
    def test_a_missing_title_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        _refused(_update(harness.client, {}), 400)
        harness.service.update.assert_not_awaited()

    def test_an_unowned_node_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.service.verify_ownership.side_effect = _not_owned

        _refused(_update(harness.client, {"title": "New"}), 404)
        harness.service.update.assert_not_awaited()

    def test_a_refused_update_is_a_4xx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.service.update.return_value = Result.fail(
            Errors.validation("Title too long", field="title")
        )

        _refused(_update(harness.client, {"title": "New"}), 400)

    def test_an_update_answers_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = _update(harness.client, {"title": "New"})

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "message": "Goal updated",
            "uid": _NODE_UID,
            "title": "New",
        }


class TestBulkDelete:
    def test_no_uids_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        _refused(_bulk_delete(harness.client, {}), 400)
        harness.service.delete.assert_not_awaited()

    def test_a_partial_delete_names_what_it_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        async def _owns_one(uid: str, user_uid: str) -> Result[bool]:
            return Result.ok(True) if uid == _NODE_UID else _not_owned(uid, user_uid)

        harness.service.verify_ownership.side_effect = _owns_one

        response = _bulk_delete(harness.client, {"uids": [_NODE_UID, "goal_foreign"]})

        assert response.status_code == 200
        assert response.json() == {
            "success": False,
            "deleted_count": 1,
            "errors": ["goal_foreign: Not found or access denied"],
        }
        harness.service.delete.assert_awaited_once_with(_NODE_UID)
