"""Insights API Routes - Event-Driven Insights Management
===========================================================

API routes for managing event-driven insights (dismiss, mark as actioned).

Phase 1 (January 2026): Insight lifecycle management.
"""

from typing import Any

from fasthtml.common import Request

from components.insight_card import DismissedInsightMessage
from core.auth import require_authenticated_user
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.insights.api")


def create_insights_api_routes(
    app: Any,
    rt: Any,
    insight_store: Any,
) -> list[Any]:
    """Create insights API routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        insight_store: InsightStore service for managing insights

    Returns:
        List of route handler functions
    """

    @rt("/api/insights/{uid}/dismiss")
    @boundary_handler(success_status=200)
    async def dismiss_insight(request: Request, uid: str) -> Result[Any]:
        """Dismiss an insight (mark as dismissed).

        Args:
            request: HTTP request with authentication
            uid: Insight UID to dismiss

        Returns:
            Result with success message or error
        """
        user_uid = require_authenticated_user(request)

        # Dismiss the insight
        result = await insight_store.dismiss_insight(uid, user_uid)

        if result.is_error:
            logger.warning(f"Failed to dismiss insight {uid}: {result.error}")
            return result

        logger.info(f"Insight dismissed: {uid} by {user_uid}")

        # Return success message (HTMX will swap with this)
        return Result.ok(DismissedInsightMessage())

    @rt("/api/insights/{uid}/action")
    @boundary_handler(success_status=200)
    async def mark_insight_actioned(request: Request, uid: str) -> Result[Any]:
        """Mark an insight as actioned.

        Args:
            request: HTTP request with authentication
            uid: Insight UID to mark as actioned

        Returns:
            Result with success message or error
        """
        user_uid = require_authenticated_user(request)

        # Mark as actioned
        result = await insight_store.mark_actioned(uid, user_uid)

        if result.is_error:
            logger.warning(f"Failed to mark insight actioned {uid}: {result.error}")
            return result

        logger.info(f"Insight marked as actioned: {uid} by {user_uid}")

        # Return success message (HTMX will swap with this)
        from fasthtml.common import Div, NotStr

        return Result.ok(
            Div(
                NotStr("✓ Great! You've acted on this insight."),
                cls="alert alert-success",
            )
        )

    @rt("/api/insights/active")
    @boundary_handler(success_status=200)
    async def get_active_insights(
        request: Request,
        domain: str | None = None,
        limit: int = 50,
    ) -> Result[Any]:
        """Get active insights for the current user (JSON API).

        Args:
            request: HTTP request with authentication
            domain: Optional domain filter
            limit: Maximum number of insights to return

        Returns:
            Result with list of active insights or error
        """
        user_uid = require_authenticated_user(request)

        # Get active insights
        result = await insight_store.get_active_insights(
            user_uid=user_uid,
            domain=domain,
            limit=limit,
        )

        if result.is_error:
            logger.error(f"Failed to retrieve active insights: {result.error}")
            return result

        insights = result.value

        # Convert to dictionaries for JSON response
        insights_data = [insight.to_dict() for insight in insights]

        return Result.ok(
            {
                "insights": insights_data,
                "count": len(insights_data),
                "domain_filter": domain,
            }
        )

    @rt("/api/insights/stats")
    @boundary_handler(success_status=200)
    async def get_insight_stats(request: Request) -> Result[Any]:
        """Get insight statistics for the current user (JSON API).

        Args:
            request: HTTP request with authentication

        Returns:
            Result with insight statistics or error
        """
        user_uid = require_authenticated_user(request)

        # Get stats
        result = await insight_store.get_insight_stats(user_uid)

        if result.is_error:
            logger.error(f"Failed to retrieve insight stats: {result.error}")
            return result

        return result

    return [dismiss_insight, mark_insight_actioned, get_active_insights, get_insight_stats]
