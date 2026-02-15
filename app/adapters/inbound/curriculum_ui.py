"""
Curriculum Hub UI Routes
=========================

Card-grid hub page showing the 5 curriculum-related sections:
Knowledge, Learning Steps, Learning Paths, Reports, Shared With Me.

Accessible from the green "C" icon in the navbar.

Layout: Standard BasePage.
"""

from typing import Any

from fasthtml.common import A, Div, H1, P, Span
from starlette.requests import Request

from core.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage

logger = get_logger("skuel.routes.curriculum.ui")


def _curriculum_card(
    icon: str,
    name: str,
    href: str,
    primary_count: int,
    primary_label: str,
    secondary_count: int = 0,
    secondary_label: str = "",
) -> A:
    """Single navigational card for the curriculum hub."""
    secondary_el = (
        Span(f"{secondary_count} {secondary_label}", cls="text-sm text-base-content/50")
        if secondary_count > 0
        else None
    )

    return A(
        # Header
        Div(
            Span(icon, cls="text-xl"),
            Span(name, cls="text-base font-semibold text-base-content"),
            cls="flex items-center gap-2 mb-3",
        ),
        # Primary count
        Div(
            Span(str(primary_count), cls="text-3xl font-bold text-base-content"),
            Span(primary_label, cls="text-sm text-base-content/50 ml-2"),
            cls="flex items-baseline",
        ),
        # Secondary
        Div(secondary_el, cls="mt-1 min-h-[1.25rem]")
        if secondary_el
        else Div(cls="mt-1 min-h-[1.25rem]"),
        href=href,
        cls="block bg-white rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
        **{"hx-boost": "false"},
    )


def create_curriculum_ui_routes(app: Any, rt: Any, services: Any) -> None:
    """Register curriculum hub UI routes."""

    @rt("/curriculum")
    async def curriculum_hub(request: Request):
        user_uid = require_authenticated_user(request)
        context_result = await services.user_service.get_user_context(user_uid)
        if context_result.is_error:
            return await BasePage(
                P("Unable to load curriculum data.", cls="text-base-content/60"),
                title="Curriculum",
                request=request,
                active_page="curriculum",
            )
        context = context_result.value

        mastered = len(context.mastered_knowledge_uids)
        in_progress = len(context.in_progress_knowledge_uids)
        enrolled = len(context.enrolled_path_uids)

        cards = Div(
            _curriculum_card(
                icon="📖",
                name="Knowledge",
                href="/ku",
                primary_count=mastered + in_progress,
                primary_label="studied",
                secondary_count=mastered,
                secondary_label="mastered",
            ),
            _curriculum_card(
                icon="📝",
                name="Learning Steps",
                href="/profile/learning-steps",
                primary_count=0,
                primary_label="steps",
            ),
            _curriculum_card(
                icon="🗺️",
                name="Learning Paths",
                href="/profile/learning-paths",
                primary_count=enrolled,
                primary_label="enrolled",
            ),
            _curriculum_card(
                icon="📄",
                name="Reports",
                href="/reports",
                primary_count=0,
                primary_label="submitted",
            ),
            _curriculum_card(
                icon="📥",
                name="Shared With Me",
                href="/profile/shared",
                primary_count=0,
                primary_label="items",
            ),
            cls="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-5",
        )

        content = Div(
            H1("Curriculum", cls="text-2xl font-bold text-base-content"),
            P(
                "Your learning journey — knowledge, paths, and submissions.",
                cls="text-base-content/60 mb-6",
            ),
            cards,
        )

        return await BasePage(content, title="Curriculum", request=request, active_page="curriculum")
