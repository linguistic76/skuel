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
    (button,) = _anchors_to(html, "/submit-activity-report")
    # The header row wraps the action under the title when it does not fit,
    # so the button never has to hold its line: a nowrap here is what pushed
    # the page past a 320px viewport.
    assert "whitespace-nowrap" not in button
    # No sidebar item points at the request form — the desktop sidebar and the
    # section nav are both lists, so one shape covers both rows.
    assert not re.search(r'<li[^>]*>\s*<a[^>]*href="/submit-activity-report"', html)
