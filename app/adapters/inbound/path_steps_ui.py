"""
Path Steps UI Routes — Detail Page + Learning Actions
=======================================================

PathStep detail view with markdown rendering, TOC sidebar, metadata,
and HTMX-powered learning state actions (start, mark-read, bookmark).

Absorbed from lesson_ui.py during Lesson→PathStep merge.
"""

from typing import Any

from fasthtml.common import H3, Div, Li, NotStr, P, Request, Ul

from adapters.inbound.auth import require_authenticated_user
from core.services.ps_service import PsService
from core.utils.logging import get_logger
from core.utils.markdown_renderer import render_markdown_with_toc
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.metadata_badge import metadata_badge
from ui.patterns.relationships import EntityRelationshipsSection

logger = get_logger("skuel.routes.path_steps.ui")


# ============================================================================
# Helpers
# ============================================================================


def _start_step_button(uid: str, is_in_progress: bool, is_mastered: bool) -> Any:
    """Render the enrollment/start button based on learning state."""
    if is_mastered:
        return Badge("Mastered", variant=BadgeT.success, size=Size.sm)
    if is_in_progress:
        return Badge("In Progress", variant=BadgeT.secondary, size=Size.sm)
    return Button(
        "Start Learning",
        variant=ButtonT.primary,
        size=Size.sm,
        hx_post=f"/api/path-steps/{uid}/start",
        hx_swap="outerHTML",
        hx_target="this",
    )


# ============================================================================
# Route factory
# ============================================================================


def create_path_steps_ui_routes(_app: Any, rt: Any, ps_service: PsService) -> list[Any]:
    """
    Create Path Steps UI routes.

    Args:
        ps_service: PsService (services.ps).
    """

    @rt("/path-steps/{uid}/details")
    async def step_detail_page(request: Request, uid: str) -> Any:
        """Path step detail page with full content rendering."""
        user_uid = require_authenticated_user(request)

        # Fetch step with content body
        result = await ps_service.get_with_content(uid)
        if result.is_error:
            return await BasePage(
                content=Div(
                    Card(
                        CardBody(
                            H3("Path Step Not Found", cls="text-lg font-bold"),
                            P(
                                f"No path step with identifier: {uid}",
                                cls="text-muted-foreground mt-2",
                            ),
                            ButtonLink(
                                "← Back to Path Steps",
                                href="/pathways/steps",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                                cls="mt-4",
                            ),
                        ),
                    ),
                    cls="max-w-4xl mx-auto p-8",
                ),
                title="Path Step Not Found",
                request=request,
            )

        step, content_body = result.value
        # Fall back to step.content property when no :Content node exists
        if not content_body and getattr(step, "content", None):
            content_body = str(step.content)

        # Record view
        await ps_service.mastery.record_view(user_uid, uid)

        # Get learning state
        state_result = await ps_service.mastery.get_learning_state(user_uid, uid)
        is_marked_read = state_result.value.is_marked_as_read if state_result.is_ok else False
        is_bookmarked = state_result.value.is_bookmarked if state_result.is_ok else False
        is_in_progress = (
            state_result.value.state.value == "in_progress" if state_result.is_ok else False
        )
        is_mastered = state_result.value.state.value == "mastered" if state_result.is_ok else False

        # Render markdown with TOC
        content_html, toc_html = render_markdown_with_toc(content_body or "")
        has_toc = bool(toc_html and toc_html.strip())

        # Breadcrumbs
        breadcrumb_path = [
            {"uid": "path-steps", "title": "Path Steps", "url": "/pathways/steps"},
            {"uid": uid, "title": step.title, "url": ""},
        ]

        # Metadata badges
        metadata_items = []
        if step.domain:
            domain_label = getattr(step.domain, "value", str(step.domain))
            metadata_items.append(metadata_badge("Domain:", domain_label, BadgeT.primary))
        if step.complexity:
            metadata_items.append(metadata_badge("Complexity:", str(step.complexity.value)))
        if step.learning_level:
            metadata_items.append(metadata_badge("Level:", str(step.learning_level.value)))
        if step.estimated_time_minutes:
            metadata_items.append(metadata_badge("Time:", f"{step.estimated_time_minutes} min"))
        if step.estimated_hours:
            metadata_items.append(metadata_badge("Hours:", f"{step.estimated_hours:.1f}h"))

        metadata_section = (
            Div(*metadata_items, cls="flex flex-wrap gap-2 mb-4") if metadata_items else Div()
        )

        # Learning objectives
        objectives_section = Div()
        if step.learning_objectives:
            objectives_section = Div(
                H3("Learning Objectives", cls="text-base font-semibold mb-2"),
                Ul(
                    *[
                        Li(obj, cls="text-sm text-muted-foreground")
                        for obj in step.learning_objectives
                    ],
                    cls="list-disc pl-5 space-y-1 mb-6",
                ),
            )

        # Tags
        tags_section = Div()
        if step.tags:
            tag_badges = [Badge(tag, variant=BadgeT.outline, size=Size.sm) for tag in step.tags]
            tags_section = Div(*tag_badges, cls="flex flex-wrap gap-1 mt-3")

        # Reading content
        reading_content = Div(
            NotStr(content_html or "No content available."),
            cls="prose prose-lg max-w-none",
        )

        # Action buttons
        mark_read_btn = Button(
            "Marked as Read" if is_marked_read else "Mark as Read",
            variant=ButtonT.success if is_marked_read else ButtonT.primary,
            size=Size.sm,
            hx_post=f"/api/path-steps/{uid}/mark-read",
            hx_swap="outerHTML",
            hx_target="this",
            disabled=is_marked_read,
        )

        bookmark_btn = Button(
            "Bookmarked" if is_bookmarked else "Bookmark",
            variant=ButtonT.secondary if is_bookmarked else ButtonT.ghost,
            size=Size.sm,
            hx_post=f"/api/path-steps/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )

        start_btn = _start_step_button(uid, is_in_progress, is_mastered)

        # Main content column
        main_column = Div(
            Breadcrumbs(path=breadcrumb_path, show_home=False),
            metadata_section,
            objectives_section,
            reading_content,
            # Actions below content
            Div(
                start_btn,
                mark_read_btn,
                bookmark_btn,
                cls="flex gap-2 border-t border-border pt-6 mt-8",
            ),
            # Metadata footer
            Div(tags_section, cls="border-t border-border pt-6 mt-8") if step.tags else Div(),
            # Lateral relationships
            EntityRelationshipsSection(entity_uid=uid, entity_type="ps"),
            cls="flex-1 min-w-0 max-w-4xl mx-auto px-6 lg:px-8 py-4 lg:py-6",
        )

        if has_toc:
            toc_sidebar = Div(
                Div(
                    H3("Contents", cls="font-semibold text-sm mb-3"),
                    Div(
                        NotStr(toc_html),
                        cls="prose prose-sm max-w-none toc-nav",
                    ),
                    cls="sticky top-20 p-5 max-h-[calc(100vh-6rem)] overflow-y-auto",
                ),
                cls="hidden lg:block w-56 shrink-0 border-l border-border",
            )
            content = Div(main_column, toc_sidebar, cls="flex")
        else:
            content = main_column

        return await BasePage(
            content=content,
            title=step.title,
            request=request,
            active_page="pathways",
            page_type=PageType.CUSTOM,
        )

    # ========================================================================
    # LEARNING STATE HTMX ACTIONS
    # ========================================================================

    @rt("/api/path-steps/{uid}/start", methods=["POST"])
    async def start_step(request: Request, uid: str) -> Any:
        """Start a path step (mark as in-progress). Returns updated button HTML.

        Enforces a limit of 2 simultaneously enrolled PathSteps.
        """
        user_uid = require_authenticated_user(request)

        # Enforce enrollment limit (max 2 in-progress PathSteps)
        count_result = await ps_service.mastery.count_in_progress_steps(user_uid)
        if not count_result.is_error and (count_result.value or 0) >= 2:
            return Button(
                "Limit reached (2)",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
                title="You can enrol in at most 2 Path Steps at once",
            )

        result = await ps_service.mastery.mark_in_progress(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
            )

        return Badge("In Progress", variant=BadgeT.secondary, size=Size.sm)

    @rt("/api/path-steps/{uid}/mark-read", methods=["POST"])
    async def mark_step_as_read(request: Request, uid: str) -> Any:
        """Mark path step as read. Returns updated button HTML."""
        user_uid = require_authenticated_user(request)

        result = await ps_service.mastery.mark_as_read(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
            )

        return Button(
            "Marked as Read",
            variant=ButtonT.success,
            size=Size.sm,
            disabled=True,
        )

    @rt("/api/path-steps/{uid}/bookmark", methods=["POST"])
    async def toggle_step_bookmark(request: Request, uid: str) -> Any:
        """Toggle path step bookmark. Returns updated button HTML."""
        user_uid = require_authenticated_user(request)

        result = await ps_service.mastery.toggle_bookmark(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
            )

        is_bookmarked = result.value

        return Button(
            "Bookmarked" if is_bookmarked else "Bookmark",
            variant=ButtonT.secondary if is_bookmarked else ButtonT.ghost,
            size=Size.sm,
            hx_post=f"/api/path-steps/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )

    logger.info(
        "Path Steps UI routes registered: /path-steps/{uid}/details, "
        "/api/path-steps/{uid}/start, /api/path-steps/{uid}/mark-read, "
        "/api/path-steps/{uid}/bookmark"
    )

    return []  # Routes registered via @rt() decorators


__all__ = ["create_path_steps_ui_routes"]
