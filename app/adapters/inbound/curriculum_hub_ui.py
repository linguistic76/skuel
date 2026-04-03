"""Curriculum Hub UI Routes
==========================

UI for curriculum browser sub-pages and legacy redirects.

Routes:
- GET /curriculum — 301 redirect to /profile (hub shelved)
- GET /lessons — 301 redirect to /explore (merged)
- GET /path-steps — 301 redirect to /explore (merged)
- GET /learning-paths — Learning Paths browser
"""

from typing import Any

from fasthtml.common import Div
from starlette.responses import RedirectResponse

from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator, RouteList
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.curriculum_hub")

# Detail route patterns per domain slug
_DETAIL_ROUTES: dict[str, str] = {
    "path-steps": "/explore/ps/{uid}",
    "learning-paths": "/lp/{uid}",
}


def create_curriculum_hub_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Any,
) -> RouteList:
    """Register curriculum hub UI routes."""

    @rt("/curriculum")
    async def curriculum_landing(request: Request) -> RedirectResponse:
        """Curriculum hub shelved — redirect to Profile (THE main hub)."""
        return RedirectResponse(url="/profile", status_code=301)

    @rt("/lessons")
    async def lessons_redirect(request: Request) -> RedirectResponse:
        """Lesson merged into PathStep, now merged into /explore."""
        return RedirectResponse(url="/explore", status_code=301)

    @rt("/path-steps")
    async def path_steps_browser(request: Request) -> RedirectResponse:
        """PathStep browser merged into /explore."""
        return RedirectResponse(url="/explore", status_code=301)

    @rt("/learning-paths")
    async def learning_paths_browser(request: Request) -> Any:
        """Learning Paths browser. Public: shared curriculum content."""
        lp_service = services.lp
        items: list[Any] = []
        if lp_service:
            result = await lp_service.core.list(limit=50)
            if not result.is_error:
                items = result.value if isinstance(result.value, list) else result.value[0]

        content = Div(
            PageHeader("Learning Paths", subtitle="Ordered sequences of path step collections"),
            _entity_list(items, "learning-paths", "No learning paths found"),
            id="main-content",
        )
        return await BasePage(
            content=content,
            title="Learning Paths",
            request=request,
            active_page="curriculum",
        )

    return []  # Routes registered via @rt() decorators


def _entity_list(items: list[Any], domain_slug: str, empty_msg: str) -> Div:
    """Render a list of curriculum entities using CardGenerator."""
    if not items:
        return EmptyState(title=empty_msg)

    detail_pattern = _DETAIL_ROUTES.get(domain_slug)

    rows = []
    for item in items:
        title = getattr(item, "title", "Untitled")
        description = getattr(item, "description", "") or ""
        uid = getattr(item, "uid", "")

        href = detail_pattern.format(uid=uid) if detail_pattern and uid else None

        rows.append(
            CardGenerator.from_dataclass(
                {"title": title, "description": description},
                display_fields=["description"],
                show_labels=False,
                metadata=[uid] if uid else None,
                title_href=href,
            )
        )
    return Div(*rows, cls="space-y-3")
