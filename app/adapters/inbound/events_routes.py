"""
Events Routes - Configuration-Driven Registration
===================================================

Factory that wires events API and UI routes using DomainRouteConfig.

Architecture:
    - Config-driven: CRUD, Query, Intelligence factories via create_activity_domain_route_config()
    - API Routes: events_api.py (domain-specific: status updates)
    - UI Routes:  events_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.events_api import create_events_api_routes
from adapters.inbound.events_ui import create_events_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from core.models.event.event_request import EventCreateRequest, EventUpdateRequest

if TYPE_CHECKING:
    from services_bootstrap import Services


EVENTS_CONFIG = create_activity_domain_route_config(
    domain_name="events",
    primary_service_attr="events",
    api_factory=create_events_api_routes,
    ui_factory=create_events_ui_routes,
    create_schema=EventCreateRequest,
    update_schema=EventUpdateRequest,
    uid_prefix="event",
    request_create_method="create_event",
    supports_goal_filter=False,
    supports_habit_filter=True,
    api_related_services={
        "habits_service": "habits",
        "goals_service": "goals",
    },
    ui_related_services={
        "connection_fetch_backend": "connection_fetch_backend",
        "user_service": "user",
        "goals_service": "goals",
        "habits_service": "habits",
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_events_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire events API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, EVENTS_CONFIG)


__all__ = ["create_events_routes"]
