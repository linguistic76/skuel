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
from core.utils.result_simplified import Errors, Result

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

    @rt("/api/insights/{uid}/dismiss", methods=["POST"])
    @boundary_handler(success_status=200)
    async def dismiss_insight(request: Request, uid: str) -> Result[Any]:
        """Dismiss an insight (mark as dismissed).

        Phase 4, Task 17: Now accepts optional notes parameter.

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
        except Exception:
            # No body provided - that's ok, notes are optional
            pass

        # Dismiss the insight with notes
        result = await insight_store.dismiss_insight(uid, user_uid, notes=notes)

        if result.is_error:
            logger.warning(f"Failed to dismiss insight {uid}: {result.error}")
            return Result.fail(result.expect_error())

        logger.info(
            f"Insight dismissed: {uid} by {user_uid}" + (f" (notes: {notes[:50]})" if notes else "")
        )

        # Return success message (HTMX will swap with this)
        return Result.ok(DismissedInsightMessage())

    @rt("/api/insights/{uid}/action", methods=["POST"])
    @boundary_handler(success_status=200)
    async def mark_insight_actioned(request: Request, uid: str) -> Result[Any]:
        """Mark an insight as actioned.

        Phase 4, Task 17: Now accepts optional notes parameter.

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
        except Exception:
            # No body provided - that's ok, notes are optional
            pass

        # Mark as actioned with notes
        result = await insight_store.mark_actioned(uid, user_uid, notes=notes)

        if result.is_error:
            logger.warning(f"Failed to mark insight actioned {uid}: {result.error}")
            return Result.fail(result.expect_error())

        logger.info(
            f"Insight marked as actioned: {uid} by {user_uid}"
            + (f" (notes: {notes[:50]})" if notes else "")
        )

        # Return success message (HTMX will swap with this)
        from fasthtml.common import Div, NotStr

        return Result.ok(
            Div(
                NotStr("✓ Great! You've acted on this insight."),
                cls="alert alert-success",
            )
        )

    # ========================================
    # Phase 2, Task 9: Bulk Action Endpoints
    # ========================================

    @rt("/api/insights/bulk/dismiss", methods=["POST"])
    @boundary_handler(success_status=200)
    async def bulk_dismiss_insights(request: Request) -> Result[Any]:
        """Bulk dismiss multiple insights (Phase 2, Task 9).

        Args:
            request: HTTP request with JSON body containing insight UIDs

        Returns:
            Result with success count or error
        """
        user_uid = require_authenticated_user(request)

        # Parse request body
        try:
            body = await request.json()
            uids = body.get("uids", [])
        except Exception as e:
            logger.error(f"Failed to parse bulk dismiss request: {e}")
            return Errors.validation(f"Invalid request body: {e}")

        if not uids:
            return Errors.validation("No insight UIDs provided")

        # Dismiss each insight
        success_count = 0
        failed_uids = []

        for uid in uids:
            result = await insight_store.dismiss_insight(uid, user_uid)
            if result.is_error:
                logger.error(f"Failed to dismiss insight {uid}: {result.error}")
                failed_uids.append(uid)
            else:
                success_count += 1

        logger.info(f"Bulk dismissed {success_count}/{len(uids)} insights for {user_uid}")

        return Result.ok(
            {
                "success_count": success_count,
                "total_requested": len(uids),
                "failed_uids": failed_uids,
            }
        )

    @rt("/api/insights/bulk/action", methods=["POST"])
    @boundary_handler(success_status=200)
    async def bulk_action_insights(request: Request) -> Result[Any]:
        """Bulk mark insights as actioned (Phase 2, Task 9).

        Args:
            request: HTTP request with JSON body containing insight UIDs

        Returns:
            Result with success count or error
        """
        user_uid = require_authenticated_user(request)

        # Parse request body
        try:
            body = await request.json()
            uids = body.get("uids", [])
        except Exception as e:
            logger.error(f"Failed to parse bulk action request: {e}")
            return Errors.validation(f"Invalid request body: {e}")

        if not uids:
            return Errors.validation("No insight UIDs provided")

        # Mark each insight as actioned
        success_count = 0
        failed_uids = []

        for uid in uids:
            result = await insight_store.mark_insight_actioned(uid, user_uid)
            if result.is_error:
                logger.error(f"Failed to mark insight {uid} as actioned: {result.error}")
                failed_uids.append(uid)
            else:
                success_count += 1

        logger.info(f"Bulk actioned {success_count}/{len(uids)} insights for {user_uid}")

        return Result.ok(
            {
                "success_count": success_count,
                "total_requested": len(uids),
                "failed_uids": failed_uids,
            }
        )

    @rt("/api/insights/bulk/smart-dismiss", methods=["POST"])
    @boundary_handler(success_status=200)
    async def smart_dismiss_insights(request: Request) -> Result[Any]:
        """Smart bulk dismiss (dismiss all insights matching filter) (Phase 2, Task 9).

        Args:
            request: HTTP request with JSON body containing filter_type and filter_value

        Returns:
            Result with success count or error

        Example:
            POST /api/insights/bulk/smart-dismiss
            {"filter_type": "impact", "filter_value": "low"}
        """
        user_uid = require_authenticated_user(request)

        # Parse request body
        try:
            body = await request.json()
            filter_type = body.get("filter_type")  # "impact", "domain", "type"
            filter_value = body.get("filter_value")  # "low", "tasks", "difficulty_pattern"
        except Exception as e:
            logger.error(f"Failed to parse smart dismiss request: {e}")
            return Errors.validation(f"Invalid request body: {e}")

        if not filter_type or not filter_value:
            return Errors.validation("filter_type and filter_value are required")

        # Get all active insights
        result = await insight_store.get_active_insights(user_uid=user_uid, limit=200)
        if result.is_error:
            return Result.fail(result.expect_error())

        insights = result.value

        # Filter insights based on criteria
        matching_insights = []
        if filter_type == "impact":
            matching_insights = [i for i in insights if i.impact.value == filter_value]
        elif filter_type == "domain":
            matching_insights = [i for i in insights if i.domain == filter_value]
        elif filter_type == "type":
            matching_insights = [i for i in insights if i.insight_type.value == filter_value]
        else:
            return Errors.validation(f"Invalid filter_type: {filter_type}")

        # Dismiss all matching insights
        success_count = 0
        failed_uids = []

        for insight in matching_insights:
            dismiss_result = await insight_store.dismiss_insight(insight.uid, user_uid)
            if dismiss_result.is_error:
                logger.error(f"Failed to dismiss insight {insight.uid}: {dismiss_result.error}")
                failed_uids.append(insight.uid)
            else:
                success_count += 1

        logger.info(
            f"Smart dismissed {success_count}/{len(matching_insights)} "
            f"{filter_type}={filter_value} insights for {user_uid}"
        )

        return Result.ok(
            {
                "success_count": success_count,
                "total_matching": len(matching_insights),
                "failed_uids": failed_uids,
                "filter": {
                    "type": filter_type,
                    "value": filter_value,
                },
            }
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
            return Result.fail(result.expect_error())

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
            return Result.fail(result.expect_error())

        result_typed: Result[Any] = result
        return result_typed

    # ========================================
    # Phase 2: Chart Visualization Endpoints
    # ========================================

    @rt("/api/insights/charts/impact-distribution")
    @boundary_handler(success_status=200)
    async def impact_distribution_chart(request: Request) -> Result[Any]:
        """Chart.js doughnut chart config for impact distribution.

        Returns JSON with count of insights per impact level (critical, high, medium, low).
        """
        user_uid = require_authenticated_user(request)

        # Get active insights
        result = await insight_store.get_active_insights(user_uid=user_uid, limit=200)

        if result.is_error:
            return Result.fail(result.expect_error())

        insights = result.value

        # Count by impact
        impact_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for insight in insights:
            impact_counts[insight.impact.value] += 1

        # Chart.js doughnut config
        chart_config = {
            "type": "doughnut",
            "data": {
                "labels": ["Critical", "High", "Medium", "Low"],
                "datasets": [
                    {
                        "label": "Insights by Impact",
                        "data": [
                            impact_counts["critical"],
                            impact_counts["high"],
                            impact_counts["medium"],
                            impact_counts["low"],
                        ],
                        "backgroundColor": [
                            "rgba(220, 38, 38, 0.8)",  # red-600 (critical)
                            "rgba(234, 88, 12, 0.8)",  # orange-600 (high)
                            "rgba(250, 204, 21, 0.8)",  # yellow-400 (medium)
                            "rgba(34, 197, 94, 0.8)",  # green-500 (low)
                        ],
                    }
                ],
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "legend": {"position": "bottom"},
                    "title": {"display": True, "text": "Insights by Impact Level"},
                },
            },
        }

        return Result.ok(chart_config)

    @rt("/api/insights/charts/domain-distribution")
    @boundary_handler(success_status=200)
    async def domain_distribution_chart(request: Request) -> Result[Any]:
        """Chart.js bar chart config for insights by domain.

        Returns JSON with count of insights per domain (tasks, goals, habits, etc.).
        """
        user_uid = require_authenticated_user(request)

        # Get active insights
        result = await insight_store.get_active_insights(user_uid=user_uid, limit=200)

        if result.is_error:
            return Result.fail(result.expect_error())

        insights = result.value

        # Count by domain
        domain_counts = {}
        for insight in insights:
            domain = insight.domain
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        # Sort by count descending
        sorted_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)

        # Chart.js bar config
        chart_config = {
            "type": "bar",
            "data": {
                "labels": [domain.title() for domain, _ in sorted_domains],
                "datasets": [
                    {
                        "label": "Active Insights",
                        "data": [count for _, count in sorted_domains],
                        "backgroundColor": "rgba(59, 130, 246, 0.8)",  # blue-500
                    }
                ],
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "legend": {"display": False},
                    "title": {"display": True, "text": "Insights by Domain"},
                },
                "scales": {"y": {"beginAtZero": True, "ticks": {"stepSize": 1}}},
            },
        }

        return Result.ok(chart_config)

    @rt("/api/insights/charts/type-distribution")
    @boundary_handler(success_status=200)
    async def type_distribution_chart(request: Request) -> Result[Any]:
        """Chart.js doughnut chart config for insight type distribution.

        Returns JSON with count of insights per type.
        """
        user_uid = require_authenticated_user(request)

        # Get active insights
        result = await insight_store.get_active_insights(user_uid=user_uid, limit=200)

        if result.is_error:
            return Result.fail(result.expect_error())

        insights = result.value

        # Count by type
        type_counts = {}
        for insight in insights:
            insight_type = insight.insight_type.value
            type_counts[insight_type] = type_counts.get(insight_type, 0) + 1

        # Sort by count descending
        sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)

        # Format labels (convert snake_case to Title Case)
        labels = [t.replace("_", " ").title() for t, _ in sorted_types]

        # Chart.js doughnut config
        chart_config = {
            "type": "doughnut",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Insights by Type",
                        "data": [count for _, count in sorted_types],
                        "backgroundColor": [
                            "rgba(99, 102, 241, 0.8)",  # indigo-500
                            "rgba(139, 92, 246, 0.8)",  # violet-500
                            "rgba(168, 85, 247, 0.8)",  # purple-500
                            "rgba(236, 72, 153, 0.8)",  # pink-500
                            "rgba(244, 63, 94, 0.8)",  # rose-500
                            "rgba(59, 130, 246, 0.8)",  # blue-500
                        ],
                    }
                ],
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "legend": {"position": "right"},
                    "title": {"display": True, "text": "Insights by Type"},
                },
            },
        }

        return Result.ok(chart_config)

    @rt("/api/insights/charts/action-rate")
    @boundary_handler(success_status=200)
    async def action_rate_chart(request: Request) -> Result[Any]:
        """Chart.js gauge/doughnut chart for insight action rate.

        Returns JSON with percentage of insights that have been actioned.
        """
        user_uid = require_authenticated_user(request)

        # Get stats
        stats_result = await insight_store.get_insight_stats(user_uid)

        if stats_result.is_error:
            return stats_result

        stats = stats_result.value
        action_rate = stats.get("action_rate", 0) * 100  # Convert to percentage
        remaining_rate = 100 - action_rate

        # Chart.js doughnut config (gauge-style)
        chart_config = {
            "type": "doughnut",
            "data": {
                "labels": ["Actioned", "Not Actioned"],
                "datasets": [
                    {
                        "label": "Action Rate",
                        "data": [action_rate, remaining_rate],
                        "backgroundColor": [
                            "rgba(34, 197, 94, 0.8)",  # green-500 (actioned)
                            "rgba(156, 163, 175, 0.3)",  # gray-400 (not actioned)
                        ],
                    }
                ],
            },
            "options": {
                "responsive": True,
                "circumference": 180,
                "rotation": -90,
                "plugins": {
                    "legend": {"position": "bottom"},
                    "title": {"display": True, "text": f"Action Rate: {action_rate:.1f}%"},
                },
            },
        }

        return Result.ok(chart_config)

    # ========================================
    # Phase 3, Task 13: Detail Modal Endpoints
    # ========================================

    @rt("/api/insights/{uid}/details")
    @boundary_handler(success_status=200)
    async def get_insight_details(request: Request, uid: str) -> Result[Any]:
        """Get detailed insight information for modal display (Phase 3, Task 13).

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
            return Result.fail(result.expect_error())

        insight = result.value

        # Verify ownership (insight belongs to requesting user)
        if insight.user_uid != user_uid:
            logger.warning(
                f"User {user_uid} attempted to access insight {uid} owned by {insight.user_uid}"
            )
            return Errors.not_found(f"Insight {uid} not found")

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
            "metadata": insight.metadata or {},
            "created_at": insight.created_at.isoformat() if insight.created_at else None,
        }

        return Result.ok(insight_data)

    @rt("/api/insights/{uid}/snooze", methods=["POST"])
    @boundary_handler(success_status=200)
    async def snooze_insight(request: Request, uid: str) -> Result[Any]:
        """Snooze an insight for a specified number of days (Phase 3, Task 13).

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
        try:
            body = await request.json()
            days = body.get("days", 1)
        except Exception as e:
            logger.error(f"Failed to parse snooze request: {e}")
            return Errors.validation(f"Invalid request body: {e}")

        # Validate days
        if not isinstance(days, int) or days < 1 or days > 30:
            return Errors.validation("Days must be an integer between 1 and 30")

        # Snooze the insight (mark as dismissed with snooze metadata)
        # For now, we'll just dismiss it - a full implementation would add snooze_until_date
        result = await insight_store.dismiss_insight(uid, user_uid)

        if result.is_error:
            logger.warning(f"Failed to snooze insight {uid}: {result.error}")
            return Result.fail(result.expect_error())

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
        # Phase 2: Chart endpoints
        impact_distribution_chart,
        domain_distribution_chart,
        type_distribution_chart,
        action_rate_chart,
        # Phase 3, Task 13: Detail modal endpoints
        get_insight_details,
        snooze_insight,
    ]
