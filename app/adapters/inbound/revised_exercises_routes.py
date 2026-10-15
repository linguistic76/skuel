"""
Revised Exercise Routes - Configuration-Driven Registration
=============================================================

Wires the RevisedExercise read routes using DomainRouteConfig. There is no
CRUD block: a revision is sent from the review page
(``POST /api/teaching/review/{uid}/revision``) and is never edited or deleted
afterwards (ADR-091 N2).
Part of the four-phase learning loop: Exercise → UserEntry → EntryReport → RevisedExercise → ...
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.revised_exercises_api import create_revised_exercises_api_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

if TYPE_CHECKING:
    from services_bootstrap import Services

REVISED_EXERCISES_CONFIG = DomainRouteConfig(
    domain_name="revised-exercises",
    primary_service_attr="revised_exercises",
    api_factory=create_revised_exercises_api_routes,
    ui_factory=None,  # UI registered via user_entry_routes.py extension block (revised_exercises_ui.py)
    api_related_services={
        "user_service": "user",
    },
)


def create_revised_exercises_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Services | None, _sync_service: Any = None
) -> None:
    """Wire revised exercise API routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, REVISED_EXERCISES_CONFIG)


__all__ = ["create_revised_exercises_routes"]
