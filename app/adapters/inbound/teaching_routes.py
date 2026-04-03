"""
Teaching Routes - Clean Architecture Factory
===============================================

Wires Teaching review API + UI routes using DomainRouteConfig.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.teaching_api import create_teaching_api_routes
from adapters.inbound.teaching_ui import create_teaching_ui_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


TEACHING_CONFIG = DomainRouteConfig(
    domain_name="teaching",
    primary_service_attr="teacher_review",
    api_factory=create_teaching_api_routes,
    ui_factory=create_teaching_ui_routes,
    api_related_services={
        "user_service": "user_service",
        "exercises_service": "exercises",
        "submissions_service": "submissions",
    },
    ui_related_services={
        "user_service": "user_service",
        "exercises_service": "exercises",
        "admin_stats": "admin_stats",
    },
)
# NOTE: exercises_service retained in both configs for function signature compatibility.
# The UI and API factories still accept it as a parameter even though exercise
# create/edit routes were removed (2026-04-03 redesign).


def create_teaching_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire teaching API + UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TEACHING_CONFIG)


__all__ = ["create_teaching_routes"]
