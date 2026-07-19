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
    Span,
)

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import ui_boundary_handler
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from core.utils.logging import get_logger
from core.utils.text_truncation import truncate_to_budget
from ui.components import ButtonT
from ui.gradebook.nav import render_gradebook_sidebar_page
from ui.learning_loop.report import (
    render_activity_report_detail,
    render_activity_report_list,
    render_progress_report_list,
    render_time_period_filter,
)
from ui.patterns.error_banner import render_error_banner
from ui.patterns.generate_report import (
    render_activity_report_request_card,
    render_recent_reports_section,
)
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink

logger = get_logger("skuel.routes.activity_reports")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_activity_reports_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    orchestrator: Any = None,
) -> list[Any]:
    """Create /activity-reports UI routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: SubmissionsOrchestrator for unified states
    """

    # ========================================================================
    # ACTIVITY REPORTS PAGE
    # ========================================================================

    @rt("/activity-reports")
    def activity_reports_page(request: Request) -> Any:
        """Activity feedback — AI and scheduled activity reports."""
        require_authenticated_user(request)

        content = Div(
            PageHeader(
                "Activity Reports",
                subtitle="AI and scheduled feedback on your activity patterns",
                actions=ButtonLink(
                    "Submit Activity Report",
                    href="/submit-activity-report",
                    cls=ButtonT.secondary,
                    size="sm",
                ),
            ),
            render_time_period_filter(),
            content_loading_placeholder(
                "/reports/activity-list",
                "activity-feedback-list",
                loading_text="Loading activity reports...",
            ),
        )
        return render_gradebook_sidebar_page(
            content=content,
            active="activity-reports",
            request=request,
        )

    # ========================================================================
    # SUBMIT ACTIVITY REPORT — on-demand activity report request
    # ========================================================================

    @rt("/submit-activity-report")
    def submit_activity_report_page(request: Request) -> Any:
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
        return render_gradebook_sidebar_page(
            content=content,
            active="activity-reports",
            request=request,
        )

    # ========================================================================
    # ACTIVITY REPORT DETAIL PAGE
    # ========================================================================

    @rt("/activity-reports/detail")
    def activity_report_detail(request: Request) -> Any:
        """Activity report detail — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        uid = request.query_params.get("uid", "").strip()
        if not uid:
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Report UID is required")),
                active="activity-reports",
                request=request,
            )
        content = Div(
            content_loading_placeholder(
                f"/activity-reports/detail/content?uid={uid}",
                "activity-report-detail-content",
            )
        )
        return render_gradebook_sidebar_page(
            content=content,
            active="activity-reports",
            request=request,
        )

    @rt("/activity-reports/detail/content")
    async def activity_report_detail_content(request: Request) -> Any:
        """HTMX fragment: activity report detail body."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "").strip()
        if not uid:
            return Div(
                render_error_banner("Report UID is required"),
                id="activity-report-detail-content",
            )
        if not orchestrator:
            return Div(
                render_error_banner("Activity report orchestrator unavailable"),
                id="activity-report-detail-content",
            )
        report_result = await orchestrator.get_activity_report(uid, user_uid)
        if report_result.is_error:
            return Div(
                render_error_banner("Report not found", str(report_result.error)),
                id="activity-report-detail-content",
            )
        report = report_result.value
        metadata = getattr(report, "metadata", None) or {}
        snapshot = metadata.get("snapshot") if isinstance(metadata, dict) else None
        intelligence = metadata.get("intelligence") if isinstance(metadata, dict) else None
        comparison = metadata.get("comparison") if isinstance(metadata, dict) else None
        return Div(
            render_activity_report_detail(
                report, snapshot=snapshot, intelligence=intelligence, comparison=comparison
            ),
            id="activity-report-detail-content",
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/reports/activity-list")
    @ui_boundary_handler("Error loading activity feedback", fragment_id="activity-feedback-list")
    async def activity_report_list_fragment(request: Request) -> Any:
        """HTMX fragment: activity reports with optional time_period filter."""
        user_uid = require_authenticated_user(request)
        if not orchestrator:
            return Div(
                render_error_banner(
                    "Activity feedback orchestrator unavailable", severity="warning"
                ),
                id="activity-feedback-list",
            )
        time_period = request.query_params.get("time_period", "")
        result = await orchestrator.get_activity_report_history(user_uid, limit=50)
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

    @rt("/reports/progress-list")
    @ui_boundary_handler("Error loading progress reports", fragment_id="progress-list")
    async def progress_list_fragment(request: Request) -> Any:
        """HTMX fragment: progress reports."""
        user_uid = require_authenticated_user(request)
        if not orchestrator:
            return Div(
                render_error_banner("Submissions orchestrator unavailable"),
                id="progress-list",
            )
        result = await orchestrator.get_activity_report_history(user_uid, limit=10)
        if result.is_error:
            logger.error(f"Error loading progress reports: {result.error}")
            return Div(
                render_error_banner("Failed to load progress reports", str(result.error)),
                id="progress-list",
            )
        return render_progress_report_list(result.value or [])

    # ========================================================================
    # HUB PREVIEW ENDPOINT (HTMX lazy-loaded from /gradebook hub)
    # ========================================================================

    @rt("/api/gradebook/activity-reports/preview")
    async def activity_reports_preview(request: Request) -> Any:
        """HTMX fragment: 3 most recent activity reports for hub preview."""
        user_uid = require_authenticated_user(request)
        if not orchestrator:
            return HubPreviewEmpty("activity reports")
        result = await orchestrator.get_activity_report_history(user_uid, limit=3)
        if result.is_error:
            return HubPreviewEmpty("activity reports")
        reports = result.value or []
        if not reports:
            return HubPreviewEmpty("activity reports")
        cards = []
        for report in reports[:3]:
            title = str(getattr(report, "title", None) or getattr(report, "uid", "Report"))
            period = getattr(report, "time_period", None) or ""
            badge = (
                Span(period, cls="text-[10px] font-medium text-muted-foreground")
                if period
                else None
            )
            content = getattr(report, "processed_content", None) or ""
            cards.append(
                HubPreviewCard(
                    title=title,
                    href="/activity-reports",
                    badge=badge,
                    description=truncate_to_budget(content, 160) if content else None,
                )
            )
        return HubPreviewGrid(cards)

    logger.info(
        "Activity Reports UI routes created "
        "(/activity-reports, /activity-reports/detail, /submit-activity-report)"
    )

    return [
        activity_reports_page,
        submit_activity_report_page,
        activity_report_detail,
        activity_report_detail_content,
        activity_report_list_fragment,
        progress_list_fragment,
    ]
