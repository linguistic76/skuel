"""
Pathways Routes - Configuration-Driven Registration
====================================================

Wires Pathways API and UI routes using DomainRouteConfig pattern.

This file handles:
- LP (Learning Path) routes via DomainRouteConfig
- PS (Path Steps) routes as separate concern (optional)

Version: 3.0 (Renamed from learning_routes.py)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.path_steps_routes import PS_CONFIG
from adapters.inbound.pathways_api import create_pathways_api_routes
from adapters.inbound.pathways_ui import create_pathways_ui_routes
from adapters.inbound.route_factories import (
    DomainRouteConfig,
    IntelligenceRouteConfig,
    register_domain_routes,
)
from core.models.enums import ContentScope
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from services_bootstrap import Services


logger = get_logger("skuel.routes.pathways")


# Configuration for main LP routes
PATHWAYS_CONFIG = DomainRouteConfig(
    domain_name="pathways",
    primary_service_attr="lp",  # services.lp — API routes use LpService directly
    api_factory=create_pathways_api_routes,
    ui_factory=create_pathways_ui_routes,
    api_related_services={
        "user_service": "user",
        "user_progress": "user_progress",
    },
    ui_related_services={
        "orchestrator": "pathways_orchestrator",
    },
    intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED),
)


def create_pathways_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """
    Wire pathways API and UI routes using configuration-driven registration.

    Handles two distinct concerns:
    1. LP (Learning Path) routes - via DomainRouteConfig
    2. PS (PathStep) routes - separate optional registration

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with learning service
        _sync_service: Optional sync service (unused, for signature compatibility)
    """

    # Register main LP routes via DomainRouteConfig (soft-fail if service missing)
    register_domain_routes(app, rt, services, PATHWAYS_CONFIG)

    # Handle PS routes separately (soft-fail if ps service missing)
    register_domain_routes(app, rt, services, PS_CONFIG)


__all__ = ["create_pathways_routes"]
