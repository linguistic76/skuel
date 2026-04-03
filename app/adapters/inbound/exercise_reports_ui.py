"""
Exercise Reports UI Routes — ExerciseReport Pages
===================================================

Routes for viewing teacher/AI feedback on exercise submissions.

Routes:
- GET /exercise-reports — Exercise reports list page
- GET /reports/list — HTMX fragment: teacher assessments received

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from fasthtml.common import (
    Div,
    P,
)

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator, RouteList
from core.utils.logging import get_logger
from ui.cards import Card
from ui.gradebook.nav import render_gradebook_sidebar_page
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.submissions.report import (
    render_received_report_list,
)

logger = get_logger("skuel.routes.exercise_reports")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_exercise_reports_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    submissions_core_service: Any = None,
) -> RouteList:
    """Create /exercise-reports UI routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        submissions_core_service: SubmissionsCoreService for received assessments
    """

    # ========================================================================
    # EXERCISE REPORTS PAGE
    # ========================================================================

    @rt("/exercise-reports")
    async def exercise_reports_page(request: Request) -> Any:
        """Teacher and AI exercise reports on submissions."""
        require_authenticated_user(request)

        reports_section = Card(
            Div(
                P("Loading exercise reports...", cls="text-center text-muted-foreground"),
                id="feedback-list",
                cls="mt-2",
                **{
                    "hx-get": "/reports/list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
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
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/reports/list")
    async def exercise_reports_list(request: Request) -> Any:
        """HTMX fragment: teacher assessments received."""
        try:
            user_uid = require_authenticated_user(request)
            if not submissions_core_service:
                return Div(
                    render_error_banner("Feedback service unavailable"),
                    id="feedback-list",
                )
            result = await submissions_core_service.get_assessments_for_student(
                student_uid=user_uid
            )
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

    logger.info("Exercise Reports UI routes created (/exercise-reports, /reports/list)")

    return [
        exercise_reports_page,
        exercise_reports_list,
    ]
