"""
Reports Routes - Configuration-Driven Registration
=================================================

Wires Reports API and UI routes using DomainRouteConfig pattern.

Benefits:
- Consistent with other domain route files
- Soft-fail service validation
- Minimal boilerplate
- Clean separation of concerns

Version: 2.0 (Migrated to DomainRouteConfig pattern)

Routes provided:
API:
- GET /api/reports/life-path-alignment
- GET /api/reports/weekly-life-summary
- GET /api/reports/monthly-life-review
- GET /api/reports/quarterly-progress
- GET /api/reports/yearly-review
- GET /api/reports/cross-domain-patterns

UI:
- GET /ui/reports (existing dashboard)
- GET /ui/reports/life-path-alignment (Phase 1)
- GET /ui/reports/weekly-life-summary (Phase 3)
"""

from adapters.inbound.reports_api import create_reports_api_routes
from adapters.inbound.reports_ui import create_reports_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

# Configuration for Reports routes
REPORTS_CONFIG = DomainRouteConfig(
    domain_name="reports",
    primary_service_attr="reports",  # services.reports
    api_factory=create_reports_api_routes,
    ui_factory=create_reports_ui_routes,
    api_related_services={},
)


def create_reports_routes(app, rt, services, _sync_service=None):
    """
    Wire reports API and UI routes using configuration-driven registration.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with reports service
        _sync_service: Optional sync service (unused, for signature compatibility)

    Returns:
        List of all registered route functions
    """
    return register_domain_routes(app, rt, services, REPORTS_CONFIG)


__all__ = ["create_reports_routes"]
