"""
KU Reading API Routes - MVP Phase A
====================================

API routes for KU interaction tracking:
- Mark as read
- Toggle bookmark
- Get navigation (next/prev KU)

Routes:
- POST /api/ku/{uid}/mark-read - Mark KU as read
- POST /api/ku/{uid}/bookmark - Toggle bookmark
- GET /api/ku/{uid}/navigation - Get next/prev KU
"""

from typing import Any

from fasthtml.common import Button, Request

from core.auth import require_authenticated_user
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.ku.reading.api")


def create_ku_reading_api_routes(
    app: Any,
    rt: Any,
    ku_interaction_service: Any,
    moc_service: Any,
) -> list[Any]:
    """
    Create KU reading API routes.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        ku_interaction_service: Interaction tracking service
        moc_service: MOC service for navigation

    Returns:
        List of registered route functions
    """

    @rt("/api/ku/{uid}/mark-read", methods=["POST"])
    async def mark_ku_as_read(request: Request, uid: str) -> Any:
        """
        Mark KU as read.

        Returns updated button HTML.
        """
        user_uid = require_authenticated_user(request)

        result = await ku_interaction_service.mark_as_read(user_uid, uid)

        if result.is_error:
            return Button(
                "❌ Error",
                cls="btn btn-sm btn-error",
                disabled=True,
            )

        # Return updated button
        return Button(
            "✓ Marked as Read",
            cls="btn btn-sm btn-outline",
            disabled=True,
        )

    @rt("/api/ku/{uid}/bookmark", methods=["POST"])
    async def toggle_ku_bookmark(request: Request, uid: str) -> Any:
        """
        Toggle KU bookmark.

        Returns updated button HTML.
        """
        user_uid = require_authenticated_user(request)

        result = await ku_interaction_service.toggle_bookmark(user_uid, uid)

        if result.is_error:
            return Button(
                "❌ Error",
                cls="btn btn-sm btn-error",
                disabled=True,
            )

        is_bookmarked = result.value

        # Return updated button
        return Button(
            "⭐ Bookmarked" if is_bookmarked else "☆ Bookmark",
            cls="btn btn-sm btn-primary" if is_bookmarked else "btn btn-sm btn-ghost",
            hx_post=f"/api/ku/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )

    @rt("/api/ku/{uid}/navigation")
    @boundary_handler()
    async def get_ku_navigation(request: Request, uid: str) -> Result[dict[str, Any]]:
        """
        Get next/prev KU in learning sequence.

        Returns:
            Result[dict]: {
                "prev_uid": str | None,
                "prev_title": str | None,
                "next_uid": str | None,
                "next_title": str | None,
            }
        """
        user_uid = require_authenticated_user(request)

        # Get MOCs containing this KU
        mocs_result = await moc_service.find_mocs_containing(uid)
        if mocs_result.is_error or not mocs_result.value:
            # No MOC context, no navigation
            return Result.ok({
                "prev_uid": None,
                "prev_title": None,
                "next_uid": None,
                "next_title": None,
            })

        # Use first MOC for navigation
        moc = mocs_result.value[0]
        moc_uid = moc.get("uid")
        current_order = moc.get("order", 0)

        # Get MOC children to find prev/next
        children_result = await moc_service.get_children(moc_uid)
        if children_result.is_error:
            return Result.ok({
                "prev_uid": None,
                "prev_title": None,
                "next_uid": None,
                "next_title": None,
            })

        children = children_result.value
        # Sort by order
        children_sorted = sorted(children, key=lambda x: x.get("order", 0))

        # Find current index
        current_idx = None
        for idx, child in enumerate(children_sorted):
            if child.get("uid") == uid:
                current_idx = idx
                break

        if current_idx is None:
            return Result.ok({
                "prev_uid": None,
                "prev_title": None,
                "next_uid": None,
                "next_title": None,
            })

        # Get prev/next
        prev_ku = children_sorted[current_idx - 1] if current_idx > 0 else None
        next_ku = children_sorted[current_idx + 1] if current_idx < len(children_sorted) - 1 else None

        return Result.ok({
            "prev_uid": prev_ku.get("uid") if prev_ku else None,
            "prev_title": prev_ku.get("title") if prev_ku else None,
            "next_uid": next_ku.get("uid") if next_ku else None,
            "next_title": next_ku.get("title") if next_ku else None,
        })

    logger.info("KU reading API routes registered (3 endpoints)")

    return [
        mark_ku_as_read,
        toggle_ku_bookmark,
        get_ku_navigation,
    ]


__all__ = ["create_ku_reading_api_routes"]
