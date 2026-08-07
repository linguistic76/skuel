"""
Choices Routes - Configuration-Driven Registration
====================================================

Factory that wires choices API and UI routes using DomainRouteConfig.

Architecture:
    - Config-driven: CRUD, Query, Intelligence factories via create_activity_domain_route_config()
    - API Routes: choices_api.py (domain-specific: status updates)
    - UI Routes:  choices_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.choices_api import create_choices_api_routes
from adapters.inbound.choices_ui import create_choices_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from core.models.choice.choice_request import ChoiceCreateRequest, ChoiceUpdateRequest

if TYPE_CHECKING:
    from services_bootstrap import Services


CHOICES_CONFIG = create_activity_domain_route_config(
    domain_name="choices",
    primary_service_attr="choices",
    api_factory=create_choices_api_routes,
    ui_factory=create_choices_ui_routes,
    create_schema=ChoiceCreateRequest,
    update_schema=ChoiceUpdateRequest,
    uid_prefix="choice",
    request_create_method="create_choice",
    supports_goal_filter=False,
    supports_habit_filter=False,
    api_related_services={
        "goals_service": "goals",
        "principles_service": "principles",
    },
    ui_related_services={"connection_fetch_backend": "connection_fetch_backend"},
    prometheus_metrics_attr="prometheus_metrics",
)


def create_choices_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire choices API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, CHOICES_CONFIG)


__all__ = ["create_choices_routes"]
