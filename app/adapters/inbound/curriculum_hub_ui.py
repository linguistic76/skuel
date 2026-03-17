"""Curriculum Hub UI Routes
==========================

UI for the curriculum landing page and browser sub-pages.

Routes:
- GET /curriculum — Landing page (4-card grid, no sidebar)
- GET /lessons — Lesson browser with Curriculum sidebar
- GET /learning-steps — Learning Steps browser with Curriculum sidebar
- GET /learning-paths — Learning Paths browser with Curriculum sidebar
"""

from typing import Any

from fasthtml.common import H2, Div, P, Span

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from core.utils.logging import get_logger
from ui.curriculum.landing import CurriculumLandingView
from ui.curriculum.layout import create_curriculum_page
from ui.layouts.base_page import BasePage
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.curriculum_hub")


def create_curriculum_hub_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Any,
) -> RouteList:
    """Register curriculum hub UI routes."""

    @rt("/curriculum")
    async def curriculum_landing(request) -> Any:
        """Curriculum hub landing page — 4-card grid, no sidebar."""
        require_authenticated_user(request)
        return await BasePage(
            CurriculumLandingView(),
            title="Curriculum",
            request=request,
            active_page="curriculum",
        )

    @rt("/lessons")
    async def lessons_browser(request) -> Any:
        """Lesson browser with Curriculum sidebar."""
        require_authenticated_user(request)

        lesson_service = services.lesson
        items: list[Any] = []
        if lesson_service:
            result = await lesson_service.core.list(limit=50)
            if not result.is_error:
                items = result.value if isinstance(result.value, list) else result.value[0]

        content = Div(
            PageHeader("Lessons", subtitle="Units for learning that compose atomic knowledge"),
            _entity_list(items, "lessons", "No lessons found."),
            id="main-content",
        )
        return await create_curriculum_page(
            content=content,
            active_section="lessons",
            request=request,
            title="Lessons - Curriculum",
        )

    @rt("/learning-steps")
    async def learning_steps_browser(request) -> Any:
        """Learning Steps browser with Curriculum sidebar."""
        require_authenticated_user(request)

        ls_service = services.ls
        items: list[Any] = []
        if ls_service:
            result = await ls_service.core.list(limit=50)
            if not result.is_error:
                items = result.value if isinstance(result.value, list) else result.value[0]

        content = Div(
            PageHeader("Learning Steps", subtitle="Collections of lessons grouped by theme"),
            _entity_list(items, "learning-steps", "No learning steps found."),
            id="main-content",
        )
        return await create_curriculum_page(
            content=content,
            active_section="learning-steps",
            request=request,
            title="Learning Steps - Curriculum",
        )

    @rt("/learning-paths")
    async def learning_paths_browser(request) -> Any:
        """Learning Paths browser with Curriculum sidebar."""
        require_authenticated_user(request)

        lp_service = services.lp
        items: list[Any] = []
        if lp_service:
            result = await lp_service.core.list(limit=50)
            if not result.is_error:
                items = result.value if isinstance(result.value, list) else result.value[0]

        content = Div(
            PageHeader("Learning Paths", subtitle="Ordered sequences of learning step collections"),
            _entity_list(items, "learning-paths", "No learning paths found."),
            id="main-content",
        )
        return await create_curriculum_page(
            content=content,
            active_section="learning-paths",
            request=request,
            title="Learning Paths - Curriculum",
        )

    return []  # Routes registered via @rt() decorators


def _entity_list(items: list[Any], domain_slug: str, empty_msg: str) -> Div:
    """Render a simple list of entities with title and description."""
    if not items:
        return Div(
            P(empty_msg, cls="text-muted-foreground text-center py-8"),
        )

    rows = []
    for item in items:
        title = getattr(item, "title", "Untitled")
        description = getattr(item, "description", "") or ""
        uid = getattr(item, "uid", "")

        rows.append(
            Div(
                Div(
                    H2(title, cls="text-base font-medium text-foreground"),
                    P(
                        description[:120] + ("..." if len(description) > 120 else ""),
                        cls="text-sm text-muted-foreground mt-0.5",
                    )
                    if description
                    else None,
                    cls="flex-1 min-w-0",
                ),
                Span(uid, cls="text-xs text-muted-foreground/60 font-mono shrink-0"),
                cls="flex items-start justify-between gap-4 py-3 px-4 hover:bg-muted/50 rounded-lg",
            )
        )

    return Div(*rows, cls="divide-y divide-border")
