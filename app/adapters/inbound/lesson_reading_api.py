"""
KU Reading API Routes - Phase A
================================

API routes for KU interaction tracking:
- Mark as read
- Toggle bookmark
- Get navigation (next/prev KU)

Routes:
- POST /api/lesson/{uid}/mark-read - Mark KU as read
- POST /api/lesson/{uid}/bookmark - Toggle bookmark
- GET /api/lesson/{uid}/navigation - Get next/prev KU in MOC order
"""

from typing import Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from ui.buttons import Button, ButtonT
from ui.layout import Size

logger = get_logger("skuel.routes.ku.reading.api")


def create_lesson_reading_api_routes(
    app: Any,
    rt: Any,
    ku_interaction_service: Any,
    ku_service: Any,
) -> list[Any]:
    """
    Create KU reading API routes.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        ku_interaction_service: Interaction tracking service
        ku_service: KU service with organization methods for prev/next

    Returns:
        List of registered route functions
    """

    @rt("/api/lesson/{uid}/mark-read", methods=["POST"])
    async def mark_ku_as_read(request: Request, uid: str) -> Any:
        """Mark KU as read. Returns updated button HTML for HTMX swap."""
        user_uid = require_authenticated_user(request)

        result = await ku_interaction_service.mark_as_read(user_uid, uid)

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

    @rt("/api/lesson/{uid}/bookmark", methods=["POST"])
    async def toggle_ku_bookmark(request: Request, uid: str) -> Any:
        """Toggle KU bookmark. Returns updated button HTML for HTMX swap."""
        user_uid = require_authenticated_user(request)

        result = await ku_interaction_service.toggle_bookmark(user_uid, uid)

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
            hx_post=f"/api/lesson/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )

    @rt("/api/lesson/{uid}/navigation")
    @boundary_handler()
    async def get_ku_navigation(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get next/prev KU in MOC learning sequence."""
        require_authenticated_user(request)
        result = await ku_service.get_navigation(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        nav = result.value
        return Result.ok(
            {
                "prev_uid": nav.prev_uid,
                "prev_title": nav.prev_title,
                "next_uid": nav.next_uid,
                "next_title": nav.next_title,
            }
        )

    logger.info("KU reading API routes registered (3 endpoints)")

    return [
        mark_ku_as_read,
        toggle_ku_bookmark,
        get_ku_navigation,
    ]


__all__ = ["create_lesson_reading_api_routes"]
