"""A rejected request body is 400 at every route that validates one itself.

Why this exists
---------------
``boundary_handler`` ends in a catch-all that logs and returns 500, so a
``ValidationError`` raised *inside* a decorated handler is indistinguishable
from a crash: the client is told "server bug" about its own bad input.

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
from core.models.event.event_request import EventCreateRequest, EventUpdateRequest
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
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
    return TestClient(app, cookies=_COOKIES)


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
    response = _crud_client(monkeypatch).post(path, json={"title": ""}, headers=_CSRF)

    _assert_validation_400(response)


def test_pathways_progress_rejects_a_bad_body_with_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """`mastery_level` is bounded to 0..1; 5.0 is the caller's error, not ours."""
    app, rt = fast_app(pico=False, default_hdrs=False)
    monkeypatch.setattr(pathways_api, "require_authenticated_user", _fake_authenticated_user)
    pathways_api.create_pathways_api_routes(app, rt, MagicMock(), MagicMock(), MagicMock())

    response = TestClient(app, cookies=_COOKIES).post(
        "/api/pathways/progress",
        json={"step_uid": "ps.demo.step", "mastery_level": 5.0},
        headers=_CSRF,
    )

    assert response.status_code == 400, response.text
    assert json.loads(response.text)["category"] == "validation"


def test_a_valid_body_still_reaches_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard rejects bad input without swallowing good input."""
    response = _crud_client(monkeypatch).post(
        "/api/tasks/create", json={"title": "a real task"}, headers=_CSRF
    )

    assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# Task and Event `description` — capped by the real request models
# ---------------------------------------------------------------------------

_EVENT_TIMES = {"event_date": "2099-01-05", "start_time": "09:00", "end_time": "10:00"}

#: domain → (create schema, update schema, the fields a create body must carry)
_DESCRIPTION_DOORS: dict[str, tuple[type[BaseModel], type[BaseModel], dict[str, str]]] = {
    "tasks": (TaskCreateRequest, TaskUpdateRequest, {"title": "a real task"}),
    "events": (EventCreateRequest, EventUpdateRequest, {"title": "a real event", **_EVENT_TIMES}),
}

_DESCRIPTION_CASES = [
    pytest.param(domain, "create", id=f"{domain}-create") for domain in _DESCRIPTION_DOORS
] + [pytest.param(domain, "update", id=f"{domain}-update") for domain in _DESCRIPTION_DOORS]


def _to_dict_entity(schema: BaseModel, uid: str, user_uid: str) -> dict[str, object]:
    """Stand in for the domain's registered converter."""
    return {"uid": uid, "user_uid": user_uid, **schema.model_dump(mode="json")}


def _post_description(
    monkeypatch: pytest.MonkeyPatch, domain: str, door: str, description: str
) -> tuple[int, str]:
    """POST one description through the real schemas; answer (status, body text)."""
    create_schema, update_schema, required = _DESCRIPTION_DOORS[domain]
    app, rt = fast_app(pico=False, default_hdrs=False)
    monkeypatch.setattr(crud_module, "require_authenticated_user", _fake_authenticated_user)

    service = MagicMock()
    service.create = AsyncMock(return_value=Result.ok({"uid": "entity_1"}))
    service.update_for_user = AsyncMock(return_value=Result.ok({"uid": "entity_1"}))
    service.verify_ownership = AsyncMock(return_value=Result.ok(True))

    CRUDRouteFactory(
        service=service,
        domain_name=domain,
        create_schema=create_schema,
        update_schema=update_schema,
        entity_converter=_to_dict_entity,
    ).register_routes(app, rt)

    if door == "create":
        path, body = f"/api/{domain}/create", {**required, "description": description}
    else:
        path, body = f"/api/{domain}/update?uid=entity_1", {"description": description}
    response = TestClient(app, cookies=_COOKIES).post(path, json=body, headers=_CSRF)
    return response.status_code, response.text


@pytest.mark.parametrize(("domain", "door"), _DESCRIPTION_CASES)
def test_an_over_length_description_is_400(
    monkeypatch: pytest.MonkeyPatch, domain: str, door: str
) -> None:
    """One character past the cap is the caller's error, named by field."""
    status, text = _post_description(monkeypatch, domain, door, "x" * 2001)

    assert status == 400, text
    payload = json.loads(text)
    assert payload["category"] == "validation"
    assert "description" in payload["message"]


@pytest.mark.parametrize(("domain", "door"), _DESCRIPTION_CASES)
def test_a_description_at_the_cap_reaches_the_service(
    monkeypatch: pytest.MonkeyPatch, domain: str, door: str
) -> None:
    status, text = _post_description(monkeypatch, domain, door, "x" * 2000)

    assert status == (201 if door == "create" else 200), text
