"""
Learning Routes - Configuration-Driven Registration
===================================================

Wires Learning API and UI routes using DomainRouteConfig pattern.

This file handles:
- LP (Learning Path) routes via DomainRouteConfig
- LS (Learning Steps) routes as separate concern (optional)

Benefits:
- Consistent with other domain route files
- Soft-fail service validation (no ValueError)
- Clean separation of concerns
- Minimal boilerplate

Version: 2.0 (Migrated to DomainRouteConfig pattern)
"""

from adapters.inbound.learning_api import create_learning_api_routes
from adapters.inbound.learning_steps_api import create_learning_steps_api_routes
from adapters.inbound.learning_ui import create_learning_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.learning")


# Configuration for main LP routes
LEARNING_CONFIG = DomainRouteConfig(
    domain_name="learning",
    primary_service_attr="learning",  # services.learning
    api_factory=create_learning_api_routes,
    ui_factory=create_learning_ui_routes,
    api_related_services={},
)


def create_learning_routes(app, rt, services, _sync_service=None):
    """
    Wire learning API and UI routes using configuration-driven registration.

    Handles two distinct concerns:
    1. LP (Learning Path) routes - via DomainRouteConfig
    2. LS (Learning Steps) routes - separate optional registration

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with learning service
        _sync_service: Optional sync service (unused, for signature compatibility)

    Returns:
        List of all registered route functions
    """

    # Register main LP routes via DomainRouteConfig (soft-fail if service missing)
    routes = register_domain_routes(app, rt, services, LEARNING_CONFIG)

    # Handle LS routes separately (optional - skipped if learning_steps service missing)
    if services and services.ls:
        ls_routes = create_learning_steps_api_routes(app, rt, services.ls)
        logger.info(f"  ✅ Learning Steps (LS) API routes registered: {len(ls_routes)} endpoints")
        routes.extend(ls_routes)

    return routes


__all__ = ["create_learning_routes"]
