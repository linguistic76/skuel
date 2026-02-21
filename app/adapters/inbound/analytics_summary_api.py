"""
Analytics Summary API - Read-Only Analytics Endpoints
=====================================================

REST API for Analytics meta-analysis (Layer 3).

Version: 1.0.0 (October 24, 2025)

This provides analytical endpoints for:
- Life Path alignment tracking (Phase 1)
- Cross-layer life summaries (Phase 3)
- Pattern detection across layers

All endpoints are read-only (no CRUD operations).
Analytics synthesize data from all layers.

Routes:
- GET /api/analytics/life-path-alignment
- GET /api/analytics/weekly-life-summary
- GET /api/analytics/monthly-life-review
- GET /api/analytics/quarterly-progress
- GET /api/analytics/yearly-review
- GET /api/analytics/cross-domain-patterns
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.boundary import boundary_handler
from core.auth import require_authenticated_user
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.analytics_service import AnalyticsService


def create_analytics_summary_api_routes(app, rt, analytics_service: "AnalyticsService"):
    """
    Create Analytics Summary API routes (read-only analytics).

    Args:
        app: FastHTML application instance
        rt: Route decorator
        analytics_service: AnalyticsService facade instance
    """

    # ========================================================================
    # LIFE PATH ALIGNMENT TRACKING (Phase 1)
    # ========================================================================

    @rt("/api/analytics/life-path-alignment")
    @boundary_handler()
    async def get_life_path_alignment_route(request: Request) -> Result[dict[str, Any]]:
        """
        Get user's alignment with their ultimate life goal.

        Query params:
            user_uid: User identifier (required)

        Returns:
            Result containing comprehensive alignment analysis:
            - alignment_score: 0.0-1.0
            - embodied_knowledge: Count of mastered knowledge
            - theoretical_knowledge: Count of unmastered knowledge
            - domain_contributions: Which domains drive alignment
            - gaps: Knowledge units needing practice
            - recommendations: Actionable next steps
        """
        user_uid = require_authenticated_user(request)

        return await analytics_service.calculate_life_path_alignment(user_uid)

    # ========================================================================
    # CROSS-LAYER LIFE SUMMARIES (Phase 3)
    # ========================================================================

    @rt("/api/analytics/weekly-life-summary")
    @boundary_handler()
    async def get_weekly_life_summary_route(request: Request) -> Result[dict[str, Any]]:
        """
        Get weekly life summary across ALL 4 layers.

        Query params:
            user_uid: User identifier (required)
            start_date: Week start date (optional, defaults to current week Monday)

        Returns:
            Result containing:
            - layer_1_activities: 7 domain metrics
            - layer_0_knowledge: Substance + curriculum metrics
            - layer_2_reflection: Journal patterns
            - cross_layer_insights: Synthesis across layers
            - summary: Human-readable text
        """
        user_uid = require_authenticated_user(request)

        # Parse start_date or default to current week Monday
        start_date_str = request.query_params.get("start_date")
        if start_date_str:
            try:
                start_date = date.fromisoformat(start_date_str)
            except ValueError:
                return Result.fail(
                    Errors.validation(
                        "start_date must be ISO format (YYYY-MM-DD)",
                        field="start_date",
                        value=start_date_str,
                    )
                )
        else:
            # Default to current week Monday
            today = date.today()
            start_date = today - timedelta(days=today.weekday())

        return await analytics_service.generate_weekly_life_summary(user_uid, week_start=start_date)

    @rt("/api/analytics/monthly-life-review")
    @boundary_handler()
    async def get_monthly_life_review_route(request: Request) -> Result[dict[str, Any]]:
        """
        Get monthly life review across ALL 4 layers.

        Query params:
            user_uid: User identifier (required)
            year: Year (required)
            month: Month 1-12 (required)

        Returns:
            Result containing weekly summary plus:
            - monthly_trends: Completion trends over month
            - goal_progress_analysis: Goal achievement details
        """
        user_uid = require_authenticated_user(request)
        year_str = request.query_params.get("year")
        month_str = request.query_params.get("month")

        if not year_str or not month_str:
            return Result.fail(Errors.validation("year and month are required", field="year,month"))

        try:
            year = int(year_str)
            month = int(month_str)

            if month < 1 or month > 12:
                return Result.fail(
                    Errors.validation("month must be between 1 and 12", field="month", value=month)
                )

        except ValueError:
            return Result.fail(
                Errors.validation("year and month must be integers", field="year,month")
            )

        return await analytics_service.generate_monthly_life_review(user_uid, year, month)

    @rt("/api/analytics/quarterly-progress")
    @boundary_handler()
    async def get_quarterly_progress_route(request: Request) -> Result[dict[str, Any]]:
        """
        Get quarterly progress analytics across ALL 4 layers.

        Query params:
            user_uid: User identifier (required)
            year: Year (required)
            quarter: Quarter 1-4 (required)

        Returns:
            Result containing monthly review plus:
            - strategic_insights: Long-term assessment
            - quarter_summary: Strategic narrative
        """
        user_uid = require_authenticated_user(request)
        year_str = request.query_params.get("year")
        quarter_str = request.query_params.get("quarter")

        if not year_str or not quarter_str:
            return Result.fail(
                Errors.validation("year and quarter are required", field="year,quarter")
            )

        try:
            year = int(year_str)
            quarter = int(quarter_str)

            if quarter < 1 or quarter > 4:
                return Result.fail(
                    Errors.validation(
                        "quarter must be between 1 and 4", field="quarter", value=quarter
                    )
                )

        except ValueError:
            return Result.fail(
                Errors.validation("year and quarter must be integers", field="year,quarter")
            )

        return await analytics_service.generate_quarterly_progress(user_uid, year, quarter)

    @rt("/api/analytics/yearly-review")
    @boundary_handler()
    async def get_yearly_review_route(request: Request) -> Result[dict[str, Any]]:
        """
        Get yearly review across ALL 4 layers.

        Query params:
            user_uid: User identifier (required)
            year: Year (required)

        Returns:
            Result containing quarterly progress plus:
            - year_achievements: Annual accomplishments
            - growth_opportunities: Areas for improvement
            - year_summary: Annual retrospective
        """
        user_uid = require_authenticated_user(request)
        year_str = request.query_params.get("year")

        if not year_str:
            return Result.fail(Errors.validation("year is required", field="year"))

        try:
            year = int(year_str)
        except ValueError:
            return Result.fail(
                Errors.validation("year must be an integer", field="year", value=year_str)
            )

        return await analytics_service.generate_yearly_review(user_uid, year)

    # ========================================================================
    # PATTERN DETECTION
    # ========================================================================

    @rt("/api/analytics/cross-domain-patterns")
    @boundary_handler()
    async def get_cross_domain_patterns_route(request: Request) -> Result[dict[str, Any]]:
        """
        Detect patterns and relationships across domains.

        Query params:
            user_uid: User identifier (required)
            start_date: Period start (ISO format, required)
            end_date: Period end (ISO format, required)

        Returns:
            Result containing pattern analysis:
            - expense_productivity_correlation
            - choice_principle_alignment
            - goal_habit_support
            - time_allocation
            - domain_balance
        """
        user_uid = require_authenticated_user(request)
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if not start_date_str or not end_date_str:
            return Result.fail(
                Errors.validation(
                    "start_date and end_date are required", field="start_date,end_date"
                )
            )

        try:
            start_date = date.fromisoformat(start_date_str)
            end_date = date.fromisoformat(end_date_str)
        except ValueError as e:
            return Result.fail(
                Errors.validation(
                    f"Dates must be ISO format (YYYY-MM-DD): {e!s}", field="start_date,end_date"
                )
            )

        if end_date < start_date:
            return Result.fail(
                Errors.validation("end_date must be after start_date", field="end_date")
            )

        return await analytics_service.detect_cross_domain_patterns(user_uid, start_date, end_date)

    return []
