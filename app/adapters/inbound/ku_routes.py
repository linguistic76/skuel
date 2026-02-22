"""
KU Routes - Configuration-Driven Registration
==============================================

Wires KU API and UI routes using DomainRouteConfig pattern.

Benefits:
- Consistent with other domain route files
- Soft-fail service validation
- Minimal boilerplate
- Clean separation of concerns

Version: 2.0 (Migrated to DomainRouteConfig pattern)
"""

from adapters.inbound.ku_api import create_ku_api_routes
from adapters.inbound.ku_ui import create_ku_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

# Configuration for KU routes
KU_CONFIG = DomainRouteConfig(
    domain_name="ku",
    primary_service_attr="ku",  # services.ku
    api_factory=create_ku_api_routes,
    ui_factory=create_ku_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
)


def create_ku_routes(app, rt, services, _sync_service=None):
    """
    Wire KU API and UI routes using configuration-driven registration.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with KU service
        _sync_service: Optional sync service (unused, for signature compatibility)

    Returns:
        List of all registered route functions
    """
    return register_domain_routes(app, rt, services, KU_CONFIG)


__all__ = ["create_ku_routes"]
