"""
Lesson Routes - Configuration-Driven Registration
====================================================

Wires Lesson API and UI routes using DomainRouteConfig pattern.

Version: 4.0 (Renamed from Article to Lesson)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.lesson_api import create_lesson_api_routes
from adapters.inbound.lesson_ui import create_lesson_ui_routes
from adapters.inbound.route_factories import (
    DomainRouteConfig,
    IntelligenceRouteConfig,
    register_domain_routes,
)
from core.models.enums import ContentScope

if TYPE_CHECKING:
    from services_bootstrap import Services


LESSON_CONFIG = DomainRouteConfig(
    domain_name="lesson",
    primary_service_attr="lesson",  # services.lesson
    api_factory=create_lesson_api_routes,
    ui_factory=create_lesson_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
    intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED),
)


def create_lesson_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire Lesson API and UI routes."""
    return register_domain_routes(app, rt, services, LESSON_CONFIG)


__all__ = ["create_lesson_routes"]
