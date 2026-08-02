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

The list surface is the GradeBook exchange lines (/gradebook, arc 2 C1) —
this file keeps only the detail page and the profile hub preview.

Routes:
- GET /entry-reports/detail?uid=  — Report detail with outcome badge + revision link
- GET /api/gradebook/entry-reports/preview — HTMX hub preview block

Renderers: ui/learning_loop/report.py
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
from ui.gradebook.nav import render_gradebook_sidebar_page
from ui.learning_loop.report import render_entry_report_detail
from ui.patterns.error_banner import render_error_banner
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid

logger = get_logger("skuel.routes.entry_reports")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_entry_reports_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    orchestrator: Any = None,
) -> list[Any]:
    """Create entry-report detail + preview routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: SubmissionsOrchestrator for unified state
    """

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
                active="gradebook",
                request=request,
            )

        if not orchestrator:
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Report service unavailable")),
                active="gradebook",
                request=request,
            )

        view_result = await orchestrator.get_entry_report_view(uid, user_uid)
        if view_result.is_error:
            logger.warning(f"Exercise report not found or inaccessible: {uid}")
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Report not found")),
                active="gradebook",
                request=request,
            )

        view = view_result.value
        content = Div(
            render_entry_report_detail(view["report"], revised_exercise=view["revised_exercise"])
        )
        return render_gradebook_sidebar_page(
            content=content,
            active="gradebook",
            request=request,
        )

    # ========================================================================
    # HUB PREVIEW ENDPOINT (HTMX lazy-loaded from /profile Reports tab)
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
            # Body field varies by writer: review/AI reports store
            # processed_content, assessments store content.
            content = (
                getattr(report, "processed_content", None) or getattr(report, "content", None) or ""
            )
            href = f"/entry-reports/detail?uid={uid}" if uid else "/gradebook"
            cards.append(
                HubPreviewCard(
                    title=title,
                    href=href,
                    badge=badge,
                    description=truncate_to_budget(content, 160) if content else None,
                )
            )
        return HubPreviewGrid(cards)

    logger.info("Entry Reports UI routes created (/entry-reports/detail + hub preview)")

    return [
        entry_report_detail,
    ]
