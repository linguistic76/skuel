"""
Notifications Routes - Clean Architecture Factory
====================================================

Wires Notifications UI routes using DomainRouteConfig.
UI-only (no separate API factory needed — HTMX handles mutations).
"""

from adapters.inbound.notifications_ui import create_notifications_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

NOTIFICATIONS_CONFIG = DomainRouteConfig(
    domain_name="notifications",
    primary_service_attr="notification_service",
    ui_factory=create_notifications_ui_routes,
)


def create_notifications_routes(app, rt, services, _sync_service=None):
    """Wire notifications UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, NOTIFICATIONS_CONFIG)


__all__ = ["create_notifications_routes"]
