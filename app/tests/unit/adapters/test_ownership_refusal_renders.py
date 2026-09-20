"""The UI ownership refusal renders AND carries the 404 (OWNERSHIP_VERIFICATION § UI Routes).

A user-owned read that fails ownership answers 404 — to the client, the cache and the
monitor — whatever the body says. These pins hold the route layer to that on the three
shapes a learner can reach:

- the Activity edit pages (six domains, GET and POST): a foreign uid gets the sidebar page
  with the not-found banner, at 404, with the refusal header;
- the top-level detail fragment the shell loads: the banner in its slot, at 404, with the
  header ``skuel.js`` swaps on, and no ``<html>`` wrapper on an HTMX request;
- the field-update card POST and the hierarchy children fragment: the same rendered 404;
- a nested fragment (``/tasks/subtasks``): a bare 404 — nothing rendered, no header.

Harness: real ``fast_app`` + TestClient + the real registrars with mocked services; auth
is faked at the name each module resolves at call time.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.choices_ui import create_choices_ui_routes
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.events_ui import create_events_ui_routes
from adapters.inbound.goals_ui import create_goals_ui_routes
from adapters.inbound.habits_ui import create_habits_ui_routes
from adapters.inbound.principles_ui import create_principles_ui_routes
from adapters.inbound.route_factories import (
    ActivityHierarchyApiConfig,
    create_activity_hierarchy_api_routes,
)
from adapters.inbound.route_factories.route_helpers import REFUSAL_HEADER, REFUSAL_RENDERED
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.utils.result_simplified import Errors, Result

_USER = "user_owner"
_FOREIGN_UID = "task_not_mine"

# Each registrar is (app, rt, service, connection_fetch_backend, ...) — the six differ in
# their optional tail (extra services / a verifier), so the map is typed at the four
# positionals they share.
_REGISTRARS: dict[str, Callable[..., Any]] = {  # boundary: six registrar signatures, one call shape
    "tasks": create_tasks_ui_routes,
    "goals": create_goals_ui_routes,
    "habits": create_habits_ui_routes,
    "events": create_events_ui_routes,
    "choices": create_choices_ui_routes,
    "principles": create_principles_ui_routes,
}
_SINGULAR = {
    "tasks": "Task",
    "goals": "Goal",
    "habits": "Habit",
    "events": "Event",
    "choices": "Choice",
    "principles": "Principle",
}


def _fake_auth(request: object) -> str:
    return _USER


def _refusing_service() -> MagicMock:
    """A facade whose verify_ownership answers NOT_FOUND — the same for foreign and missing."""
    service = MagicMock()
    service.verify_ownership = AsyncMock(
        return_value=Result.fail(Errors.not_found(resource="entity", identifier=_FOREIGN_UID))
    )
    return service


def _backend() -> MagicMock:
    backend = MagicMock()
    backend.fetch_entity_connections = AsyncMock(return_value={})
    backend.fetch_source_pathstep = AsyncMock(return_value=None)
    return backend


def _client_for(domain: str, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, MagicMock]:
    monkeypatch.setattr(f"adapters.inbound.{domain}_ui.require_authenticated_user", _fake_auth)
    monkeypatch.setattr(
        "adapters.inbound.activity_ui_factory.require_authenticated_user", _fake_auth
    )
    app, rt = fast_app(pico=False, default_hdrs=False)
    service = _refusing_service()
    _REGISTRARS[domain](app, rt, service, _backend())
    return TestClient(app), service


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


# ============================================================================
# Edit pages — the sidebar page with the banner, at 404
# ============================================================================


@pytest.mark.parametrize("domain", sorted(_REGISTRARS))
def test_edit_page_get_refuses_a_foreign_uid_with_chrome_and_404(
    domain: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, service = _client_for(domain, monkeypatch)

    response = client.get(f"/{domain}/edit?uid={_FOREIGN_UID}")

    assert response.status_code == 404
    assert response.headers[REFUSAL_HEADER.lower()] == REFUSAL_RENDERED
    body = response.text
    assert f"{_SINGULAR[domain]} not found" in body
    assert "<nav" in body  # the learner keeps the page chrome
    service.verify_ownership.assert_awaited_once_with(_FOREIGN_UID, _USER)


@pytest.mark.parametrize("domain", sorted(_REGISTRARS))
def test_edit_page_post_refuses_before_reading_the_form(
    domain: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, service = _client_for(domain, monkeypatch)

    response = client.post(
        f"/{domain}/edit?uid={_FOREIGN_UID}",
        data={"title": "attacker payload"},
        headers=_csrf_headers(client),
    )

    assert response.status_code == 404
    assert f"{_SINGULAR[domain]} not found" in response.text
    assert "<nav" in response.text
    service.verify_ownership.assert_awaited_once_with(_FOREIGN_UID, _USER)


# ============================================================================
# The top-level fragment a detail shell loads — banner in the slot, at 404
# ============================================================================


def test_detail_content_fragment_refuses_with_the_banner_at_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service = _client_for("tasks", monkeypatch)

    response = client.get(
        f"/tasks/detail/content?uid={_FOREIGN_UID}", headers={"HX-Request": "true"}
    )

    assert response.status_code == 404
    assert response.headers[REFUSAL_HEADER.lower()] == REFUSAL_RENDERED
    assert "Task not found" in response.text
    assert 'id="task-detail-content"' in response.text  # the slot HTMX swaps outerHTML on
    assert "<html" not in response.text  # a fragment, not a page
    service.verify_ownership.assert_awaited_once_with(_FOREIGN_UID, _USER)


def test_detail_content_fragment_missing_uid_is_a_rendered_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service = _client_for("tasks", monkeypatch)

    response = client.get("/tasks/detail/content", headers={"HX-Request": "true"})

    assert response.status_code == 404
    assert "Missing task UID" in response.text
    service.verify_ownership.assert_not_awaited()


# ============================================================================
# A nested fragment — bare 404, nothing rendered, no header
# ============================================================================


def test_subtasks_fragment_foreign_uid_is_a_bare_404(monkeypatch: pytest.MonkeyPatch) -> None:
    client, service = _client_for("tasks", monkeypatch)
    service.get_subtasks = AsyncMock()

    response = client.get(f"/tasks/subtasks?uid={_FOREIGN_UID}")

    assert response.status_code == 404
    assert REFUSAL_HEADER.lower() not in response.headers
    assert "<" not in response.text  # no body to swap
    service.get_subtasks.assert_not_awaited()


# ============================================================================
# The hierarchy children fragment — the tree row's refusal, at 404
# ============================================================================


def test_children_fragment_refuses_at_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "adapters.inbound.route_factories.hierarchy_api_factory.require_authenticated_user",
        _fake_auth,
    )
    app, rt = fast_app(pico=False, default_hdrs=False)
    service = _refusing_service()
    get_children = AsyncMock(return_value=Result.ok([]))
    create_activity_hierarchy_api_routes(
        rt,
        ActivityHierarchyApiConfig(
            domain_name="tasks",
            singular="task",
            service=service,
            get_children=get_children,
            get_parent=AsyncMock(return_value=Result.ok(None)),
            get_hierarchy=AsyncMock(return_value=Result.ok({})),
            add_child_relationship=AsyncMock(return_value=Result.ok(True)),
            remove_child_relationship=AsyncMock(return_value=Result.ok(True)),
        ),
    )
    client = TestClient(app)

    response = client.get(f"/api/tasks/{_FOREIGN_UID}/children", headers={"HX-Request": "true"})

    assert response.status_code == 404
    assert response.headers[REFUSAL_HEADER.lower()] == REFUSAL_RENDERED
    assert "Not found" in response.text
    get_children.assert_not_awaited()
