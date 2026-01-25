"""
Finance Routes - Configuration-Driven Registration
=================================================

Wires Finance API and UI routes using DomainRouteConfig pattern.

SECURITY: All Finance routes require ADMIN role.
Finance is its own domain group (not Activity, not Curriculum).

Benefits:
- Consistent with other domain route files
- Soft-fail service validation
- Minimal boilerplate
- Clean separation of concerns

Version: 2.0 (Migrated to DomainRouteConfig pattern)
"""

from adapters.inbound.finance_api import create_finance_api_routes
from adapters.inbound.finance_ui import create_finance_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

# Configuration for Finance routes
FINANCE_CONFIG = DomainRouteConfig(
    domain_name="finance",
    primary_service_attr="finance",  # services.finance
    api_factory=create_finance_api_routes,
    ui_factory=create_finance_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        "user_service": "user_service",  # user_service=services.user_service
    },
    ui_related_services={
        # Format: {kwarg_name: container_attr}
        "user_service": "user_service",  # user_service=services.user_service
    },
)


def create_finance_routes(app, rt, services, _sync_service=None):
    """
    Wire finance API and UI routes using configuration-driven registration.

    SECURITY: All Finance routes require ADMIN role (enforced in route decorators).

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with finance and user services
        _sync_service: Optional sync service (unused, for signature compatibility)

    Returns:
        List of all registered route functions
    """
    return register_domain_routes(app, rt, services, FINANCE_CONFIG)


__all__ = ["create_finance_routes"]
