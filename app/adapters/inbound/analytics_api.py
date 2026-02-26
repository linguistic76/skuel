"""
Analytics API Routes
================================

Event-driven analytics API for querying live metrics.


- Exposes analytics data from CrossDomainAnalyticsService
- Real-time metrics via Neo4j + in-memory caching
- Event-driven updates (no polling needed)

Endpoints:
- GET /api/analytics/learning-velocity
- GET /api/analytics/spending-patterns
- GET /api/analytics/mood-analysis
- GET /api/analytics/productivity
- GET /api/analytics/habit-consistency
- GET /api/analytics/dashboard (combined metrics)

Version: 1.0.0
Date: 2025-11-06
"""

from datetime import datetime

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
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

        days_back = int(request.query_params.get("days_back", 30))

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

    @rt("/api/analytics/spending-patterns")
    @boundary_handler()
    async def spending_patterns(request):
        """
        Get spending pattern analysis for user.

        Query params:
            user_uid: User identifier (required)
            days_back: Number of days to analyze (default: 30)

        Returns:
            SpendingPatternAnalysis with:
            - spending_by_domain (category breakdown)
            - top_spending_domain
            - avg_expense_amount
            - expense_frequency_per_week
        """
        user_uid = require_authenticated_user(request)

        days_back = int(request.query_params.get("days_back", 30))

        result = await analytics.get_spending_patterns(user_uid, days_back)

        if result.is_ok:
            analysis = result.value
            return Result.ok(
                {
                    "user_uid": analysis.user_uid,
                    "period_days": analysis.period_days,
                    "spending_by_domain": analysis.spending_by_domain,
                    "top_spending_domain": analysis.top_spending_domain,
                    "avg_expense_amount": analysis.avg_expense_amount,
                    "expense_frequency_per_week": analysis.expense_frequency_per_week,
                    "highest_expense_day": analysis.highest_expense_day,
                    "generated_at": datetime.now().isoformat(),
                }
            )

        return result

    # ========================================================================
    # MOOD ANALYSIS ANALYTICS
    # ========================================================================

    @rt("/api/analytics/mood-analysis")
    @boundary_handler()
    async def mood_analysis(request):
        """
        Get journal mood analysis for user.

        Query params:
            user_uid: User identifier (required)
            days_back: Number of days to analyze (default: 30)

        Returns:
            JournalMoodAnalysis with:
            - average_mood (0.0 to 1.0)
            - mood_trend (improving/stable/declining)
            - most_common_themes
            - entries_per_week
            - longest_streak
        """
        user_uid = require_authenticated_user(request)

        days_back = int(request.query_params.get("days_back", 30))

        result = await analytics.get_mood_analysis(user_uid, days_back)

        if result.is_ok:
            analysis = result.value
            return Result.ok(
                {
                    "user_uid": analysis.user_uid,
                    "period_days": analysis.period_days,
                    "average_mood": analysis.average_mood,
                    "mood_trend": analysis.mood_trend,
                    "most_common_themes": analysis.most_common_themes,
                    "entries_per_week": analysis.entries_per_week,
                    "longest_streak": analysis.longest_streak,
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
        Get productivity analytics from task completions.

        Query params:
            user_uid: User identifier (required)

        Returns:
            ProductivityAnalytics with:
            - tasks_completed (total count)
            - first_completion_at
            - last_completion_at
            - completion_velocity (tasks per week)
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
            - total_completions
            - first_completion_at
            - last_completion_at
            - consistency_score
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
        """
        Get combined analytics dashboard for user.

        Query params:
            user_uid: User identifier (required)
            days_back: Number of days to analyze (default: 30)

        Returns:
            Combined dashboard with:
            - learning_velocity
            - productivity_metrics
            - habit_consistency
            - spending_patterns
            - mood_analysis
        """
        user_uid = require_authenticated_user(request)

        days_back = int(request.query_params.get("days_back", 30))

        # Gather all analytics (parallel queries would be better)
        learning_result = await analytics.get_learning_velocity(user_uid, days_back)
        spending_result = await analytics.get_spending_patterns(user_uid, days_back)
        mood_result = await analytics.get_mood_analysis(user_uid, days_back)

        dashboard = {
            "user_uid": user_uid,
            "period_days": days_back,
            "generated_at": datetime.now().isoformat(),
            "learning_velocity": None,
            "spending_patterns": None,
            "mood_analysis": None,
        }

        if learning_result.is_ok:
            v = learning_result.value
            dashboard["learning_velocity"] = {
                "kus_mastered_per_week": v.kus_mastered_per_week,
                "paths_completed": v.paths_completed,
                "velocity_trend": v.velocity_trend,
            }

        if spending_result.is_ok:
            s = spending_result.value
            dashboard["spending_patterns"] = {
                "top_spending_domain": s.top_spending_domain,
                "avg_expense_amount": s.avg_expense_amount,
                "expense_frequency_per_week": s.expense_frequency_per_week,
            }

        if mood_result.is_ok:
            m = mood_result.value
            dashboard["mood_analysis"] = {
                "average_mood": m.average_mood,
                "mood_trend": m.mood_trend,
                "entries_per_week": m.entries_per_week,
            }

        return Result.ok(dashboard)

    logger.info("✅ Analytics API routes registered (6 endpoints)")
