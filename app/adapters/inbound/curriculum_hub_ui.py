"""Curriculum Hub UI Routes
==========================

UI for curriculum browser sub-pages.

Routes:
- GET /curriculum — 301 redirect to /profile (shelved: landing page deprecated)
- GET /lessons — 301 redirect to /path-steps (Lesson merged into PathStep)
- GET /path-steps — PathStep browser (Registered In / Available)
- GET /learning-paths — Learning Paths browser
"""

from typing import Any

from fasthtml.common import Div, H4, Li, NotStr, Span, Ul
from starlette.responses import RedirectResponse

from adapters.inbound.auth import get_current_user
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator, RouteList
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
    "path-steps": "/path-steps/{uid}/details",
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
        """Lesson merged into PathStep — redirect to /path-steps."""
        return RedirectResponse(url="/path-steps", status_code=301)

    @rt("/path-steps")
    async def path_steps_browser(request: Request) -> Any:
        """PathStep browser — Registered In + Available sections.

        Public: shared curriculum content is readable without authentication.
        Enrolled steps section only populates for authenticated users.
        """
        user_uid: str | None = get_current_user(request)

        ps_service = services.ps
        all_steps: list[Any] = []
        enrolled_uids: set[str] = set()

        if ps_service:
            list_result = await ps_service.core.list(limit=200)
            if not list_result.is_error:
                raw = list_result.value
                all_steps = raw if isinstance(raw, list) else raw[0]

            if user_uid:
                uid_result = await ps_service.mastery.get_in_progress_step_uids(user_uid)
                if not uid_result.is_error:
                    enrolled_uids = set(uid_result.value or [])

        enrolled_steps = [s for s in all_steps if s.uid in enrolled_uids]
        available_steps = [s for s in all_steps if s.uid not in enrolled_uids]

        content = Div(
            PageHeader("Path Steps"),
            _ps_list(enrolled_steps, available_steps),
            id="main-content",
        )

        return await BasePage(
            content=content,
            title="Path Steps",
            request=request,
            active_page="curriculum",
        )

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


def _ps_list(enrolled_steps: list[Any], available_steps: list[Any]) -> Div:
    """Render PathStep list: Registered In expanded, Available in an accordion.

    Accordion opens by default when user has no enrolled steps.
    """
    rows: list[Any] = []

    if enrolled_steps:
        rows.append(
            H4("Registered In", cls="text-sm font-semibold text-foreground mt-2 mb-2")
        )
        for step in enrolled_steps:
            rows.append(_ps_card(step, enrolled=True))

    if available_steps:
        open_by_default = "true" if not enrolled_steps else "false"
        chevron_svg = NotStr(
            '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
            'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            'class="transition-transform duration-200" '
            ':class="open ? \'rotate-180\' : \'\'">'
            '<path d="m6 9 6 6 6-6"/>'
            "</svg>"
        )
        rows.append(
            Div(
                Div(
                    Span(
                        f"Available ({len(available_steps)})",
                        cls=f"text-sm font-semibold text-foreground {'mt-6' if enrolled_steps else 'mt-2'}",
                    ),
                    chevron_svg,
                    cls="flex items-center justify-between cursor-pointer py-1 select-none",
                    **{"@click": "open = !open"},
                ),
                Div(
                    *[_ps_card(step, enrolled=False) for step in available_steps[:5]],
                    x_show="open",
                    **{"x-transition": ""},
                ),
                x_data=f"{{ open: {open_by_default} }}",
            )
        )

    if not enrolled_steps and not available_steps:
        return EmptyState(title="No path steps found")

    return Div(*rows, cls="space-y-3")


def _ps_card(step: Any, enrolled: bool) -> Any:
    """Render a single PathStep card with enrolment state."""
    uid = getattr(step, "uid", "")
    title = getattr(step, "title", None) or uid
    description = (getattr(step, "description", "") or "")[:200]

    if enrolled:
        action = Badge("Registered", variant=BadgeT.secondary, size=Size.sm)
    else:
        action = Button(
            "Register",
            variant=ButtonT.primary,
            size=Size.sm,
            hx_post=f"/api/path-steps/{uid}/start",
            hx_swap="outerHTML",
            hx_target="this",
        )

    return Div(
        Div(
            Div(
                CardGenerator.from_dataclass(
                    {"title": title, "description": description},
                    display_fields=["description"],
                    show_labels=False,
                    title_href=f"/path-steps/{uid}/details",
                ),
                cls="flex-1 min-w-0",
            ),
            Div(action, cls="shrink-0 ml-4 flex items-start pt-1"),
            cls="flex items-start gap-2",
        ),
        id=f"ps-{uid}",
        cls="relative",
    )


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
