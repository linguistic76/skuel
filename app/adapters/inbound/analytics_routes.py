"""
Analytics Routes - Configuration-Driven Registration
=================================================

Wires Analytics API and UI routes using DomainRouteConfig pattern.

Benefits:
- Consistent with other domain route files
- Soft-fail service validation
- Minimal boilerplate
- Clean separation of concerns

Version: 2.0 (Migrated to DomainRouteConfig pattern)

Routes provided:
API:
- GET /api/analytics/life-path-alignment
- GET /api/analytics/weekly-life-summary
- GET /api/analytics/monthly-life-review
- GET /api/analytics/quarterly-progress
- GET /api/analytics/yearly-review
- GET /api/analytics/cross-domain-patterns

UI:
- GET /ui/analytics (existing dashboard)
- GET /ui/analytics/life-path-alignment
- GET /ui/analytics/weekly-life-summary
"""

from adapters.inbound.analytics_summary_api import create_analytics_summary_api_routes
from adapters.inbound.analytics_ui import create_analytics_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

# Configuration for Analytics routes
ANALYTICS_CONFIG = DomainRouteConfig(
    domain_name="analytics",
    primary_service_attr="analytics",  # services.analytics
    api_factory=create_analytics_summary_api_routes,
    ui_factory=create_analytics_ui_routes,
    api_related_services={},
)


def create_analytics_routes(app, rt, services, _sync_service=None):
    """
    Wire analytics API and UI routes using configuration-driven registration.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with analytics service
        _sync_service: Optional sync service (unused, for signature compatibility)

    Returns:
        List of all registered route functions
    """
    return register_domain_routes(app, rt, services, ANALYTICS_CONFIG)


__all__ = ["create_analytics_routes"]
