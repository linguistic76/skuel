"""Regression tests for filter-param forwarding in the Activity UI factory.

Pins the two halves of the shell-first query-param fix
(``adapters/inbound/activity_ui_factory.py``):

1. Shell forwarding: ``GET /{domain}?status=X`` must embed the filter params
   in the content-fragment placeholder URL. Before the fix the placeholder
   was hardcoded to ``/{domain}/content``, so stat-card links, bookmarks,
   and refreshes of a filtered view silently rendered the default filter.
   Only params declared in ``config.filter_params`` are forwarded (whitelist).
2. URL sync: ``GET /{domain}/list-fragment`` (the filter bar's endpoint)
   must answer with an ``HX-Push-Url`` header pointing at the canonical
   page URL, omitting default-valued params.

Harness: a real ``fast_app`` + Starlette TestClient — no Neo4j, no server.
Auth and the sidebar-page renderer are monkeypatched at the factory's import
site; the sidebar stub returns the content unchanged so assertions can see
the placeholder markup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import Div, fast_app
from starlette.testclient import TestClient

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from core.utils.result_simplified import Result
from ui.activities.filter_bar import FilterBarConfig, FilterSelect

_USER_UID = "user_test"


@dataclass(frozen=True)
class _Item:
    uid: str
    status: str


_ITEMS = [_Item(uid="task_a", status="active"), _Item(uid="task_b", status="completed")]


def _fake_require_authenticated_user(request: object) -> str:
    return _USER_UID


async def _fake_sidebar_page(content: Any, **kwargs: Any) -> Any:
    return content


def _filter_items(items: list[_Item], status: str, sort_by: str) -> list[_Item]:
    if status == "all":
        return list(items)
    return [i for i in items if i.status == status]


@pytest.fixture(autouse=True)
def _patch_factory_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "adapters.inbound.activity_ui_factory.require_authenticated_user",
        _fake_require_authenticated_user,
    )
    monkeypatch.setattr(
        "adapters.inbound.activity_ui_factory.render_activity_sidebar_page",
        _fake_sidebar_page,
    )


def _client() -> TestClient:
    app, rt = fast_app(pico=False, default_hdrs=False)

    backend = MagicMock()
    backend.fetch_entity_connections = AsyncMock(return_value={})

    async def get_all(user_uid: str) -> Result[list[_Item]]:
        return Result.ok(list(_ITEMS))

    async def get_one(uid: str) -> Result[_Item]:
        return Result.ok(_ITEMS[0])

    def list_component(filtered: list[_Item], connections_map: dict[str, Any]) -> Div:
        return Div(*[Div(i.uid) for i in filtered], id="task-list")

    def stats_component(all_items: list[_Item]) -> Div:
        return Div(f"total:{len(all_items)}")

    def detail_component(entity: _Item, connections: list[Any]) -> Div:
        return Div("detail")

    config = ActivityUIConfig(
        domain_name="tasks",
        domain_singular="task",
        page_title="Tasks",
        filter_params=(("status", "active"), ("sort_by", "priority")),
        get_all=get_all,
        get_one=get_one,
        backend=backend,
        filter_fn=_filter_items,
        connection_config=MagicMock(),
        filter_config=FilterBarConfig(
            fragment_url="/tasks/list-fragment",
            list_target_id="task-list",
            filters=[
                FilterSelect(
                    name="status",
                    label="Status",
                    options=[("Active", "active"), ("Completed", "completed"), ("All", "all")],
                    default="active",
                )
            ],
            sort_options=[("Priority", "priority"), ("Title", "title")],
            sort_default="priority",
        ),
        list_component=list_component,
        stats_component=stats_component,
        detail_component=detail_component,
    )
    create_activity_ui_routes(app, rt, config)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Shell forwards filter params into the placeholder URL
# ---------------------------------------------------------------------------


def test_shell_forwards_filter_params_to_fragment_url() -> None:
    client = _client()
    resp = client.get("/tasks?status=completed&sort_by=title")
    assert resp.status_code == 200
    assert 'hx-get="/tasks/content?status=completed&amp;sort_by=title"' in resp.text


def test_shell_without_params_uses_bare_fragment_url() -> None:
    client = _client()
    resp = client.get("/tasks")
    assert resp.status_code == 200
    assert 'hx-get="/tasks/content"' in resp.text


def test_shell_forwarding_is_whitelisted() -> None:
    client = _client()
    resp = client.get("/tasks?status=all&evil=payload")
    assert resp.status_code == 200
    # Only declared filter_params reach the fragment URL; unknown params are
    # dropped (the page head may still echo the raw request URL elsewhere).
    fragment_urls = re.findall(r'hx-get="(/tasks/content[^"]*)"', resp.text)
    assert fragment_urls == ["/tasks/content?status=all"]


def test_content_fragment_applies_forwarded_status() -> None:
    client = _client()
    resp = client.get("/tasks/content?status=completed")
    assert resp.status_code == 200
    assert "task_b" in resp.text
    assert "task_a" not in resp.text


# ---------------------------------------------------------------------------
# 2. list-fragment pushes the canonical page URL
# ---------------------------------------------------------------------------


def test_list_fragment_pushes_canonical_page_url() -> None:
    client = _client()
    resp = client.get("/tasks/list-fragment?status=completed&sort_by=priority")
    assert resp.status_code == 200
    # sort_by=priority is the default — omitted from the canonical URL.
    assert resp.headers["hx-push-url"] == "/tasks?status=completed"


def test_list_fragment_with_defaults_pushes_bare_page_url() -> None:
    client = _client()
    resp = client.get("/tasks/list-fragment")
    assert resp.status_code == 200
    assert resp.headers["hx-push-url"] == "/tasks"
