"""Study Routes — Orchestrator for Submission + Report UI Routes
================================================================

Wires the decomposed submission and report UI routes:
- submissions_ui.py → /submit, /submissions, /submissions/{uid}, fragments
- exercise_reports_ui.py → /exercise-reports, /reports/list
- activity_reports_ui.py → /activity-reports, /submit-activity-report, fragments

The /study route itself redirects to /profile (301).

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from starlette.responses import RedirectResponse

from adapters.inbound.activity_reports_ui import create_activity_reports_ui_routes
from adapters.inbound.exercise_reports_ui import create_exercise_reports_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator, RouteList
from adapters.inbound.submissions_ui import create_submissions_ui_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.study")


def create_study_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> RouteList:
    """Wire study routes via decomposed UI files."""

    # /study redirect
    @rt("/study")
    async def study_landing(request: Request) -> Any:
        """Study hub shelved — redirect to Profile (THE main hub)."""
        return RedirectResponse(url="/profile", status_code=301)

    # Submissions UI
    create_submissions_ui_routes(
        app,
        rt,
        submissions_service=services.submissions,
        processing_service=getattr(services, "submissions_processor", None),
        exercises_service=getattr(services, "exercises", None),
        submissions_search_service=getattr(services, "submissions_search", None),
        submissions_core_service=getattr(services, "submissions_core", None),
        teacher_review_service=getattr(services, "teacher_review", None),
    )

    # Exercise Reports UI
    create_exercise_reports_ui_routes(
        app,
        rt,
        submissions_core_service=getattr(services, "submissions_core", None),
    )

    # Activity Reports UI
    create_activity_reports_ui_routes(
        app,
        rt,
        submissions_service=services.submissions,
        activity_report_service=getattr(services, "activity_report", None),
    )

    logger.info("Study routes wired (submissions + exercise reports + activity reports)")
    return []
