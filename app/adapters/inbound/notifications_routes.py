"""
Notifications Routes - Clean Architecture Factory
====================================================

Wires Notifications UI routes using DomainRouteConfig.
UI-only (no separate API factory needed — HTMX handles mutations).
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.notifications_ui import create_notifications_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


NOTIFICATIONS_CONFIG = DomainRouteConfig(
    domain_name="notifications",
    primary_service_attr="notifications",
    ui_factory=create_notifications_ui_routes,
)


def create_notifications_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Services | None, _sync_service: Any = None
) -> None:
    """Wire notifications UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, NOTIFICATIONS_CONFIG)


__all__ = ["create_notifications_routes"]
