"""
Analytics Dashboard UI Routes
==============================

UI routes for statistical domain analytics. All HTML construction
delegated to ui/analytics/.

Uses StatCard/StatsGrid from ui/patterns/stats_grid.py for all metric displays.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.services.analytics_service import AnalyticsService

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from core.config.settings import get_settings
from core.models.enums import AnalyticsDomain
from core.utils.logging import get_logger
from ui.analytics import (
    render_analytics_dashboard,
    render_analytics_result,
    render_life_path_alignment_dashboard,
    render_period_fields,
    render_weekly_life_summary,
)
from ui.patterns.error_banner import render_error_banner, render_inline_error

logger = get_logger("skuel.routes.analytics.ui")


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


@dataclass
class PeriodParams:
    """Typed parameters for period selection."""

    period: str
    start_date: str
    end_date: str


def parse_period_params(request: Request) -> PeriodParams:
    """Extract period parameters from request query params."""
    return PeriodParams(
        period=request.query_params.get("period", ""),
        start_date=request.query_params.get("start_date", ""),
        end_date=request.query_params.get("end_date", ""),
    )


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_analytics_ui_routes(
    app: FastHTMLApp, rt: RouteDecorator, analytics_service: "AnalyticsService"
) -> None:
    """Register analytics UI routes."""

    @app.get("/ui/analytics")
    def analytics_dashboard(
        request: Request,
    ) -> Any:
        """Analytics dashboard."""
        require_authenticated_user(request)
        return render_analytics_dashboard(request)

    @app.get("/ui/analytics/period-fields")
    def get_period_fields(
        request: Request,
    ) -> Any:
        """Get dynamic period input fields."""
        require_authenticated_user(request)
        params = parse_period_params(request)
        return render_period_fields(params.period)

    @app.get("/ui/analytics/view")
    async def view_analytics(request: Request) -> Any:
        """Generate and view analytics."""
        user_uid = require_authenticated_user(request)
        try:
            analytics_domain_str = request.query_params.get("analytics_domain", "tasks")
            params = parse_period_params(request)

            analytics_domain = AnalyticsDomain(analytics_domain_str)
            today = date.today()

            if params.period == "week_current":
                week_start = today - timedelta(days=today.weekday())
                result = await analytics_service.generate_weekly_report(
                    user_uid, analytics_domain, week_start
                )
            elif params.period == "week_last":
                last_week_start = today - timedelta(days=today.weekday() + 7)
                result = await analytics_service.generate_weekly_report(
                    user_uid, analytics_domain, last_week_start
                )
            elif params.period == "month_current":
                result = await analytics_service.generate_monthly_report(
                    user_uid, analytics_domain, today.year, today.month
                )
            elif params.period == "month_last":
                first_of_month = today.replace(day=1)
                last_month_end = first_of_month - timedelta(days=1)
                result = await analytics_service.generate_monthly_report(
                    user_uid,
                    analytics_domain,
                    last_month_end.year,
                    last_month_end.month,
                )
            elif params.period == "year_current":
                result = await analytics_service.generate_yearly_report(
                    user_uid, analytics_domain, today.year
                )
            elif params.period == "custom":
                if not params.start_date or not params.end_date:
                    return render_inline_error("Custom range requires both start and end dates.")
                try:
                    start = date.fromisoformat(params.start_date)
                    end = date.fromisoformat(params.end_date)
                except ValueError:
                    return render_inline_error("Invalid date format. Use YYYY-MM-DD.")
                if start > end:
                    return render_inline_error("Start date must be before end date.")
                result = await analytics_service.generate_report(
                    user_uid, analytics_domain, start, end
                )
            else:
                return render_inline_error("Invalid period selection")

            if result.is_error:
                return render_inline_error(f"Error generating analytics: {result.error}")

            return render_analytics_result(result.value)

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error viewing analytics: {e}")
            return render_error_banner(
                "Error generating analytics",
                technical_details=str(e),
                show_details=get_settings().application.debug,
            )

    @app.get("/ui/analytics/life-path-alignment")
    async def life_path_alignment_ui(request: Request) -> Any:
        """Render Life Path alignment dashboard UI."""
        user_uid = require_authenticated_user(request)

        try:
            result = await analytics_service.calculate_life_path_alignment(user_uid)
            if result.is_error:
                return render_inline_error(f"Error: {result.expect_error().message}")

            return render_life_path_alignment_dashboard(result.value)

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error rendering Life Path alignment: {e}")
            return render_error_banner(
                "Error loading Life Path alignment",
                technical_details=str(e),
                show_details=get_settings().application.debug,
            )

    @app.get("/ui/analytics/weekly-life-summary")
    async def weekly_life_summary_ui(request: Request) -> Any:
        """Render weekly life summary UI (ALL layers)."""
        user_uid = require_authenticated_user(request)
        start_date_str = request.query_params.get("start_date")

        try:
            if start_date_str:
                try:
                    start_date = date.fromisoformat(start_date_str)
                except ValueError:
                    return render_inline_error("Invalid date format. Use YYYY-MM-DD.")

                result = await analytics_service.generate_weekly_life_summary(
                    user_uid, week_start=start_date
                )
            else:
                result = await analytics_service.generate_weekly_life_summary(user_uid)

            if result.is_error:
                return render_inline_error(f"Error: {result.expect_error().message}")

            return render_weekly_life_summary(result.value)

        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error rendering weekly life summary: {e}")
            return render_error_banner(
                "Error loading weekly life summary",
                technical_details=str(e),
                show_details=get_settings().application.debug,
            )

    logger.info("Analytics UI routes registered (including Life Path + cross-layer)")


__all__ = ["create_analytics_ui_routes"]
