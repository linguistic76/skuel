"""
Principles Routes - Config-Driven Registration
================================================

Activity Domain: CRUD, Query, and Intelligence factories declared in config.
Analytics factory remains in principles_api.py.
"""

from adapters.inbound.principles_api import create_principles_api_routes
from adapters.inbound.principles_ui import create_principles_ui_routes
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from core.models.ku.ku_request import KuPrincipleCreateRequest, KuUpdateRequest

PRINCIPLES_CONFIG = create_activity_domain_route_config(
    domain_name="principles",
    primary_service_attr="principles",
    api_factory=create_principles_api_routes,
    ui_factory=create_principles_ui_routes,
    create_schema=KuPrincipleCreateRequest,
    update_schema=KuUpdateRequest,
    uid_prefix="principle",
    supports_goal_filter=True,
    supports_habit_filter=True,
    api_related_services={
        "user_service": "user_service",
        "goals_service": "goals",
        "habits_service": "habits",
    },
)


def create_principles_routes(app, rt, services, _sync_service=None):
    """Wire principles API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, PRINCIPLES_CONFIG)


__all__ = ["create_principles_routes"]
