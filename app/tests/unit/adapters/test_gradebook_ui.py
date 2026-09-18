"""The GradeBook page renders under the Tasks+ sidebar — it has no sidebar of its own.

Reached from the Tasks+ sidebar's GradeBook row, the page keeps that sidebar
(row lit) with its content to the right. The on-demand activity report's door
is the page header's action, not a sidebar row.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastcore.xml import to_xml  # type: ignore[import-untyped]

from adapters.inbound.user_entry_ui import create_user_entry_ui_routes
from core.utils.result_simplified import Result
from ui.activities.nav import ACTIVITY_SIDEBAR_TITLE


class _RouteRegistry:
    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], object] = {}

    def __call__(self, path: str, methods: list[str] | None = None):
        method = (methods[0] if methods else "GET").upper()

        def decorator(func):
            self.handlers[(path, method)] = func
            return func

        return decorator

    def get(self, path: str, method: str = "GET"):
        return self.handlers[(path, method.upper())]


def _make_request(user_uid: str = "user_gradebook") -> SimpleNamespace:
    request = SimpleNamespace()
    request.session = {"user_uid": user_uid}
    request.url = SimpleNamespace(path="/gradebook")
    request.method = "GET"
    request.cookies = {}
    request.headers = {}
    request.query_params = {}
    return request


@pytest.fixture
def shell_as_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render the page shell as a dict so the sidebar and title are inspectable."""

    def fake_base_page(**kwargs):
        return {"__base_page__": True, **kwargs}

    import ui.patterns.sidebar as sidebar_module

    monkeypatch.setattr(sidebar_module, "BasePage", fake_base_page)


@pytest.fixture
def gradebook_handler():
    registry = _RouteRegistry()
    orchestrator = SimpleNamespace(
        get_student_exchange_summaries=AsyncMock(
            return_value=Result.ok({"exercises": [], "other_feedback": []})
        ),
        get_activity_report_history=AsyncMock(return_value=Result.ok([])),
    )
    create_user_entry_ui_routes(None, registry, SimpleNamespace(), orchestrator=orchestrator)
    return registry.get("/gradebook")


def _anchors_to(html: str, href: str) -> list[str]:
    return re.findall(rf'<a[^>]*href="{re.escape(href)}"[^>]*>', html)


@pytest.mark.asyncio
async def test_the_gradebook_page_renders_inside_the_tasks_plus_sidebar(
    gradebook_handler, shell_as_dict
) -> None:
    page = await gradebook_handler(_make_request())
    html = to_xml(page["content"])

    assert page["__base_page__"] is True
    assert f'aria-label="{ACTIVITY_SIDEBAR_TITLE} sidebar"' in html
    assert 'aria-label="GradeBook sidebar"' not in html
    # The GradeBook row is the lit one.
    assert any("bg-accent font-semibold" in tag for tag in _anchors_to(html, "/gradebook"))
    assert page["title"] == "GradeBook"


@pytest.mark.asyncio
async def test_the_activity_report_request_is_the_header_action_not_a_sidebar_row(
    gradebook_handler, shell_as_dict
) -> None:
    page = await gradebook_handler(_make_request())
    html = to_xml(page["content"])

    assert "Request activity report" in html
    assert len(_anchors_to(html, "/submit-activity-report")) == 1
    # No sidebar item (desktop <li> or mobile tab) points at the request form.
    assert not re.search(r'<li[^>]*>\s*<a[^>]*href="/submit-activity-report"', html)
    assert not re.search(r'<a[^>]*href="/submit-activity-report"[^>]*role="tab"', html)
