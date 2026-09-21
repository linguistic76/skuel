"""The HTMX forms that post to CRUD-factory doors are answered — driven as they post.

The exercise editor (``ui/exercises/editor.py``), the exercise card's Delete
(``ui/exercises/cards.py``) and the teacher's New Group modal
(``adapters/inbound/teaching_ui.py``) each post a browser form encoding to a door
the CRUD factory registers (``/create``, ``/update?uid=``, ``/delete?uid=``). The
door reads the body by Content-Type (``parse_body``), so the form's fields reach
the service exactly as a JSON client's would. These tests post the encoding htmx
sends — multipart for a ``Form`` (FastHTML's default enctype), an empty url-encoded
body for a bare button — through the real ``DomainRouteConfig`` wiring, and read
what comes back: the status the button expects, the service call the form meant,
404 for a uid the caller does not own, 405 for the verb the door does not serve.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

import adapters.inbound.route_factories.crud_route_factory as crud_module
import adapters.inbound.route_factories.route_helpers as helpers_module
from adapters.inbound.boundary import install_malformed_json_guard
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.exercises_routes import EXERCISES_CONFIG
from adapters.inbound.groups_routes import GROUPS_CONFIG
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.models.enums import UserRole
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_teacher"
_EXERCISE_UID = "ex_abc123"


def _fake_auth(request: object) -> str:
    return _USER_UID


def _caller(role: UserRole) -> MagicMock:
    user = MagicMock()
    user.uid = _USER_UID
    user.role = role
    user.has_permission = role.has_permission
    return user


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    services: MagicMock


def _make_harness(monkeypatch: pytest.MonkeyPatch, config: DomainRouteConfig) -> _Harness:
    """The domain's routes on a bare app, every service a mock, the caller a TEACHER."""
    app, rt = fast_app(pico=False, default_hdrs=False)
    monkeypatch.setattr(crud_module, "require_authenticated_user", _fake_auth)
    monkeypatch.setattr(helpers_module, "require_authenticated_user", _fake_auth)
    monkeypatch.setattr("adapters.inbound.auth.roles.require_authenticated_user", _fake_auth)

    services = MagicMock()
    services.user.get_user = AsyncMock(return_value=Result.ok(_caller(UserRole.TEACHER)))
    primary = getattr(services, config.primary_service_attr)
    primary.create = AsyncMock(return_value=Result.ok({"uid": "created"}))
    primary.update_for_user = AsyncMock(return_value=Result.ok({"uid": _EXERCISE_UID}))
    primary.delete_for_user = AsyncMock(return_value=Result.ok(True))

    register_domain_routes(app, rt, services, config)
    install_malformed_json_guard(app)
    return _Harness(client=TestClient(app), services=services)


def _post_form(client: TestClient, path: str, fields: dict[str, str] | None = None):
    """A ``Form`` posts multipart; a bare button posts an empty url-encoded body."""
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    headers = {CSRF_HEADER_NAME: token, "HX-Request": "true"}
    if fields:
        return client.post(path, files={k: (None, v) for k, v in fields.items()}, headers=headers)
    return client.post(
        path,
        content=b"",
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    )


# The editor's fields, as its inputs are named.
_EDITOR_FIELDS = {
    "name": "Daily Reflection",
    "instructions": "Ask me one clarifying question.",
    "model": "claude-sonnet-4-6",
    "context_notes": "Be gentle\nBe curious",
    "domain": "",
}


class TestExerciseEditor:
    def test_create_form_reaches_the_service_as_an_exercise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch, EXERCISES_CONFIG)

        response = _post_form(harness.client, "/api/exercises/create", _EDITOR_FIELDS)

        assert response.status_code == 201, response.text
        (entity,), _kwargs = harness.services.exercises.create.await_args
        assert entity.title == "Daily Reflection"
        assert entity.instructions == "Ask me one clarifying question."
        assert tuple(entity.context_notes) == ("Be gentle", "Be curious")
        assert entity.owner_uid == _USER_UID

    def test_edit_form_renames_through_title(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The request speaks ``name``; the entity stores ``title``. The patch the
        service receives carries the field the graph has."""
        harness = _make_harness(monkeypatch, EXERCISES_CONFIG)

        response = _post_form(
            harness.client, f"/api/exercises/update?uid={_EXERCISE_UID}", _EDITOR_FIELDS
        )

        assert response.status_code == 200, response.text
        (uid, changes, user_uid), _kwargs = harness.services.exercises.update_for_user.await_args
        assert (uid, user_uid) == (_EXERCISE_UID, _USER_UID)
        patch = changes.to_changes()
        assert patch["title"] == "Daily Reflection"
        assert "name" not in patch
        assert patch["context_notes"] == ["Be gentle", "Be curious"]
        assert patch["domain"] is None  # "None" in the select clears the domain

    def test_delete_button_posts_and_is_answered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, EXERCISES_CONFIG)

        response = _post_form(harness.client, f"/api/exercises/delete?uid={_EXERCISE_UID}")

        assert response.status_code == 200, response.text
        harness.services.exercises.delete_for_user.assert_awaited_once_with(
            _EXERCISE_UID, _USER_UID, cascade=True
        )

    def test_the_delete_door_is_a_post_not_a_delete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Why the hx_* guard holds a target to its verb: the same path, the other verb."""
        harness = _make_harness(monkeypatch, EXERCISES_CONFIG)

        response = harness.client.delete(f"/api/exercises/delete?uid={_EXERCISE_UID}")

        assert response.status_code == 405
        harness.services.exercises.delete_for_user.assert_not_awaited()

    def test_a_foreign_uid_still_answers_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, EXERCISES_CONFIG)
        harness.services.exercises.update_for_user = AsyncMock(
            return_value=Result.fail(Errors.not_found("Exercise", "ex_theirs"))
        )

        response = _post_form(harness.client, "/api/exercises/update?uid=ex_theirs", _EDITOR_FIELDS)

        assert response.status_code == 404

    def test_a_rejected_form_is_400_naming_the_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, EXERCISES_CONFIG)

        response = _post_form(
            harness.client, "/api/exercises/create", {**_EDITOR_FIELDS, "domain": "work"}
        )

        assert response.status_code == 400
        assert "domain" in response.json()["message"]
        harness.services.exercises.create.assert_not_awaited()


class TestNewGroupModal:
    def test_form_fields_reach_the_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Optional fields left blank arrive as ``None``; ``max_members`` is coerced."""
        harness = _make_harness(monkeypatch, GROUPS_CONFIG)

        response = _post_form(
            harness.client,
            "/api/groups/create",
            {"name": "Physics 101", "description": "", "max_members": "30"},
        )

        assert response.status_code == 201, response.text
        (entity,), _kwargs = harness.services.groups.create.await_args
        assert entity.name == "Physics 101"
        assert entity.description is None
        assert entity.max_members == 30

    def test_json_clients_are_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, GROUPS_CONFIG)
        token = mint_token()
        harness.client.cookies.set(CSRF_COOKIE_NAME, token)

        response = harness.client.post(
            "/api/groups/create", json={"name": "Physics 101"}, headers={CSRF_HEADER_NAME: token}
        )

        assert response.status_code == 201, response.text
