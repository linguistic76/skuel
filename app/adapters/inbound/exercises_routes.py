"""
Exercise Routes - Configuration-Driven Registration
======================================================

Wires Exercise API and UI routes using DomainRouteConfig. An exercise is authored
only in the content vault (ADR-091 S4), so the domain registers no CRUD routes:
the app reads exercises and records what learners do with them.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.exercises_api import create_exercises_api_routes
from adapters.inbound.exercises_ui import create_exercises_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


EXERCISES_CONFIG = DomainRouteConfig(
    domain_name="exercises",
    primary_service_attr="exercises",
    api_factory=create_exercises_api_routes,
    ui_factory=create_exercises_ui_routes,
    api_related_services={
        "entry_report_service": "entry_report",
        "user_service": "user",
        "intelligence_tier": "intelligence_tier",
    },
)


def create_exercises_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Services | None, _sync_service: Any = None
) -> None:
    """Wire exercise API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, EXERCISES_CONFIG)


__all__ = ["create_exercises_routes"]
