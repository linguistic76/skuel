"""
Askesis Routes - Configuration-Driven Registration
=================================================

Wires Askesis API and UI routes using DomainRouteConfig pattern.

Benefits:
- Consistent with other domain route files
- Soft-fail service validation
- Minimal boilerplate
- Clean separation of concerns

Version: 2.0 (Migrated to DomainRouteConfig pattern)
"""

from adapters.inbound.askesis_api import create_askesis_api_routes
from adapters.inbound.askesis_ui import create_askesis_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

# Configuration for Askesis routes
ASKESIS_CONFIG = DomainRouteConfig(
    domain_name="askesis",
    primary_service_attr="askesis",  # services.askesis
    api_factory=create_askesis_api_routes,
    ui_factory=create_askesis_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        # askesis_core_service is optional (Priority 1.1 implementation)
        "askesis_core_service": "askesis_core",  # askesis_core_service=services.askesis_core
        "user_service": "user_service",  # user_service=services.user_service (for UserContext building)
    },
)


def create_askesis_routes(app, rt, services, _sync_service=None):
    """
    Wire askesis API and UI routes using configuration-driven registration.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with askesis service
        _sync_service: Optional sync service (unused, for signature compatibility)

    Returns:
        List of all registered route functions
    """
    return register_domain_routes(app, rt, services, ASKESIS_CONFIG)


__all__ = ["create_askesis_routes"]
