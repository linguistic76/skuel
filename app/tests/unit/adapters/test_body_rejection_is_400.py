"""A rejected request body is 400 at every route that validates one itself.

Why this exists
---------------
``boundary_handler`` ends in a catch-all that logs and returns 500, so a
``ValidationError`` raised *inside* a decorated handler is indistinguishable
from a crash: the client is told "server bug" about its own bad input. The
app-level ``install_request_validation_guard`` does not help here — it only sees
exceptions that escape the handler, and these are raised within it.

``parse_json_body`` is the seam that keeps the two apart, so the routes that
validate a body themselves go through it. These tests drive the real registered
routes, because the failure they guard against is invisible at the call site:
the code reads fine and the status is wrong.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from httpx import Response
from pydantic import BaseModel, Field
from starlette.testclient import TestClient

import adapters.inbound.pathways_api as pathways_api
import adapters.inbound.route_factories.crud_route_factory as crud_module
from adapters.inbound.route_factories.crud_route_factory import CRUDRouteFactory
from core.utils.result_simplified import Result

_CSRF = {"X-CSRF-Token": "tok", "content-type": "application/json"}
_COOKIES = {"csrf_token": "tok"}


def _fake_authenticated_user(request: object) -> str:
    """Stand in for the session lookup — these tests are about the body."""
    return "user_mike"


class _Schema(BaseModel):
    """Rejects an empty title, so a request can be bad in exactly one way."""

    title: str = Field(min_length=1)


def _to_entity(schema: _Schema, uid: str, user_uid: str) -> dict[str, str]:
    """Stand in for the domain's registered converter."""
    return {"uid": uid, "title": schema.title, "user_uid": user_uid}


def _crud_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app, rt = fast_app(pico=False, default_hdrs=False)
    monkeypatch.setattr(crud_module, "require_authenticated_user", _fake_authenticated_user)

    service = MagicMock()
    service.create = AsyncMock(return_value=Result.ok({"uid": "task_1"}))
    service.update_for_user = AsyncMock(return_value=Result.ok({"uid": "task_1"}))
    service.verify_ownership = AsyncMock(return_value=Result.ok(True))

    CRUDRouteFactory(
        service=service,
        domain_name="tasks",
        create_schema=_Schema,
        update_schema=_Schema,
        entity_converter=_to_entity,
    ).register_routes(app, rt)
    return TestClient(app)


def _assert_validation_400(response: Response) -> None:
    """The status AND the envelope — a 400 with a crash body is still a crash."""
    assert response.status_code == 400, response.text
    payload = json.loads(response.text)
    assert payload["category"] == "validation"
    assert "title" in payload["message"], "the message names no field the caller can fix"


@pytest.mark.parametrize("path", ["/api/tasks/create", "/api/tasks/update?uid=task_1"])
def test_crud_factory_rejects_a_bad_body_with_400(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """Both CRUD write routes validate the body themselves — and answer 400."""
    response = _crud_client(monkeypatch).post(
        path, json={"title": ""}, headers=_CSRF, cookies=_COOKIES
    )

    _assert_validation_400(response)


def test_pathways_progress_rejects_a_bad_body_with_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """`mastery_level` is bounded to 0..1; 5.0 is the caller's error, not ours."""
    app, rt = fast_app(pico=False, default_hdrs=False)
    monkeypatch.setattr(pathways_api, "require_authenticated_user", _fake_authenticated_user)
    pathways_api.create_pathways_api_routes(app, rt, MagicMock(), MagicMock(), MagicMock())

    response = TestClient(app).post(
        "/api/pathways/progress",
        json={"step_uid": "ps.demo.step", "mastery_level": 5.0},
        headers=_CSRF,
        cookies=_COOKIES,
    )

    assert response.status_code == 400, response.text
    assert json.loads(response.text)["category"] == "validation"


def test_a_valid_body_still_reaches_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard rejects bad input without swallowing good input."""
    response = _crud_client(monkeypatch).post(
        "/api/tasks/create", json={"title": "a real task"}, headers=_CSRF, cookies=_COOKIES
    )

    assert response.status_code == 201, response.text
