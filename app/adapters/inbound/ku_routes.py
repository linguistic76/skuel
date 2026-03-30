"""
Ku Routes - Configuration-Driven Registration
==============================================

Wires all Ku routes using DomainRouteConfig pattern.
KuService is the only service dependency — no LessonService.

Routes:
- GET  /ku                           — Knowledge index
- GET  /ku/{uid}                     — Ku detail page
- POST /api/ku/{uid}/mark-studying   — Mark Ku as studying (IN_PROGRESS)
- POST /api/ku/{uid}/mark-understood — Mark Ku as understood (MASTERED)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.ku_ui import create_ku_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


def _ku_api_routes(_app: Any, _rt: Any, _service: Any, **_kw: Any) -> list[Any]:
    """Ku API routes are registered inline in ku_ui.py via @rt()."""
    return []


KU_CONFIG = DomainRouteConfig(
    domain_name="ku",
    primary_service_attr="ku",  # services.ku -> KuService
    api_factory=_ku_api_routes,
    ui_factory=create_ku_ui_routes,
    ui_related_services={
        "user_relationship_service": "user_relationships",
        "exercises_service": "exercises",
        "form_template_service": "form_templates",
    },
)


def create_ku_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire Ku UI routes."""
    return register_domain_routes(app, rt, services, KU_CONFIG)


__all__ = ["create_ku_routes"]
