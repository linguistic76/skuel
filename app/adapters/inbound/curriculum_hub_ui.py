"""Curriculum Hub UI Routes
==========================

UI for curriculum browser sub-pages.

Routes:
- GET /curriculum — 301 redirect to /profile (shelved: landing page deprecated)
- GET /lessons — Lesson browser
- GET /learning-steps — Learning Steps browser
- GET /learning-paths — Learning Paths browser
"""

from typing import Any

from fasthtml.common import Div
from starlette.responses import RedirectResponse

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader

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
    async def curriculum_landing(request: Any) -> RedirectResponse:
        """Curriculum hub shelved — redirect to Profile (THE main hub)."""
        return RedirectResponse(url="/profile", status_code=301)

    @rt("/lessons")
    async def lessons_browser(request) -> Any:
        """Lesson browser."""
        user_uid = require_authenticated_user(request)

        lesson_service = services.lesson
        items: list[Any] = []
        learning_states: dict[str, str] = {}
        if lesson_service:
            result = await lesson_service.core.list(limit=50)
            if not result.is_error:
                items = result.value if isinstance(result.value, list) else result.value[0]

            # Fetch learning states for all lessons
            if items:
                uids = [getattr(item, "uid", "") for item in items if getattr(item, "uid", "")]
                states_result = await lesson_service.mastery.get_learning_states_batch(user_uid, uids)
                if states_result.is_ok:
                    learning_states = {k: v.value for k, v in states_result.value.items()}

        content = Div(
            PageHeader("Lessons", subtitle="Units for learning that compose atomic knowledge"),
            _lesson_list(items, learning_states),
            id="main-content",
        )
        return await BasePage(
            content=content,
            title="Lessons",
            request=request,
            active_page="curriculum",
        )

    @rt("/learning-steps")
    async def learning_steps_browser(request) -> Any:
        """Learning Steps browser."""
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
        return await BasePage(
            content=content,
            title="Learning Steps",
            request=request,
            active_page="curriculum",
        )

    @rt("/learning-paths")
    async def learning_paths_browser(request) -> Any:
        """Learning Paths browser."""
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
        return await BasePage(
            content=content,
            title="Learning Paths",
            request=request,
            active_page="curriculum",
        )

    return []  # Routes registered via @rt() decorators


def _enrollment_button(uid: str, state: str) -> Any:
    """Render enrollment button based on learning state."""
    if state == "mastered":
        return Badge("Mastered", variant=BadgeT.success, size=Size.sm)
    if state == "in_progress":
        return Badge("In Progress", variant=BadgeT.secondary, size=Size.sm)
    return Button(
        "Start Lesson",
        variant=ButtonT.primary,
        size=Size.sm,
        hx_post=f"/api/lesson/{uid}/start",
        hx_swap="outerHTML",
        hx_target="this",
    )


def _lesson_list(items: list[Any], learning_states: dict[str, str]) -> Div:
    """Render lesson list with enrollment buttons."""
    if not items:
        return EmptyState(title="No lessons found")

    detail_pattern = _DETAIL_ROUTES.get("lessons")
    rows = []
    for item in items:
        title = getattr(item, "title", "Untitled")
        description = getattr(item, "description", "") or ""
        uid = getattr(item, "uid", "")
        href = detail_pattern.format(uid=uid) if detail_pattern and uid else None
        state = learning_states.get(uid, "none")

        rows.append(
            CardGenerator.from_dataclass(
                {"title": title, "description": description},
                display_fields=["description"],
                show_labels=False,
                metadata=[uid] if uid else None,
                title_href=href,
                actions=_enrollment_button(uid, state),
            )
        )
    return Div(*rows, cls="space-y-3")


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
