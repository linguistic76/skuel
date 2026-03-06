"""
KU Reading API Routes - Phase A
================================

API routes for KU interaction tracking:
- Mark as read
- Toggle bookmark
- Get navigation (next/prev KU)

Routes:
- POST /api/article/{uid}/mark-read - Mark KU as read
- POST /api/article/{uid}/bookmark - Toggle bookmark
- GET /api/article/{uid}/navigation - Get next/prev KU in MOC order
"""

from typing import Any

from fasthtml.common import Button, Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.ku.reading.api")


def create_article_reading_api_routes(
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

    @rt("/api/article/{uid}/mark-read", methods=["POST"])
    async def mark_ku_as_read(request: Request, uid: str) -> Any:
        """Mark KU as read. Returns updated button HTML for HTMX swap."""
        user_uid = require_authenticated_user(request)

        result = await ku_interaction_service.mark_as_read(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                cls="btn btn-sm btn-error",
                disabled=True,
            )

        return Button(
            "Marked as Read",
            cls="btn btn-sm btn-outline btn-success",
            disabled=True,
        )

    @rt("/api/article/{uid}/bookmark", methods=["POST"])
    async def toggle_ku_bookmark(request: Request, uid: str) -> Any:
        """Toggle KU bookmark. Returns updated button HTML for HTMX swap."""
        user_uid = require_authenticated_user(request)

        result = await ku_interaction_service.toggle_bookmark(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                cls="btn btn-sm btn-error",
                disabled=True,
            )

        is_bookmarked = result.value

        return Button(
            "Bookmarked" if is_bookmarked else "Bookmark",
            cls="btn btn-sm btn-secondary" if is_bookmarked else "btn btn-sm btn-ghost",
            hx_post=f"/api/article/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )

    @rt("/api/article/{uid}/navigation")
    @boundary_handler()
    async def get_ku_navigation(request: Request, uid: str) -> Result[dict[str, Any]]:
        """
        Get next/prev KU in MOC learning sequence.

        Uses MOC ORGANIZES order to determine siblings.
        """
        require_authenticated_user(request)

        empty_nav: dict[str, Any] = {
            "prev_uid": None,
            "prev_title": None,
            "next_uid": None,
            "next_title": None,
        }

        # Get organizers containing this KU
        organizers_result = await ku_service.find_organizers(uid)
        if organizers_result.is_error or not organizers_result.value:
            return Result.ok(empty_nav)

        # Use first organizer for navigation
        moc_uid = organizers_result.value[0].get("uid")

        # Get children via organization view (depth=1 for direct children only)
        moc_view_result = await ku_service.get_organization_view(moc_uid, max_depth=1)
        if moc_view_result.is_error:
            return Result.ok(empty_nav)

        children = moc_view_result.value.children

        # Find current index
        current_idx = None
        for idx, child in enumerate(children):
            if child.uid == uid:
                current_idx = idx
                break

        if current_idx is None:
            return Result.ok(empty_nav)

        # Get prev/next
        prev_ku = children[current_idx - 1] if current_idx > 0 else None
        next_ku = children[current_idx + 1] if current_idx < len(children) - 1 else None

        return Result.ok(
            {
                "prev_uid": prev_ku.uid if prev_ku else None,
                "prev_title": prev_ku.title if prev_ku else None,
                "next_uid": next_ku.uid if next_ku else None,
                "next_title": next_ku.title if next_ku else None,
            }
        )

    logger.info("KU reading API routes registered (3 endpoints)")

    return [
        mark_ku_as_read,
        toggle_ku_bookmark,
        get_ku_navigation,
    ]


__all__ = ["create_article_reading_api_routes"]
