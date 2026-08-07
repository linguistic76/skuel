"""
Principles Routes - Configuration-Driven Registration
=======================================================

Factory that wires principles API and UI routes using DomainRouteConfig.

Architecture:
    - Config-driven: CRUD, Query, Intelligence factories via create_activity_domain_route_config()
    - API Routes: principles_api.py (domain-specific: status updates)
    - UI Routes:  principles_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.principles_api import create_principles_api_routes
from adapters.inbound.principles_ui import create_principles_ui_routes
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from core.models.principle.principle_request import (
    PrincipleCreateRequest,
    PrincipleUpdateRequest,
)

if TYPE_CHECKING:
    from services_bootstrap import Services


PRINCIPLES_CONFIG = create_activity_domain_route_config(
    domain_name="principles",
    primary_service_attr="principles",
    api_factory=create_principles_api_routes,
    ui_factory=create_principles_ui_routes,
    create_schema=PrincipleCreateRequest,
    update_schema=PrincipleUpdateRequest,
    uid_prefix="principle",
    request_create_method="create_principle",
    supports_goal_filter=True,
    supports_habit_filter=False,
    api_related_services={
        "goals_service": "goals",
        "habits_service": "habits",
    },
    ui_related_services={"connection_fetch_backend": "connection_fetch_backend"},
    prometheus_metrics_attr="prometheus_metrics",
)


def create_principles_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire principles API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, PRINCIPLES_CONFIG)


__all__ = ["create_principles_routes"]
