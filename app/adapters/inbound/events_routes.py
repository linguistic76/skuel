"""
Events Routes - Config-Driven Registration
============================================

Activity Domain: CRUD, Query, and Intelligence factories declared in config.
Status and Analytics factories remain in events_api.py.
UI: Three-view standalone (calendar-first) via events_ui.py.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.events_api import create_events_api_routes
from adapters.inbound.events_ui import create_events_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from core.models.entity_requests import EntityUpdateRequest
from core.models.event.event_request import EventCreateRequest

if TYPE_CHECKING:
    from services_bootstrap import Services


EVENTS_CONFIG = create_activity_domain_route_config(
    domain_name="events",
    primary_service_attr="events",
    api_factory=create_events_api_routes,
    ui_factory=create_events_ui_routes,
    create_schema=EventCreateRequest,
    update_schema=EntityUpdateRequest,
    uid_prefix="event",
    supports_goal_filter=True,
    supports_habit_filter=True,
    api_related_services={
        "user_service": "user_service",
        "goals_service": "goals",
        "habits_service": "habits",
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_events_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire events API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, EVENTS_CONFIG)


__all__ = ["create_events_routes"]
