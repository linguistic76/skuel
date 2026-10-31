"""
Analytics Dashboard UI Routes
==============================

UI routes for statistical domain analytics. All HTML construction
delegated to ui/analytics/.

Both pages belong to the Insights section (``active_page="insights"``): Insights
links them, and the navbar's Insights icon stays lit on them.

Uses StatCard/StatsGrid from ui/patterns/stats_grid.py for all metric displays.
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.analytics_service import AnalyticsService

from fasthtml.common import FT
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import ui_boundary_handler
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.route_factories import (
    parse_date_param_strict,
    parse_enum_param_strict,
    refuse_malformed,
)
from core.config.settings import get_settings
from core.models.enums import AnalyticsDomain, AnalyticsPeriod
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from ui.analytics import (
    render_analytics_dashboard,
    render_analytics_result,
    render_period_fields,
    render_weekly_life_summary,
)
from ui.layouts.base_page import BasePage
from ui.patterns.error_banner import render_error_banner

logger = get_logger("skuel.routes.analytics.ui")


# ============================================================================
# QUERY READERS
# ============================================================================
#
# The dashboard's domain and period pickers mint their values, so one that does
# not read is a crafted or stale request: a bare 400 (``refuse_malformed``), and
# HTMX leaves the slot as it was. The custom range's dates are the learner's own
# typing, so a range that does not read answers the form's banner instead.


def _read_period(request: Request) -> Result[AnalyticsPeriod]:
    """The picker's period; missing or blank is this week, the picker's first choice."""
    period = parse_enum_param_strict(request.query_params.get("period"), "period", AnalyticsPeriod)
    if period.is_error:
        return Result.fail(period)
    return Result.ok(period.value or AnalyticsPeriod.WEEK_CURRENT)


def _read_domain(request: Request) -> Result[AnalyticsDomain]:
    """The picker's domain; missing or blank is tasks, the picker's first choice."""
    domain = parse_enum_param_strict(
        request.query_params.get("analytics_domain"), "analytics_domain", AnalyticsDomain
    )
    if domain.is_error:
        return Result.fail(domain)
    return Result.ok(domain.value or AnalyticsDomain.TASKS)


def _read_custom_range(request: Request) -> Result[tuple[date, date]]:
    """The learner's typed range, or the refusal its banner shows.

    A custom range has no default: either date left blank is a refusal, as is a
    date that does not read or a start after the end (one day is a range).
    """
    start = parse_date_param_strict(
        request.query_params.get("start_date"), "start_date", default=None
    )
    end = parse_date_param_strict(request.query_params.get("end_date"), "end_date", default=None)
    if start.is_error or end.is_error:
        return Result.fail(Errors.validation("Enter each date as YYYY-MM-DD."))
    if start.value is None or end.value is None:
        return Result.fail(Errors.validation("A custom range needs both a start and an end date."))
    if start.value > end.value:
        return Result.fail(Errors.validation("The start date must be on or before the end date."))
    return Result.ok((start.value, end.value))


def _weekly_summary_page(request: Request, content: FT) -> FT:
    """The weekly life summary's shell, for its result, its refusal and its crash alike."""
    return BasePage(content, title="Weekly Life Summary", request=request, active_page="insights")


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_analytics_ui_routes(
    app: FastHTMLApp, rt: RouteDecorator, analytics_service: AnalyticsService
) -> None:
    """Register analytics UI routes."""

    @app.get("/ui/analytics")
    def analytics_dashboard(
        request: Request,
    ) -> FT:
        """Analytics dashboard."""
        require_authenticated_user(request)
        return render_analytics_dashboard(request)

    @app.get("/ui/analytics/period-fields")
    def get_period_fields(request: Request) -> FT | str | Response:
        """The date inputs the picker's period needs (only a custom range has any)."""
        require_authenticated_user(request)
        period = _read_period(request)
        if period.is_error:
            return refuse_malformed(period.expect_error())
        return render_period_fields(period.value)

    @app.get("/ui/analytics/view")
    @ui_boundary_handler("Error generating analytics")
    async def view_analytics(request: Request) -> FT | Response:
        """The report for the picked domain and period, into the dashboard's result slot."""
        user_uid = require_authenticated_user(request)
        domain = _read_domain(request)
        if domain.is_error:
            return refuse_malformed(domain.expect_error())
        period = _read_period(request)
        if period.is_error:
            return refuse_malformed(period.expect_error())

        analytics_domain = domain.value
        today = today_in(current_zone())

        match period.value:
            case AnalyticsPeriod.WEEK_CURRENT:
                week_start = today - timedelta(days=today.weekday())
                result = await analytics_service.generate_weekly_report(
                    user_uid, analytics_domain, week_start
                )
            case AnalyticsPeriod.WEEK_LAST:
                last_week_start = today - timedelta(days=today.weekday() + 7)
                result = await analytics_service.generate_weekly_report(
                    user_uid, analytics_domain, last_week_start
                )
            case AnalyticsPeriod.MONTH_CURRENT:
                result = await analytics_service.generate_monthly_report(
                    user_uid, analytics_domain, today.year, today.month
                )
            case AnalyticsPeriod.MONTH_LAST:
                last_month_end = today.replace(day=1) - timedelta(days=1)
                result = await analytics_service.generate_monthly_report(
                    user_uid, analytics_domain, last_month_end.year, last_month_end.month
                )
            case AnalyticsPeriod.YEAR_CURRENT:
                result = await analytics_service.generate_yearly_report(
                    user_uid, analytics_domain, today.year
                )
            case AnalyticsPeriod.CUSTOM:
                custom_range = _read_custom_range(request)
                if custom_range.is_error:
                    return render_error_banner(custom_range.expect_error().message)
                start, end = custom_range.value
                result = await analytics_service.generate_report(
                    user_uid, analytics_domain, start, end
                )

        if result.is_error:
            return render_error_banner(
                "Could not generate your analytics",
                technical_details=result.expect_error().message,
                show_details=get_settings().application.debug,
            )
        return render_analytics_result(result.value)

    @app.get("/ui/analytics/weekly-life-summary")
    @ui_boundary_handler("Could not load your weekly life summary", page=_weekly_summary_page)
    async def weekly_life_summary_ui(request: Request) -> FT | Response:
        """Weekly life summary page (ALL layers); ``start_date`` picks the week."""
        user_uid = require_authenticated_user(request)
        start_date = parse_date_param_strict(
            request.query_params.get("start_date"), "start_date", default=None
        )
        if start_date.is_error:
            return refuse_malformed(start_date.expect_error())

        if start_date.value:
            result = await analytics_service.generate_weekly_life_summary(
                user_uid, week_start=start_date.value
            )
        else:
            result = await analytics_service.generate_weekly_life_summary(user_uid)

        content = (
            render_error_banner(
                "Could not load your weekly life summary",
                technical_details=result.expect_error().message,
                show_details=get_settings().application.debug,
            )
            if result.is_error
            else render_weekly_life_summary(result.value)
        )
        return _weekly_summary_page(request, content)

    logger.info("Analytics UI routes registered (dashboard + weekly life summary)")


__all__ = ["create_analytics_ui_routes"]
