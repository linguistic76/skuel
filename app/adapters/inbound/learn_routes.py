"""Learn Routes — Student Workspace Hub Orchestrator
=====================================================

Wires the /learn workspace routes with all needed submission services.

Routes:
- GET /learn — Dashboard landing (no sidebar)
- GET /learn/submit — File upload form
- GET /learn/submissions — My submitted work
- GET /learn/reports — Teacher assessments + progress reports
- GET /learn/submissions/{uid} — Submission detail
- HTMX fragments for all above

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.learn_ui import create_learn_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.learn")


LEARN_CONFIG = DomainRouteConfig(
    domain_name="learn",
    primary_service_attr="submissions",
    api_factory=create_learn_ui_routes,
    api_related_services={
        "processing_service": "submissions_processor",
        "user_service": "user_service",
        "exercises_service": "assignments",
        "submissions_search_service": "submissions_search",
        "submissions_core_service": "submissions_core",
        "activity_report_service": "activity_report",
        "teacher_review_service": "teacher_review",
    },
)


def create_learn_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> RouteList:
    """Wire learn routes via DomainRouteConfig."""
    return register_domain_routes(app, rt, services, LEARN_CONFIG)
