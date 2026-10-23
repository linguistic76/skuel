"""
Analytics API Routes
================================

The signed-in user's cross-domain analytics, from CrossDomainAnalyticsService —
every figure derived from the graph on the request that asks for it.

Endpoints:
- GET /api/analytics/learning-velocity
- GET /api/analytics/productivity
- GET /api/analytics/habit-consistency
- GET /api/analytics/dashboard (combined metrics)
"""

from datetime import datetime

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import parse_int_param_strict
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


def register_analytics_routes(app, services):
    """
    Register analytics API routes.

    Args:
        app: FastHTML application
        services: Services container with cross_domain_analytics service
    """
    rt = app.route
    analytics = services.cross_domain_analytics

    # ========================================================================
    # LEARNING VELOCITY ANALYTICS
    # ========================================================================

    @rt("/api/analytics/learning-velocity")
    @boundary_handler()
    async def learning_velocity(request):
        """
        Get learning velocity metrics for the signed-in user.

        Query params:
            days_back: Number of days to analyze (default: 30)

        Returns:
            LearningVelocityMetrics with:
            - kus_mastered_per_week
            - paths_completed
            - total_learning_hours
            - velocity_trend (accelerating/steady/slowing)
            - compared_to_previous_period (% change)
        """
        user_uid = require_authenticated_user(request)

        days_back = parse_int_param_strict(
            request.query_params.get("days_back"), "days_back", 1, default=30, cap=365
        )
        if days_back.is_error:
            return Result.fail(days_back)

        result = await analytics.get_learning_velocity(user_uid, days_back.value)

        if result.is_ok:
            metrics = result.value
            return Result.ok(
                {
                    "user_uid": metrics.user_uid,
                    "period_days": metrics.period_days,
                    "kus_mastered_per_week": metrics.kus_mastered_per_week,
                    "paths_completed": metrics.paths_completed,
                    "total_learning_hours": metrics.total_learning_hours,
                    "velocity_trend": metrics.velocity_trend,
                    "compared_to_previous_period": metrics.compared_to_previous_period,
                    "generated_at": datetime.now().isoformat(),
                }
            )

        return result

    # ========================================================================
    # PRODUCTIVITY ANALYTICS
    # ========================================================================

    @rt("/api/analytics/productivity")
    @boundary_handler()
    async def productivity_metrics(request):
        """
        Get the signed-in user's productivity analytics from task completions.

        Returns:
            The productivity figures:
            - tasks_completed (tasks currently in COMPLETED)
            - first_completion_at (ISO date of the earliest completion day)
            - last_completion_at (ISO date of the latest completion day)
            - velocity_window_days / tasks_completed_in_window
            - completion_velocity (tasks per week over that trailing window)

        ``completion_velocity`` is a rate over a fixed recent window, not a
        lifetime average, so the window and its numerator are served alongside
        it: a bare tasks/week figure cannot be interpreted without them.

        Every figure is derived from the tasks the user currently owns in
        COMPLETED, on one read — so the window is a subset of the total by
        construction, and a task deleted or reopened leaves the total and both
        days. A completed task with no ``completion_date`` is in the total and
        on no day. See ``CrossDomainAnalyticsService.get_productivity_metrics``.
        """
        user_uid = require_authenticated_user(request)

        # Use analytics service (query moved from route to service layer)
        result = await analytics.get_productivity_metrics(user_uid)

        if result.is_ok:
            metrics = result.value
            first_at = metrics.get("first_completion_at")
            last_at = metrics.get("last_completion_at")

            return Result.ok(
                {
                    "user_uid": metrics["user_uid"],
                    "tasks_completed": metrics["tasks_completed"],
                    "first_completion_at": first_at.isoformat() if first_at else None,
                    "last_completion_at": last_at.isoformat() if last_at else None,
                    "velocity_window_days": metrics["velocity_window_days"],
                    "tasks_completed_in_window": metrics["tasks_completed_in_window"],
                    "completion_velocity": metrics["completion_velocity"],
                    "generated_at": datetime.now().isoformat(),
                }
            )

        return result

    # ========================================================================
    # HABIT CONSISTENCY ANALYTICS
    # ========================================================================

    @rt("/api/analytics/habit-consistency")
    @boundary_handler()
    async def habit_consistency_metrics(request):
        """
        Get the signed-in user's habit consistency analytics.

        Returns:
            The habit figures:
            - total_completions (every completion record the user owns)
            - first_completion_at (ISO instant of the earliest completion)
            - last_completion_at (ISO instant of the latest completion)
            - consistency_window_days / completions_in_window
            - consistency_score (completions per week over that trailing window)

        ``consistency_score`` is a rate over a fixed recent window, not a
        lifetime average, so the window and its numerator are served alongside
        it: a bare completions/week figure cannot be interpreted without them.

        Every figure is derived from the user's completion records on one read,
        so the window is a subset of the total by construction. See
        ``CrossDomainAnalyticsService.get_habit_consistency``.
        """
        user_uid = require_authenticated_user(request)

        # Use analytics service (query moved from route to service layer)
        result = await analytics.get_habit_consistency(user_uid)

        if result.is_ok:
            metrics = result.value
            first_at = metrics.get("first_completion_at")
            last_at = metrics.get("last_completion_at")

            return Result.ok(
                {
                    "user_uid": metrics["user_uid"],
                    "total_completions": metrics["total_completions"],
                    "first_completion_at": first_at.isoformat() if first_at else None,
                    "last_completion_at": last_at.isoformat() if last_at else None,
                    "consistency_window_days": metrics["consistency_window_days"],
                    "completions_in_window": metrics["completions_in_window"],
                    "consistency_score": metrics["consistency_score"],
                    "generated_at": datetime.now().isoformat(),
                }
            )

        return result

    # ========================================================================
    # ANALYTICS DASHBOARD (Combined Metrics)
    # ========================================================================

    @rt("/api/analytics/dashboard")
    @boundary_handler()
    async def analytics_dashboard(request):
        """Get combined analytics dashboard for user."""
        user_uid = require_authenticated_user(request)

        days_back = parse_int_param_strict(
            request.query_params.get("days_back"), "days_back", 1, default=30, cap=365
        )
        if days_back.is_error:
            return Result.fail(days_back)

        return await analytics.get_combined_dashboard(user_uid, days_back.value)

    logger.info("✅ Analytics API routes registered (4 endpoints)")
