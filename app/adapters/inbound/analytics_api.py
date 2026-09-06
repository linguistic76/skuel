"""
Analytics API Routes
================================

Event-driven analytics API for querying live metrics.


- Exposes analytics data from CrossDomainAnalyticsService
- Real-time metrics via Neo4j + in-memory caching
- Event-driven updates (no polling needed)

Endpoints:
- GET /api/analytics/learning-velocity
- GET /api/analytics/productivity
- GET /api/analytics/habit-consistency
- GET /api/analytics/dashboard (combined metrics)

Version: 1.0.0
Date: 2025-11-06
"""

from datetime import datetime

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import parse_int_query_param
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
        Get learning velocity metrics for user.

        Query params:
            user_uid: User identifier (required)
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

        days_back = parse_int_query_param(
            request.query_params, "days_back", 30, minimum=1, maximum=365
        )

        result = await analytics.get_learning_velocity(user_uid, days_back)

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
    # SPENDING PATTERNS ANALYTICS
    # ========================================================================
    # REMOVED (ADR-052 Phase 5): /api/analytics/spending-patterns — the native
    # expense module was demolished, so there is no spending data to aggregate.

    # ========================================================================
    # PRODUCTIVITY ANALYTICS
    # ========================================================================

    @rt("/api/analytics/productivity")
    @boundary_handler()
    async def productivity_metrics(request):
        """
        Get productivity analytics from task completions.

        Query params:
            user_uid: User identifier (required)

        Returns:
            ProductivityAnalytics with:
            - tasks_completed (tasks currently in COMPLETED)
            - first_completion_at
            - last_completion_at
            - velocity_window_days / tasks_completed_in_window
            - completion_velocity (tasks per week over that trailing window)

        ``completion_velocity`` is a rate over a fixed recent window, not a
        lifetime average, so the window and its numerator are served alongside
        it: a bare tasks/week figure cannot be interpreted without them.

        ``tasks_completed`` and ``tasks_completed_in_window`` are both derived
        from the graph on one read — the tasks the user currently owns in
        COMPLETED, and the subset stamped inside the window — so the window is
        a subset of the total by construction. Only the two stamps come from
        the analytics node, so a user with no stamped completion yet — every
        one of theirs predating the handler, or its announcement lost — has real
        counts and ``null`` stamps until ``./dev backfill-productivity-stamps``
        runs. A *later* lost announcement is not that case and not repairable
        here: the counts stay current while ``last_completion_at`` goes stale
        (``docs/roadmap/ingest-transition-obligation-durability.md``). See
        ``CrossDomainAnalyticsService.get_productivity_metrics``.
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
        Get habit consistency analytics.

        Query params:
            user_uid: User identifier (required)

        Returns:
            HabitAnalytics with:
            - total_completions (cumulative, event-maintained)
            - first_completion_at
            - last_completion_at
            - consistency_window_days / completions_in_window
            - consistency_score (completions per week over that trailing window)

        ``consistency_score`` is a rate over a fixed recent window, not a
        lifetime average, so the window and its numerator are served alongside
        it: a bare completions/week figure cannot be interpreted without them.

        ``total_completions`` is the event-maintained cumulative count while
        ``completions_in_window`` is counted live from the completion records,
        so the second exceeding the first means the tally missed completions —
        the bulk-logging door (``HabitCompletionBulk``) publishes an event no
        analytics handler subscribes to. The score is unaffected; only the
        cumulative figures are behind. See
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

        days_back = parse_int_query_param(
            request.query_params, "days_back", 30, minimum=1, maximum=365
        )

        return await analytics.get_combined_dashboard(user_uid, days_back)

    logger.info("✅ Analytics API routes registered (4 endpoints)")
