"""Insights API Routes - Event-Driven Insights Management
===========================================================

API routes for managing event-driven insights (dismiss, mark as actioned).

(January 2026): Insight lifecycle management.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import FT, Request

if TYPE_CHECKING:
    from core.services.insight.insight_store import InsightStore

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.form_helpers import parse_json_body
from core.models.entity_requests import SmartDismissRequest
from core.models.insight_request import BulkInsightUidsRequest, SnoozeInsightRequest
from core.ports.query_types import ChartJsConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.insights.insight_card import DismissedInsightMessage

logger = get_logger("skuel.routes.insights.api")


def create_insights_api_routes(
    app: Any,
    rt: Any,
    insight_store: "InsightStore",
) -> list[Any]:
    """Create insights API routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        insight_store: InsightStore service for managing insights

    Returns:
        List of route handler functions
    """

    # NOTE: the bulk routes MUST be registered before the /{uid}/ routes —
    # Starlette matches in registration order, so a later-registered
    # /api/insights/bulk/dismiss is shadowed by /api/insights/{uid}/dismiss
    # (uid="bulk") and becomes unreachable.

    # ========================================
    # Bulk Action Endpoints
    # ========================================

    @rt("/api/insights/bulk/dismiss", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def bulk_dismiss_insights(request: Request) -> Result[dict[str, Any]]:
        """Bulk dismiss multiple insights."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_json_body(request, BulkInsightUidsRequest)
        if parsed.is_error:
            return parsed  # type: ignore[return-value]

        return await insight_store.bulk_dismiss(parsed.value.uids, user_uid)

    @rt("/api/insights/bulk/action", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def bulk_action_insights(request: Request) -> Result[dict[str, Any]]:
        """Bulk mark insights as actioned."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_json_body(request, BulkInsightUidsRequest)
        if parsed.is_error:
            return parsed  # type: ignore[return-value]

        return await insight_store.bulk_mark_actioned(parsed.value.uids, user_uid)

    @rt("/api/insights/bulk/smart-dismiss", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def smart_dismiss_insights(request: Request) -> Result[dict[str, Any]]:
        """Smart bulk dismiss — dismiss all insights matching a filter."""
        user_uid = require_authenticated_user(request)

        parsed = await parse_json_body(request, SmartDismissRequest)
        if parsed.is_error:
            return parsed  # type: ignore[return-value]
        req = parsed.value

        return await insight_store.smart_dismiss(user_uid, req.filter_type, req.filter_value)

    @rt("/api/insights/{uid}/dismiss", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def dismiss_insight(request: Request, uid: str) -> Result[FT]:
        """Dismiss an insight (mark as dismissed).

        Args:
            request: HTTP request with authentication (optional JSON body with notes)
            uid: Insight UID to dismiss

        Returns:
            Result with success message or error
        """
        user_uid = require_authenticated_user(request)

        # Parse optional notes from request body
        notes = ""
        try:
            body = await request.json()
            notes = body.get("notes", "")
        except Exception:  # safety-net: JSON parsing boundary — optional body
            # No body provided - that's ok, notes are optional
            pass

        # Dismiss the insight with notes
        result = await insight_store.dismiss_insight(uid, user_uid, notes=notes)

        if result.is_error:
            logger.warning(f"Failed to dismiss insight {uid}: {result.error}")
            return Result.fail(result)

        logger.info(
            f"Insight dismissed: {uid} by {user_uid}" + (f" (notes: {notes[:50]})" if notes else "")
        )

        # Return success message (HTMX will swap with this)
        return Result.ok(DismissedInsightMessage())

    @rt("/api/insights/{uid}/action", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def mark_insight_actioned(request: Request, uid: str) -> Result[FT]:
        """Mark an insight as actioned.

        Args:
            request: HTTP request with authentication (optional JSON body with notes)
            uid: Insight UID to mark as actioned

        Returns:
            Result with success message or error
        """
        user_uid = require_authenticated_user(request)

        # Parse optional notes from request body
        notes = ""
        try:
            body = await request.json()
            notes = body.get("notes", "")
        except Exception:  # safety-net: JSON parsing boundary — optional body
            # No body provided - that's ok, notes are optional
            pass

        # Mark as actioned with notes
        result = await insight_store.mark_actioned(uid, user_uid, notes=notes)

        if result.is_error:
            logger.warning(f"Failed to mark insight actioned {uid}: {result.error}")
            return Result.fail(result)

        logger.info(
            f"Insight marked as actioned: {uid} by {user_uid}"
            + (f" (notes: {notes[:50]})" if notes else "")
        )

        # Return success message (HTMX will swap with this)
        from fasthtml.common import NotStr

        from ui.feedback import Alert, AlertT

        return Result.ok(
            Alert(
                NotStr("✓ Great! You've acted on this insight."),
                variant=AlertT.success,
            )
        )

    @rt("/api/insights/active")
    @boundary_handler(success_status=200)
    async def get_active_insights(
        request: Request,
        domain: str | None = None,
        limit: int = 50,
    ) -> Result[dict[str, Any]]:
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
            return Result.fail(result)

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
    async def get_insight_stats(request: Request) -> Result[dict[str, Any]]:
        """Get insight statistics for the current user (JSON API).

        Args:
            request: HTTP request with authentication

        Returns:
            Result with insight statistics or error
        """
        user_uid = require_authenticated_user(request)

        return await insight_store.get_insight_stats(user_uid)

    # ========================================
    # Chart Visualization Endpoints
    # ========================================

    @rt("/api/insights/charts/impact-distribution")
    @boundary_handler(success_status=200)
    async def impact_distribution_chart(request: Request) -> Result[ChartJsConfig]:
        """Chart.js doughnut chart config for impact distribution."""
        user_uid = require_authenticated_user(request)
        return await insight_store.get_impact_distribution_chart(user_uid)

    @rt("/api/insights/charts/domain-distribution")
    @boundary_handler(success_status=200)
    async def domain_distribution_chart(request: Request) -> Result[ChartJsConfig]:
        """Chart.js bar chart config for insights by domain."""
        user_uid = require_authenticated_user(request)
        return await insight_store.get_domain_distribution_chart(user_uid)

    @rt("/api/insights/charts/type-distribution")
    @boundary_handler(success_status=200)
    async def type_distribution_chart(request: Request) -> Result[ChartJsConfig]:
        """Chart.js doughnut chart config for insight type distribution."""
        user_uid = require_authenticated_user(request)
        return await insight_store.get_type_distribution_chart(user_uid)

    @rt("/api/insights/charts/action-rate")
    @boundary_handler(success_status=200)
    async def action_rate_chart(request: Request) -> Result[ChartJsConfig]:
        """Chart.js gauge/doughnut chart for insight action rate."""
        user_uid = require_authenticated_user(request)
        return await insight_store.get_action_rate_chart(user_uid)

    # ========================================
    # Detail Modal Endpoints
    # ========================================

    @rt("/api/insights/{uid}/details")
    @boundary_handler(success_status=200)
    async def get_insight_details(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Get detailed insight information for modal display.

        Args:
            request: HTTP request with authentication
            uid: Insight UID to get details for

        Returns:
            Result with detailed insight data or error
        """
        user_uid = require_authenticated_user(request)

        # Get insight by UID
        result = await insight_store.get_insight_by_uid(uid)

        if result.is_error:
            logger.error(f"Failed to retrieve insight details for {uid}: {result.error}")
            return Result.fail(result)

        insight = result.value

        # Verify ownership (insight belongs to requesting user)
        if insight.user_uid != user_uid:
            logger.warning(
                f"User {user_uid} attempted to access insight {uid} owned by {insight.user_uid}"
            )
            return Result.fail(Errors.not_found(f"Insight {uid} not found"))

        # Convert to dictionary with full details
        insight_data = {
            "uid": insight.uid,
            "title": insight.title,
            "description": insight.description,
            "insight_type": insight.insight_type.value,
            "domain": insight.domain,
            "impact": insight.impact.value,
            "confidence": insight.confidence,
            "entity_uid": insight.entity_uid,
            "recommended_actions": insight.recommended_actions,
            "supporting_data": insight.supporting_data or {},
            "created_at": insight.created_at.isoformat() if insight.created_at else None,
        }

        return Result.ok(insight_data)

    @rt("/api/insights/{uid}/snooze", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def snooze_insight(request: Request, uid: str) -> Result[dict[str, Any]]:
        """Snooze an insight for a specified number of days.

        Args:
            request: HTTP request with authentication and JSON body
            uid: Insight UID to snooze

        Returns:
            Result with success message or error

        Example:
            POST /api/insights/{uid}/snooze
            {"days": 3}
        """
        user_uid = require_authenticated_user(request)

        # Parse request body
        parsed = await parse_json_body(request, SnoozeInsightRequest)
        if parsed.is_error:
            return parsed  # type: ignore[return-value]
        days = parsed.value.days

        # Snooze the insight (mark as dismissed with snooze metadata)
        # For now, we'll just dismiss it - a full implementation would add snooze_until_date
        result = await insight_store.dismiss_insight(uid, user_uid)

        if result.is_error:
            logger.warning(f"Failed to snooze insight {uid}: {result.error}")
            return Result.fail(result)

        logger.info(f"Insight snoozed for {days} days: {uid} by {user_uid}")

        return Result.ok(
            {
                "message": f"Insight snoozed for {days} day(s)",
                "uid": uid,
                "days": days,
            }
        )

    return [
        dismiss_insight,
        mark_insight_actioned,
        get_active_insights,
        get_insight_stats,
        # Chart endpoints
        impact_distribution_chart,
        domain_distribution_chart,
        type_distribution_chart,
        action_rate_chart,
        get_insight_details,
        snooze_insight,
    ]
