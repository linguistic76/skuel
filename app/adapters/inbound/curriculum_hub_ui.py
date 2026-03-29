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

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from core.utils.logging import get_logger
from ui.curriculum.landing import CurriculumLandingView
from ui.curriculum.layout import create_curriculum_page
from ui.layouts.base_page import BasePage
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.stats_grid import StatItem

logger = get_logger("skuel.routes.curriculum_hub")

# Detail route patterns per domain slug
_DETAIL_ROUTES: dict[str, str] = {
    "lessons": "/lesson/{uid}/details",
    "learning-steps": "/ls/{uid}",
    "learning-paths": "/lp/{uid}",
}


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

        # Fetch counts for stats grid
        stats: list[StatItem] = []
        for label, service_attr in [
            ("Lessons", "lesson"),
            ("Learning Steps", "ls"),
            ("Learning Paths", "lp"),
            ("Exercises", "exercises"),
        ]:
            svc = getattr(services, service_attr, None)
            if svc:
                # Facades have .core sub-service; flat BaseService services don't
                counter = getattr(svc, "core", svc)
                count_result = await counter.count()
                count = count_result.value if not count_result.is_error else 0
            else:
                count = 0
            stats.append(StatItem(label=label, value=count))

        return await BasePage(
            CurriculumLandingView(stats=stats),
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
            _entity_list(items, "lessons", "No lessons found"),
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
            _entity_list(items, "learning-steps", "No learning steps found"),
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
            _entity_list(items, "learning-paths", "No learning paths found"),
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
