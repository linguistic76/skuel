"""
Path Steps UI Routes — Learning State Actions
===============================================

POST mutation endpoints for HTMX learning state actions (start, mark-read, bookmark).
Detail view lives at /explore/ps/{uid} (explore_ui.py).
"""

from typing import Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from core.services.ps_service import PsService
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.feedback import Badge, BadgeT
from ui.layout import Size

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

    GET detail route redirects to /explore/ps/{uid} (merged discovery page).
    POST mutation endpoints remain here for HTMX learning state actions.
    """

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
        "Path Steps UI routes registered: "
        "/api/path-steps/{uid}/start, /api/path-steps/{uid}/mark-read, "
        "/api/path-steps/{uid}/bookmark"
    )

    return []


__all__ = ["create_path_steps_ui_routes"]
