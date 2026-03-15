"""
Lesson Reading Routes - Configuration-Driven Registration
===========================================================

Wires Lesson reading UI and API routes for the reading interface.

Routes:
- UI: /lesson/{uid} - Lesson detail page with reading interface
- API: /api/lesson/{uid}/mark-read, /api/lesson/{uid}/bookmark, /api/lesson/{uid}/navigation
"""

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.lesson_reading_api import create_lesson_reading_api_routes
from adapters.inbound.lesson_reading_ui import create_lesson_reading_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes


def _lesson_reading_api_factory(
    app: FastHTMLApp, rt: RouteDecorator, lesson_service: Any, **_kwargs: Any
) -> RouteList:
    """Bridge to lesson_reading_api with derived services."""
    return create_lesson_reading_api_routes(
        app=app,
        rt=rt,
        ku_interaction_service=lesson_service.mastery,
        ku_service=lesson_service,
    )


def _lesson_reading_ui_factory(
    app: FastHTMLApp, rt: RouteDecorator, lesson_service: Any, **kwargs: Any
) -> RouteList:
    """Bridge to lesson_reading_ui with derived + kwargs services."""
    return create_lesson_reading_ui_routes(
        app=app,
        rt=rt,
        ku_service=lesson_service,
        ku_interaction_service=lesson_service.mastery,
        exercises_service=kwargs.get("exercises_service"),
        form_template_service=kwargs.get("form_template_service"),
    )


LESSON_READING_CONFIG = DomainRouteConfig(
    domain_name="lesson_reading",
    primary_service_attr="lesson",
    api_factory=_lesson_reading_api_factory,
    ui_factory=_lesson_reading_ui_factory,
    ui_related_services={
        "exercises_service": "exercises",
        "form_template_service": "form_templates",
    },
)


def create_lesson_reading_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> RouteList:
    """Wire Lesson reading routes via DomainRouteConfig."""
    return register_domain_routes(app, rt, services, LESSON_READING_CONFIG)


__all__ = ["create_lesson_reading_routes"]
