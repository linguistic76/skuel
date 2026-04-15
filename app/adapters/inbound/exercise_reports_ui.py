"""
Phase 3: ExerciseReport — Student-Facing Feedback Pages
=========================================================

Student view of exercise feedback. An ExerciseReport is created when a teacher
or AI evaluates a submission (Phase 2: ExerciseSubmission):

    ExerciseSubmission → ExerciseReport  (teacher: ProcessorType.HUMAN)
                      → ExerciseReport  (AI: ProcessorType.LLM)

assessment_outcome drives what the student sees:
    APPROVED        — work accepted; loop closes for this exercise
    NEEDS_REVISION  — detail page surfaces link to Phase 4 (RevisedExercise)
    AI_EVALUATED    — AI feedback; teacher review may follow

These pages live in the GradeBook sidebar (ui/gradebook/nav.py).

Routes:
- GET /exercise-reports              — Exercise reports list page
- GET /exercise-reports/detail?uid=  — Report detail with outcome badge + revision link
- GET /reports/list                  — HTMX fragment: teacher assessments received

Renderers: ui/submissions/report.py
Services: ExerciseReportService (AI), TeacherReviewService (teacher)
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
from core.utils.logging import get_logger
from ui.cards import Card
from ui.gradebook.nav import render_gradebook_sidebar_page
from ui.learning_loop.report import (
    render_exercise_report_detail,
    render_received_report_list,
)
from ui.patterns.error_banner import render_error_banner
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.exercise_reports")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_exercise_reports_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    orchestrator: Any = None,
) -> list[Any]:
    """Create /exercise-reports UI routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: SubmissionsOrchestrator for unified state
    """

    # ========================================================================
    # EXERCISE REPORTS PAGE
    # ========================================================================

    @rt("/exercise-reports")
    async def exercise_reports_page(request: Request) -> Any:
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
                "Exercise Reports",
                subtitle="Teacher and AI feedback on your exercise submissions",
            ),
            reports_section,
        )
        return await render_gradebook_sidebar_page(
            content=content,
            active="exercise-reports",
            request=request,
        )

    # ========================================================================
    # EXERCISE REPORT DETAIL PAGE
    # ========================================================================

    @rt("/exercise-reports/detail")
    async def exercise_report_detail(request: Request) -> Any:
        """Exercise report detail view — full feedback content and outcome."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "").strip()

        if not uid:
            return await render_gradebook_sidebar_page(
                content=Div(render_error_banner("Report UID is required")),
                active="exercise-reports",
                request=request,
            )

        if not orchestrator:
            return await render_gradebook_sidebar_page(
                content=Div(render_error_banner("Report service unavailable")),
                active="exercise-reports",
                request=request,
            )

        view_result = await orchestrator.get_exercise_report_view(uid, user_uid)
        if view_result.is_error:
            logger.warning(f"Exercise report not found or inaccessible: {uid}")
            return await render_gradebook_sidebar_page(
                content=Div(render_error_banner("Report not found")),
                active="exercise-reports",
                request=request,
            )

        view = view_result.value
        content = Div(
            render_exercise_report_detail(view["report"], revised_exercise=view["revised_exercise"])
        )
        return await render_gradebook_sidebar_page(
            content=content,
            active="exercise-reports",
            request=request,
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/reports/list")
    async def exercise_reports_list(request: Request) -> Any:
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

    @rt("/api/gradebook/exercise-reports/preview")
    async def exercise_reports_preview(request: Request) -> Any:
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
            source = getattr(report, "source", None) or ""
            badge = (
                Span(source.title(), cls="text-[10px] font-medium text-muted-foreground")
                if source
                else None
            )
            href = f"/exercise-reports/detail?uid={uid}" if uid else "/exercise-reports"
            cards.append(HubPreviewCard(title=title, href=href, badge=badge))
        return HubPreviewGrid(cards)

    logger.info(
        "Exercise Reports UI routes created "
        "(/exercise-reports, /exercise-reports/detail, /reports/list)"
    )

    return [
        exercise_reports_page,
        exercise_report_detail,
        exercise_reports_list,
    ]
