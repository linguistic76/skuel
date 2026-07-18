"""
Phase 3: EntryReport — Student-Facing Feedback Pages
=========================================================

Student view of exercise feedback. An EntryReport is created when a teacher
or AI evaluates a submission (Phase 2: UserEntry):

    UserEntry → EntryReport  (teacher: ReportSource.HUMAN)
              → EntryReport  (AI: ReportSource.LLM)

assessment_outcome drives what the student sees:
    APPROVED        — work accepted; loop closes for this exercise
    NEEDS_REVISION  — detail page surfaces link to Phase 4 (RevisedExercise)
    AI_EVALUATED    — AI feedback; teacher review may follow

These pages live in the GradeBook sidebar (ui/gradebook/nav.py).

Routes:
- GET /entry-reports              — Exercise reports list page
- GET /entry-reports/detail?uid=  — Report detail with outcome badge + revision link
- GET /reports/list                  — HTMX fragment: teacher assessments received

Renderers: ui/submissions/report.py
Services: EntryReportService (AI), TeacherReviewService (teacher)
See: /docs/architecture/REPORT_ARCHITECTURE.md
See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from fasthtml.common import (
    Div,
    Span,
)

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from core.models.enums.pipeline import ReportSource
from core.utils.logging import get_logger
from core.utils.text_truncation import truncate_to_budget
from ui.components import Card
from ui.gradebook.nav import render_gradebook_sidebar_page
from ui.learning_loop.report import (
    render_entry_report_detail,
    render_received_report_list,
)
from ui.patterns.error_banner import render_error_banner
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.entry_reports")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_entry_reports_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    orchestrator: Any = None,
) -> list[Any]:
    """Create /entry-reports UI routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: SubmissionsOrchestrator for unified state
    """

    # ========================================================================
    # EXERCISE REPORTS PAGE
    # ========================================================================

    @rt("/entry-reports")
    def entry_reports_page(request: Request) -> Any:
        """Teacher and AI exercise reports on submissions."""
        require_authenticated_user(request)

        reports_section = Card(
            content_loading_placeholder(
                "/reports/list",
                "feedback-list",
                loading_text="Loading exercise reports...",
            ),
            cls="bg-background shadow-sm p-4",
        )

        content = Div(
            PageHeader(
                "Entry Reports",
                subtitle="Teacher and AI feedback on your exercise submissions",
            ),
            reports_section,
        )
        return render_gradebook_sidebar_page(
            content=content,
            active="entry-reports",
            request=request,
        )

    # ========================================================================
    # EXERCISE REPORT DETAIL PAGE
    # ========================================================================

    @rt("/entry-reports/detail")
    async def entry_report_detail(request: Request) -> Any:
        """Exercise report detail view — full feedback content and outcome."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "").strip()

        if not uid:
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Report UID is required")),
                active="entry-reports",
                request=request,
            )

        if not orchestrator:
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Report service unavailable")),
                active="entry-reports",
                request=request,
            )

        view_result = await orchestrator.get_entry_report_view(uid, user_uid)
        if view_result.is_error:
            logger.warning(f"Exercise report not found or inaccessible: {uid}")
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Report not found")),
                active="entry-reports",
                request=request,
            )

        view = view_result.value
        content = Div(
            render_entry_report_detail(view["report"], revised_exercise=view["revised_exercise"])
        )
        return render_gradebook_sidebar_page(
            content=content,
            active="entry-reports",
            request=request,
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/reports/list")
    async def entry_reports_list(request: Request) -> Any:
        """HTMX fragment: teacher assessments received."""
        try:
            user_uid = require_authenticated_user(request)
            if not orchestrator:
                return Div(
                    render_error_banner("Feedback service unavailable"),
                    id="feedback-list",
                )
            result = await orchestrator.get_assessments_for_student(user_uid)
            if result.is_error:
                logger.error(f"Error loading feedback list: {result.error}")
                return Div(
                    render_error_banner("Failed to load feedback", str(result.error)),
                    id="feedback-list",
                )
            return render_received_report_list(result.value or [])
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading feedback list: {e}", exc_info=True)
            return Div(
                render_error_banner("Error loading feedback", str(e)),
                id="feedback-list",
            )

    # ========================================================================
    # HUB PREVIEW ENDPOINT (HTMX lazy-loaded from /gradebook hub)
    # ========================================================================

    @rt("/api/gradebook/entry-reports/preview")
    async def entry_reports_preview(request: Request) -> Any:
        """HTMX fragment: 3 most recent exercise reports for hub preview."""
        user_uid = require_authenticated_user(request)
        if not orchestrator:
            return HubPreviewEmpty("exercise reports")
        result = await orchestrator.get_assessments_for_student(user_uid, limit=3)
        if result.is_error:
            return HubPreviewEmpty("exercise reports")
        reports = result.value or []
        if not reports:
            return HubPreviewEmpty("exercise reports")
        cards = []
        for report in reports[:3]:
            uid = getattr(report, "uid", "") or ""
            title = getattr(report, "title", None) or uid or "Report"
            processor_type = getattr(report, "processor_type", None)
            badge = (
                Span(
                    processor_type.get_short_label(),
                    cls="text-[10px] font-medium text-muted-foreground",
                )
                if isinstance(processor_type, ReportSource)
                else None
            )
            content = getattr(report, "processed_content", None) or ""
            href = f"/entry-reports/detail?uid={uid}" if uid else "/entry-reports"
            cards.append(
                HubPreviewCard(
                    title=title,
                    href=href,
                    badge=badge,
                    description=truncate_to_budget(content, 160) if content else None,
                )
            )
        return HubPreviewGrid(cards)

    logger.info(
        "Entry Reports UI routes created (/entry-reports, /entry-reports/detail, /reports/list)"
    )

    return [
        entry_reports_page,
        entry_report_detail,
        entry_reports_list,
    ]
