"""
Explore Routes — Configuration-Driven Registration
====================================================

Wires the /explore discovery page using DomainRouteConfig pattern.
Merges Ku + PathStep into a single exploratory surface.

Routes:
- GET  /explore              — Discovery index
- GET  /api/explore/search   — HTMX fragment: filtered card grid
- GET  /explore/ku/{uid}     — Ku detail page
- GET  /explore/ps/{uid}     — PathStep detail page
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.explore_ui import create_explore_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


def _explore_api_routes(_app: Any, _rt: Any, _service: Any, **_kw: Any) -> list[Any]:
    """Explore API routes are registered inline in explore_ui.py via @rt()."""
    return []


EXPLORE_CONFIG = DomainRouteConfig(
    domain_name="explore",
    primary_service_attr="ku",  # services.ku -> KuService (primary)
    api_factory=_explore_api_routes,
    ui_factory=create_explore_ui_routes,
    ui_related_services={
        "ps_service": "ps",
        "user_relationship_service": "user_relationships",
        "exercises_service": "exercises",
        "submissions_search_service": "submissions_search",
    },
)


def create_explore_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire explore UI routes."""
    register_domain_routes(app, rt, services, EXPLORE_CONFIG)


__all__ = ["create_explore_routes"]
