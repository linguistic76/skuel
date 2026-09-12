"""The generated page shells light the sidebar row the config names.

Events have no activity-sidebar row of their own — every event page lights
"Monthly" — so the shared factory's list and detail shells must take the row
from ``ActivityUIConfig.sidebar_active`` rather than the domain slug, or a
successful create would land on a detail page with no active row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import Div, fast_app
from starlette.testclient import TestClient

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from core.utils.result_simplified import Result
from ui.activities.filter_bar import FilterBarConfig


@dataclass(frozen=True)
class _Item:
    uid: str
    status: str


def _fake_authenticated_user(request: object) -> str:
    return "user_test"


def _keep_all(items: list[_Item], status: str) -> list[_Item]:
    return list(items)


def _list_component(filtered: list[_Item], connections_map: dict[str, Any]) -> Div:
    return Div(id="event-list")


def _stats_component(all_items: list[_Item]) -> Div:
    return Div()


def _detail_component(entity: _Item, connections: list[Any]) -> Div:
    return Div("detail")


def _client(
    monkeypatch: pytest.MonkeyPatch, *, sidebar_active: str | None
) -> tuple[TestClient, list[str]]:
    seen: list[str] = []

    def fake_sidebar_page(content: Any, **kwargs: Any) -> Any:
        seen.append(kwargs["active"])
        return content

    monkeypatch.setattr(
        "adapters.inbound.activity_ui_factory.require_authenticated_user",
        _fake_authenticated_user,
    )
    monkeypatch.setattr(
        "adapters.inbound.activity_ui_factory.render_activity_sidebar_page", fake_sidebar_page
    )
    app, rt = fast_app(pico=False, default_hdrs=False)
    backend = MagicMock()
    backend.fetch_entity_connections = AsyncMock(return_value={})

    async def get_all(user_uid: str) -> Result[list[_Item]]:
        return Result.ok([])

    async def get_one(uid: str) -> Result[_Item]:
        return Result.ok(_Item(uid=uid, status="active"))

    config = ActivityUIConfig(
        domain_name="events",
        domain_singular="event",
        page_title="Events",
        filter_params=(("status", "upcoming"),),
        get_all=get_all,
        get_one=get_one,
        backend=backend,
        filter_fn=_keep_all,
        connection_config=MagicMock(),
        filter_config=FilterBarConfig(
            fragment_url="/events/list-fragment", list_target_id="event-list", filters=[]
        ),
        list_component=_list_component,
        stats_component=_stats_component,
        detail_component=_detail_component,
        sidebar_active=sidebar_active,
    )
    create_activity_ui_routes(app, rt, config)
    return TestClient(app), seen


def test_shells_light_the_configured_row(monkeypatch: pytest.MonkeyPatch) -> None:
    client, seen = _client(monkeypatch, sidebar_active="monthly")
    client.get("/events")
    client.get("/events/detail?uid=event_1")
    client.get("/events/detail")  # the missing-uid banner is a shell too
    assert seen == ["monthly", "monthly", "monthly"]


def test_shells_default_to_the_domain_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    client, seen = _client(monkeypatch, sidebar_active=None)
    client.get("/events")
    client.get("/events/detail?uid=event_1")
    assert seen == ["events", "events"]
