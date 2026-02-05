"""
Events Routes - Config-Driven Registration
============================================

Activity Domain: CRUD, Query, and Intelligence factories declared in config.
Status and Analytics factories remain in events_api.py.
UI disabled — /events redirects to /calendar per One Path Forward.

See: /adapters/inbound/calendar_routes.py for /events redirect
"""

from adapters.inbound.events_api import create_events_api_routes
from core.infrastructure.routes import create_activity_domain_route_config, register_domain_routes
from core.models.event.event_request import EventCreateRequest, EventUpdateRequest

EVENTS_CONFIG = create_activity_domain_route_config(
    domain_name="events",
    primary_service_attr="events",
    api_factory=create_events_api_routes,
    create_schema=EventCreateRequest,
    update_schema=EventUpdateRequest,
    uid_prefix="event",
    supports_goal_filter=True,
    supports_habit_filter=True,
    api_related_services={
        "user_service": "user_service",
        "goals_service": "goals",
        "habits_service": "habits",
    },
)


def create_events_routes(app, rt, services, _sync_service=None):
    """Wire events API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, EVENTS_CONFIG)


__all__ = ["create_events_routes"]
