"""Reports Routes - File Submission and Processing Pipeline
================================================================

Wires Reports API, UI, and Sharing routes using DomainRouteConfig
(Multi-Factory variant).

Standard factories (via DomainRouteConfig):
- create_reports_api_routes: Upload, list, process, download, content management
- create_reports_ui_routes: Dashboard, detail view, HTMX fragments

Extension factory (manual -- different primary service):
- create_reports_sharing_api_routes: Share, unshare, visibility, portfolio

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.reports_api import create_reports_api_routes
from adapters.inbound.reports_assessment_api import create_reports_assessment_api_routes
from adapters.inbound.reports_progress_api import create_reports_progress_api_routes
from adapters.inbound.reports_sharing_api import create_reports_sharing_api_routes
from adapters.inbound.reports_ui import create_reports_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.reports")

REPORTS_CONFIG = DomainRouteConfig(
    domain_name="reports",
    primary_service_attr="reports",
    api_factory=create_reports_api_routes,
    ui_factory=create_reports_ui_routes,
    api_related_services={
        "processing_service": "report_processor",
        "reports_query_service": "reports_query",
        "reports_core_service": "reports_core",
    },
    ui_related_services={
        "_processing_service": "report_processor",
        "_report_projects_service": "assignments",
    },
)


def create_reports_routes(app: Any, rt: Any, services: Any, _sync_service=None) -> list[Any]:
    """
    Wire reports API, UI, and sharing routes using configuration-driven registration.

    Uses DomainRouteConfig for standard API + UI routes (shared primary service).
    Sharing routes appended manually: their primary service (reports_sharing)
    differs from the API/UI primary (reports).

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container
        _sync_service: Unused, signature compatibility

    Returns:
        List of all registered route functions
    """
    routes = register_domain_routes(app, rt, services, REPORTS_CONFIG)

    # Extension: sharing routes use a different primary service
    if services and services.reports_sharing:
        sharing_routes = create_reports_sharing_api_routes(
            app,
            rt,
            services.reports_sharing,
            services.reports_core,
        )
        routes.extend(sharing_routes or [])
        logger.info("Report sharing routes registered (Portfolio feature)")

    # Extension: progress report generation routes
    progress_generator = getattr(services, "progress_generator", None)
    if progress_generator and services.reports:
        schedule_service = getattr(services, "report_schedule", None)
        progress_routes = create_reports_progress_api_routes(
            app,
            rt,
            progress_generator,
            services.reports,
            schedule_service=schedule_service,
        )
        routes.extend(progress_routes or [])
        logger.info("Report progress routes registered")

    # Extension: assessment routes (require TEACHER role)
    if services and services.reports_core:

        def get_user_service():
            return services.user_service

        assessment_routes = create_reports_assessment_api_routes(
            app,
            rt,
            services.reports_core,
            user_service_getter=get_user_service,
        )
        routes.extend(assessment_routes or [])
        logger.info("Report assessment routes registered")

    return routes


__all__ = ["create_reports_routes"]
