"""``GET /api/sidebar/badges`` emits exactly ``ACTIVITY_SIDEBAR_ITEMS ∩ DOMAIN_STATS_CONFIG``.

Every fragment the handler returns is an OOB swap into a ``sidebar-badge-{slug}``
slot the Tasks+ sidebar rendered — one per domain row that has a stats config.
A config without a row would be a fragment that targets nothing; a row without
a config gets no badge. The two sides are pinned against each other here so
neither drifts without this test saying so.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import Div, fast_app, to_xml
from starlette.testclient import TestClient

import adapters.inbound.user_profile_ui as profile_module
from adapters.inbound.user_profile_ui import setup_user_profile_routes
from core.services.user.unified_user_context import RichUserContext
from core.utils.result_simplified import Result
from ui.activities.nav import ACTIVITY_SIDEBAR_ITEMS, render_activity_sidebar_page
from ui.profile.domain_stats_config import DOMAIN_STATS_CONFIG

ROW_SLUGS = {item.slug for item in ACTIVITY_SIDEBAR_ITEMS}
BADGED_SLUGS = ROW_SLUGS & set(DOMAIN_STATS_CONFIG)


def _fake_authenticated_user(request: object) -> str:
    return "user_test"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(profile_module, "require_authenticated_user", _fake_authenticated_user)
    services = MagicMock()
    services.user.get_rich_unified_context = AsyncMock(
        return_value=Result.ok(RichUserContext(user_uid="user_test", username="test"))
    )
    app, rt = fast_app(pico=False, default_hdrs=False)
    setup_user_profile_routes(rt, services)
    return TestClient(app)


HX = {"HX-Request": "true"}


def _emitted_slugs(html: str) -> list[str]:
    """The slug of every OOB badge span in the fragment."""
    spans = re.findall(r"<span [^>]*>", html)
    return [
        match.group(1)
        for span in spans
        if 'hx-swap-oob="true"' in span
        and (match := re.search(r'id="sidebar-badge-([a-z-]+)"', span)) is not None
    ]


def test_every_configured_domain_has_a_tasks_plus_row() -> None:
    """A stats config with no row would be a fragment that no page swaps in."""
    assert set(DOMAIN_STATS_CONFIG) <= ROW_SLUGS


def test_the_handler_emits_one_fragment_per_badged_row_and_nothing_else(
    client: TestClient,
) -> None:
    response = client.get("/api/sidebar/badges", headers=HX)

    assert response.status_code == 200
    emitted = _emitted_slugs(response.text)
    assert len(emitted) == len(set(emitted))
    assert set(emitted) == BADGED_SLUGS
    assert set(emitted) == set(DOMAIN_STATS_CONFIG)  # the six activity domains, Events included


def test_every_fragment_lands_in_a_slot_the_tasks_plus_sidebar_rendered(
    client: TestClient,
) -> None:
    page = to_xml(render_activity_sidebar_page(Div("x"), active="tasks"))
    emitted = _emitted_slugs(client.get("/api/sidebar/badges", headers=HX).text)

    for slug in emitted:
        assert page.count(f'id="sidebar-badge-{slug}"') == 1, slug


def test_a_failed_context_read_degrades_to_an_empty_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(profile_module, "require_authenticated_user", _fake_authenticated_user)
    services = MagicMock()
    services.user.get_rich_unified_context = AsyncMock(return_value=Result.fail("down"))
    app, rt = fast_app(pico=False, default_hdrs=False)
    setup_user_profile_routes(rt, services)
    response = TestClient(app).get("/api/sidebar/badges", headers=HX)

    assert response.status_code == 200
    assert _emitted_slugs(response.text) == []
