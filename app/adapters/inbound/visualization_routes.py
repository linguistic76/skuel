"""
Visualization Routes - Clean Architecture Factory
=================================================

Minimal factory that wires visualization API routes using DomainRouteConfig.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.visualization_api import create_visualization_api_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


VISUALIZATION_CONFIG = DomainRouteConfig(
    domain_name="visualization",
    primary_service_attr="visualization",
    api_factory=create_visualization_api_routes,
    ui_factory=None,  # No UI routes for visualization
)


def create_visualization_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire visualization API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, VISUALIZATION_CONFIG)


__all__ = ["create_visualization_routes"]
