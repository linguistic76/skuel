"""
Pathways Routes - Configuration-Driven Registration
====================================================

Wires Pathways API and UI routes using DomainRouteConfig pattern.

This file handles:
- LP (Learning Path) routes via DomainRouteConfig
- LS (Learning Steps) routes as separate concern (optional)

Version: 3.0 (Renamed from learning_routes.py)
"""

from adapters.inbound.learning_steps_routes import LS_CONFIG
from adapters.inbound.pathways_api import create_pathways_api_routes
from adapters.inbound.pathways_ui import create_pathways_ui_routes
from adapters.inbound.route_factories import (
    DomainRouteConfig,
    IntelligenceRouteConfig,
    register_domain_routes,
)
from core.models.enums import ContentScope
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.pathways")


# Configuration for main LP routes
PATHWAYS_CONFIG = DomainRouteConfig(
    domain_name="pathways",
    primary_service_attr="lp",  # services.lp
    api_factory=create_pathways_api_routes,
    ui_factory=create_pathways_ui_routes,
    api_related_services={
        "user_service": "user_service",
        "user_progress": "user_progress",
    },
    ui_related_services={
        "user_progress": "user_progress",
        "ls_service": "ls",
    },
    intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED),
)


def create_pathways_routes(app, rt, services, _sync_service=None):
    """
    Wire pathways API and UI routes using configuration-driven registration.

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
    routes = register_domain_routes(app, rt, services, PATHWAYS_CONFIG)

    # Handle LS routes separately (soft-fail if ls service missing)
    routes.extend(register_domain_routes(app, rt, services, LS_CONFIG))

    return routes


__all__ = ["create_pathways_routes"]
