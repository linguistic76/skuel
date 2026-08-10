"""Learning Paths UI Routes
===========================

Standalone browser for LearningPath entities — the top of the curriculum hierarchy.

Routes:
- GET /learning-paths — Learning Paths browser
"""

from typing import Any

from fasthtml.common import Div

from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.learning_paths")


def create_learning_paths_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Any,
) -> None:
    """Register learning paths UI routes."""

    @rt("/learning-paths")
    def learning_paths_browser(request: Request) -> Any:
        """Learning Paths browser — shell renders immediately, content loads via HTMX."""
        content = Div(
            PageHeader("Learning Paths", subtitle="Ordered sequences of path step collections"),
            content_loading_placeholder("/learning-paths/content", "learning-paths-content"),
            id="main-content",
        )
        return BasePage(
            content=content,
            title="Learning Paths",
            request=request,
            active_page="learning-paths",
        )

    @rt("/learning-paths/content")
    async def learning_paths_content_fragment(request: Request) -> Any:
        """HTMX fragment: learning paths list."""
        lp_service = services.lp
        items: list[Any] = []
        if lp_service:
            # The LP catalogue method, not generic CRUD ``list()``: this is a
            # public listing, and only the domain method composes the publication
            # gate — generic list() showed draft-marked paths (Codex #1006).
            result = await lp_service.core.list_all_paths(limit=50)
            if not result.is_error:
                items = result.value
        return Div(_entity_list(items), id="learning-paths-content")


def _entity_list(items: list[Any]) -> Div:
    """Render a list of learning path entities using CardGenerator."""
    if not items:
        return EmptyState(title="No learning paths found")

    rows = []
    for item in items:
        title = getattr(item, "title", "Untitled")
        description = getattr(item, "description", "") or ""
        uid = getattr(item, "uid", "")

        href = f"/lp/{uid}" if uid else None

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
