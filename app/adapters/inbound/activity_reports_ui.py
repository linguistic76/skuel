"""
Activity Reports UI Routes — ActivityReport Pages
===================================================

Routes for viewing and requesting activity reports.

Routes:
- GET /activity-reports — Activity reports list page
- GET /activity-reports/detail — Activity report detail view
- GET /submit-activity-report — On-demand activity report request form
- GET /reports/activity-list — HTMX fragment: activity reports with time filter
- GET /reports/progress-list — HTMX fragment: progress reports

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from fasthtml.common import (
    Div,
    P,
)
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import RouteDecorator, RouteList
from core.models.enums.entity_enums import EntityType
from core.utils.logging import get_logger
from ui.buttons import ButtonLink, ButtonT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.patterns.error_banner import render_error_banner
from ui.patterns.generate_report import (
    render_activity_report_request_card,
    render_recent_reports_section,
)
from ui.patterns.page_header import PageHeader
from ui.submissions.report import (
    render_activity_report_detail,
    render_activity_report_list,
    render_progress_report_list,
    render_time_period_filter,
)

logger = get_logger("skuel.routes.activity_reports")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_activity_reports_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    submissions_service: Any = None,
    activity_report_service: Any = None,
) -> RouteList:
    """Create /activity-reports UI routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        submissions_service: SubmissionsService for progress report queries
        activity_report_service: ActivityReportService for activity feedback history
    """

    # ========================================================================
    # ACTIVITY REPORTS PAGE
    # ========================================================================

    @rt("/activity-reports")
    async def activity_reports_page(request: Request) -> Any:
        """Activity feedback — AI and scheduled activity reports."""
        require_authenticated_user(request)

        content = Div(
            PageHeader(
                "Activity Reports",
                subtitle="AI and scheduled feedback on your activity patterns",
                actions=ButtonLink(
                    "Submit Activity Report",
                    href="/submit-activity-report",
                    variant=ButtonT.secondary,
                    size=Size.sm,
                ),
            ),
            render_time_period_filter(),
            Div(
                P("Loading activity reports...", cls="text-center text-muted-foreground"),
                id="activity-feedback-list",
                cls="mt-2",
                **{
                    "hx-get": "/reports/activity-list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
        )
        return await BasePage(
            content=content,
            title="Activity Reports",
            request=request,
            active_page="activity-reports",
        )

    # ========================================================================
    # SUBMIT ACTIVITY REPORT — on-demand activity report request
    # ========================================================================

    @rt("/submit-activity-report")
    async def submit_activity_report_page(request: Request) -> Any:
        """Submit a request to generate an activity report."""
        require_authenticated_user(request)

        content = Div(
            PageHeader(
                "Submit Activity Report Request",
                subtitle="Request an on-demand activity report across your domains",
            ),
            render_activity_report_request_card(),
            render_recent_reports_section(),
        )
        return await BasePage(
            content=content,
            title="Submit Activity Report",
            request=request,
            active_page="activity-reports",
        )

    # ========================================================================
    # ACTIVITY REPORT DETAIL PAGE
    # ========================================================================

    @rt("/activity-reports/detail")
    async def activity_report_detail(request: Request) -> Any:
        """Activity report detail view with domain breakdown and annotation."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "").strip()

        if not uid:
            return await BasePage(
                content=Div(render_error_banner("Report UID is required")),
                title="Activity Report",
                request=request,
                active_page="activity-reports",
            )

        if not activity_report_service:
            return await BasePage(
                content=Div(render_error_banner("Activity report service unavailable")),
                title="Activity Report",
                request=request,
                active_page="activity-reports",
            )

        # Fetch the report from history (service returns list, find by uid)
        history_result = await activity_report_service.get_history(subject_uid=user_uid, limit=100)
        if history_result.is_error:
            return await BasePage(
                content=Div(
                    render_error_banner("Failed to load report", str(history_result.error))
                ),
                title="Activity Report",
                request=request,
                active_page="activity-reports",
            )

        report = None
        for r in history_result.value or []:
            if getattr(r, "uid", None) == uid:
                report = r
                break

        if not report:
            return await BasePage(
                content=Div(render_error_banner("Report not found")),
                title="Activity Report",
                request=request,
                active_page="activity-reports",
            )

        # Extract snapshot, intelligence, and comparison from metadata
        metadata = getattr(report, "metadata", None) or {}
        snapshot = metadata.get("snapshot") if isinstance(metadata, dict) else None
        intelligence = metadata.get("intelligence") if isinstance(metadata, dict) else None
        comparison = metadata.get("comparison") if isinstance(metadata, dict) else None

        content = Div(
            render_activity_report_detail(
                report, snapshot=snapshot, intelligence=intelligence, comparison=comparison
            )
        )
        return await BasePage(
            content=content,
            title=getattr(report, "title", "Activity Report"),
            request=request,
            active_page="activity-reports",
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/reports/activity-list")
    async def activity_report_list_fragment(request: Request) -> Any:
        """HTMX fragment: activity reports with optional time_period filter."""
        try:
            user_uid = require_authenticated_user(request)
            if not activity_report_service:
                return Div(
                    render_error_banner(
                        "Activity feedback service unavailable", severity="warning"
                    ),
                    id="activity-feedback-list",
                )
            time_period = request.query_params.get("time_period", "")
            result = await activity_report_service.get_history(subject_uid=user_uid, limit=50)
            if result.is_error:
                logger.error(f"Error loading activity feedback: {result.error}")
                return Div(
                    render_error_banner("Failed to load activity feedback", str(result.error)),
                    id="activity-feedback-list",
                )
            reports = result.value or []
            if time_period:
                reports = [r for r in reports if getattr(r, "time_period", None) == time_period]
            return render_activity_report_list(reports)
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading activity feedback list: {e}", exc_info=True)
            return Div(
                render_error_banner("Error loading activity feedback", str(e)),
                id="activity-feedback-list",
            )

    @rt("/reports/progress-list")
    async def progress_list_fragment(request: Request) -> Any:
        """HTMX fragment: progress reports."""
        try:
            user_uid = require_authenticated_user(request)
            if not submissions_service:
                return Div(
                    render_error_banner("Submissions service unavailable"),
                    id="progress-list",
                )
            result = await submissions_service.list_submissions(
                user_uid=user_uid,
                entity_type=EntityType.ACTIVITY_REPORT,
                limit=10,
            )
            if result.is_error:
                logger.error(f"Error loading progress reports: {result.error}")
                return Div(
                    render_error_banner("Failed to load progress reports", str(result.error)),
                    id="progress-list",
                )
            return render_progress_report_list(result.value or [])
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading progress report list: {e}", exc_info=True)
            return Div(
                render_error_banner("Error loading progress reports", str(e)),
                id="progress-list",
            )

    logger.info(
        "Activity Reports UI routes created "
        "(/activity-reports, /activity-reports/detail, /submit-activity-report)"
    )

    return [
        activity_reports_page,
        submit_activity_report_page,
        activity_report_detail,
        activity_report_list_fragment,
        progress_list_fragment,
    ]
