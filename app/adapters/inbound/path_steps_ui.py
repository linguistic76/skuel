"""
Path Steps UI Routes — Browser + Learning State Actions
=========================================================

GET /path-steps — top-level PathStep browser (lists all curriculum PathSteps).
POST mutation endpoints for HTMX learning state actions (start, mark-read, bookmark).
Detail view lives at /explore/ps/{uid} (explore_ui.py).
"""

from typing import Any

from fasthtml.common import A, Div, P, Request, Span

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from core.services.ps_service import PsService
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.patterns.empty_state import EmptyState
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader

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
    """Create Path Steps UI routes.

    GET /path-steps lists all curriculum PathSteps. Detail view lives at
    /explore/ps/{uid} (merged discovery page). POST mutation endpoints remain
    here for HTMX learning state actions.
    """

    # ========================================================================
    # BROWSER
    # ========================================================================

    @rt("/path-steps")
    async def path_steps_browser(request: Request) -> Any:
        """PathSteps browser — shell renders immediately, content loads via HTMX."""
        content = Div(
            PageHeader("Path Steps", subtitle="Curriculum content units (composed of Kus)"),
            content_loading_placeholder("/path-steps/content", "path-steps-content"),
            id="main-content",
        )
        return await BasePage(
            content=content,
            title="Path Steps",
            request=request,
            active_page="path-steps",
        )

    @rt("/path-steps/content")
    async def path_steps_content_fragment(request: Request) -> Any:
        """HTMX fragment: PathStep list."""
        result = await ps_service.list_steps(limit=50)
        items: list[Any] = []
        if not result.is_error and result.value:
            items = list(result.value)
        return Div(_path_step_list(items), id="path-steps-content")

    # ========================================================================
    # LEARNING STATE HTMX ACTIONS
    # ========================================================================

    @rt("/api/path-steps/{uid}/start", methods=["POST"])
    @csrf_protected
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
    @csrf_protected
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
    @csrf_protected
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
        "Path Steps UI routes registered: "
        "/path-steps, /path-steps/content, "
        "/api/path-steps/{uid}/start, /api/path-steps/{uid}/mark-read, "
        "/api/path-steps/{uid}/bookmark"
    )

    return []


def _path_step_list(items: list[Any]) -> Any:
    """Render PathSteps with a teal 'Path Step' badge per row.

    Mirrors the visual treatment in library_ui.py so PathStep rows look
    consistent everywhere.
    """
    if not items:
        return EmptyState(title="No path steps found")

    count_note = Span(
        f"{len(items)} path step{'s' if len(items) != 1 else ''}",
        cls="text-xs text-muted-foreground mb-3 block",
    )

    rows = []
    for step in items:
        uid = getattr(step, "uid", "")
        title = getattr(step, "title", None) or uid or "Untitled"
        description = getattr(step, "description", "") or ""
        truncated = description[:120] + ("…" if len(description) > 120 else "")

        rows.append(
            Div(
                Div(
                    Badge(
                        "Path Step",
                        variant=None,
                        cls="bg-teal-100 text-teal-800 border-teal-200",
                        size=Size.sm,
                    ),
                    A(
                        title,
                        href=f"/explore/ps/{uid}" if uid else "#",
                        cls="text-sm font-medium text-foreground hover:text-primary hover:underline ml-2",
                    ),
                    cls="flex items-center",
                ),
                P(truncated, cls="text-xs text-muted-foreground mt-0.5") if description else None,
                cls="py-2.5 border-b border-border/50 last:border-0",
            )
        )
    return Div(count_note, Div(*rows))


__all__ = ["create_path_steps_ui_routes"]
