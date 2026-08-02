"""
Calendar Routes - Configuration-Driven Registration
=====================================================

Factory that wires calendar API and UI routes using DomainRouteConfig.

Architecture:
    - API Routes: calendar_api.py (item-details JSON)
    - UI Routes:  calendar_ui.py  (month/week views, HTMX fragments,
      item-details modal, per-day habit completion, task/event reschedule)
    - Components: ui/calendar/components.py
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.calendar_api import create_calendar_api_routes
from adapters.inbound.calendar_ui import create_calendar_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


CALENDAR_CONFIG = DomainRouteConfig(
    domain_name="calendar",
    primary_service_attr="calendar",
    api_factory=create_calendar_api_routes,
    ui_factory=create_calendar_ui_routes,
)


def create_calendar_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire calendar API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, CALENDAR_CONFIG)


__all__ = ["create_calendar_routes"]
