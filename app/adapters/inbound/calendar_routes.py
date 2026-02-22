"""
Calendar Routes - Configuration-Driven Registration
=====================================================

Factory that wires calendar API and UI routes using DomainRouteConfig.

Architecture:
    - API Routes: calendar_api.py (quick-create, item details, reschedule)
    - UI Routes:  calendar_ui.py  (month/week/day views, HTMX fragments)
    - Components: calendar_components.py
"""

from adapters.inbound.calendar_api import create_calendar_api_routes
from adapters.inbound.calendar_ui import create_calendar_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

CALENDAR_CONFIG = DomainRouteConfig(
    domain_name="calendar",
    primary_service_attr="calendar",
    api_factory=create_calendar_api_routes,
    ui_factory=create_calendar_ui_routes,
    api_related_services={},
    ui_related_services={
        "habits_service": "habits",
    },
)


def create_calendar_routes(app, rt, services, _sync_service=None):
    """Wire calendar API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, CALENDAR_CONFIG)


__all__ = ["create_calendar_routes"]
