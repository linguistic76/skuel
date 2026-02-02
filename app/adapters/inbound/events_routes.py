"""
Events Routes - API-Only Factory
=================================

Registers only API routes for events domain.
UI route (/events) redirected to unified calendar view (/calendar) per One Path Forward.

See: /adapters/inbound/calendar_routes.py for /events redirect
"""

from adapters.inbound.events_api import create_events_api_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

EVENTS_CONFIG = DomainRouteConfig(
    domain_name="events",
    primary_service_attr="events",
    api_factory=create_events_api_routes,
    ui_factory=None,  # UI disabled - /events redirects to /calendar
    api_related_services={
        # Format: {kwarg_name: container_attr}
        # Each entry is passed to api_factory as: kwarg_name=getattr(services, container_attr)
        "user_service": "user_service",  # user_service=services.user_service
        "goals_service": "goals",  # goals_service=services.goals
        "habits_service": "habits",  # habits_service=services.habits
    },
)


def create_events_routes(app, rt, services, _sync_service=None):
    """Wire events API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, EVENTS_CONFIG)


__all__ = ["create_events_routes"]
