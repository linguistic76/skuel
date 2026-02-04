"""Assignments Routes - File Submission and Processing Pipeline
================================================================

Wires Assignments API, UI, and Sharing routes using DomainRouteConfig
(Multi-Factory variant).

Standard factories (via DomainRouteConfig):
- create_assignments_api_routes: Upload, list, process, download, content management
- create_assignments_ui_routes: Dashboard, detail view, HTMX fragments

Extension factory (manual — different primary service):
- create_assignments_sharing_api_routes: Share, unshare, visibility, portfolio

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.assignments_api import create_assignments_api_routes
from adapters.inbound.assignments_sharing_api import create_assignments_sharing_api_routes
from adapters.inbound.assignments_ui import create_assignments_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.assignments")

ASSIGNMENTS_CONFIG = DomainRouteConfig(
    domain_name="assignments",
    primary_service_attr="assignments",
    api_factory=create_assignments_api_routes,
    ui_factory=create_assignments_ui_routes,
    api_related_services={
        "processing_service": "processing_pipeline",
        "assignments_query_service": "assignments_query",
        "assignments_core_service": "assignments_core",
    },
    ui_related_services={
        "_processing_service": "processing_pipeline",
    },
)


def create_assignments_routes(app: Any, rt: Any, services: Any, _sync_service=None) -> list[Any]:
    """
    Wire assignments API, UI, and sharing routes using configuration-driven registration.

    Uses DomainRouteConfig for standard API + UI routes (shared primary service).
    Sharing routes appended manually: their primary service (assignments_sharing)
    differs from the API/UI primary (assignments).

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container
        _sync_service: Unused, signature compatibility

    Returns:
        List of all registered route functions
    """
    routes = register_domain_routes(app, rt, services, ASSIGNMENTS_CONFIG)

    # Extension: sharing routes use a different primary service
    if services and services.assignments_sharing:
        sharing_routes = create_assignments_sharing_api_routes(
            app,
            rt,
            services.assignments_sharing,
            services.assignments_core,
        )
        routes.extend(sharing_routes or [])
        logger.info("✅ Assignment sharing routes registered (Portfolio feature)")

    return routes


__all__ = ["create_assignments_routes"]
