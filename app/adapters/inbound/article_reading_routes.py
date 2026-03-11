"""
Article Reading Routes - Configuration-Driven Registration
===========================================================

Wires Article reading UI and API routes for the reading interface.

Routes:
- UI: /article/{uid} - Article detail page with reading interface
- API: /api/article/{uid}/mark-read, /api/article/{uid}/bookmark, /api/article/{uid}/navigation
"""

from typing import Any

from adapters.inbound.article_reading_api import create_article_reading_api_routes
from adapters.inbound.article_reading_ui import create_article_reading_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes


def _article_reading_api_factory(
    app: FastHTMLApp, rt: RouteDecorator, article_service: Any, **_kwargs: Any
) -> RouteList:
    """Bridge to article_reading_api with derived services."""
    return create_article_reading_api_routes(
        app=app,
        rt=rt,
        ku_interaction_service=article_service.mastery,
        ku_service=article_service,
    )


def _article_reading_ui_factory(
    app: FastHTMLApp, rt: RouteDecorator, article_service: Any, **kwargs: Any
) -> RouteList:
    """Bridge to article_reading_ui with derived + kwargs services."""
    return create_article_reading_ui_routes(
        app=app,
        rt=rt,
        ku_service=article_service,
        ku_interaction_service=article_service.mastery,
        exercises_service=kwargs.get("exercises_service"),
        form_template_service=kwargs.get("form_template_service"),
    )


ARTICLE_READING_CONFIG = DomainRouteConfig(
    domain_name="article_reading",
    primary_service_attr="article",
    api_factory=_article_reading_api_factory,
    ui_factory=_article_reading_ui_factory,
    ui_related_services={
        "exercises_service": "exercises",
        "form_template_service": "form_templates",
    },
)


def create_article_reading_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> RouteList:
    """Wire Article reading routes via DomainRouteConfig."""
    return register_domain_routes(app, rt, services, ARTICLE_READING_CONFIG)


__all__ = ["create_article_reading_routes"]
