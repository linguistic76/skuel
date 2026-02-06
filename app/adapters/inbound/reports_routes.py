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
from adapters.inbound.reports_sharing_api import create_reports_sharing_api_routes
from adapters.inbound.reports_ui import create_reports_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.reports")

REPORTS_CONFIG = DomainRouteConfig(
    domain_name="reports",
    primary_service_attr="reports",
    api_factory=create_reports_api_routes,
    ui_factory=create_reports_ui_routes,
    api_related_services={
        "processing_service": "processing_pipeline",
        "reports_query_service": "reports_query",
        "reports_core_service": "reports_core",
    },
    ui_related_services={
        "_processing_service": "processing_pipeline",
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

    return routes


__all__ = ["create_reports_routes"]
