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
this file keeps only the detail page.

Routes:
- GET /entry-reports/detail?uid=  — Report detail with outcome badge + revision link

Renderers: ui/learning_loop/report.py
Services: EntryReportService (AI), TeacherReviewService (teacher)
See: /docs/architecture/REPORT_ARCHITECTURE.md
See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from fasthtml.common import (
    Div,
)

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from core.utils.logging import get_logger
from ui.activities.nav import render_activity_sidebar_error, render_activity_sidebar_page
from ui.gradebook.summary import GRADEBOOK_TITLE
from ui.learning_loop.report import render_entry_report_detail

logger = get_logger("skuel.routes.entry_reports")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_entry_reports_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    orchestrator: Any = None,
) -> None:
    """Create the entry-report detail route.

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
            return render_activity_sidebar_error(
                "Report UID is required",
                active="gradebook",
                request=request,
                title=GRADEBOOK_TITLE,
            )

        if not orchestrator:
            return render_activity_sidebar_error(
                "Report service unavailable",
                active="gradebook",
                request=request,
                title=GRADEBOOK_TITLE,
            )

        view_result = await orchestrator.get_entry_report_view(uid, user_uid)
        if view_result.is_error:
            logger.warning(f"Exercise report not found or inaccessible: {uid}")
            return render_activity_sidebar_error(
                "Report not found",
                active="gradebook",
                request=request,
                title=GRADEBOOK_TITLE,
            )

        view = view_result.value
        content = Div(
            render_entry_report_detail(view["report"], revised_exercise=view["revised_exercise"])
        )
        return render_activity_sidebar_page(
            content=content,
            active="gradebook",
            request=request,
            title=GRADEBOOK_TITLE,
        )

    logger.info("Entry Reports UI routes created (/entry-reports/detail)")
