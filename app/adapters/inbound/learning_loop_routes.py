"""Learning Loop Routes — Orchestrator for GradeBook UI Routes
==============================================================

Wires the decomposed submission and report UI routes:
- submissions_ui.py → /submit, /gradebook, /gradebook/{uid}, fragments (GradeBook sidebar)
- exercise_reports_ui.py → /exercise-reports, /reports/list (GradeBook sidebar)
- activity_reports_ui.py → /activity-reports, /submit-activity-report, fragments (GradeBook sidebar)

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.activity_reports_ui import create_activity_reports_ui_routes
from adapters.inbound.exercise_reports_ui import create_exercise_reports_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.submissions_ui import create_submissions_ui_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.learning_loop")


def create_learning_loop_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> RouteList:
    """Wire learning loop routes via decomposed UI files."""

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
        user_service=getattr(services, "user_service", None),
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

    logger.info("Learning loop routes wired (submissions + reports)")
    return []
