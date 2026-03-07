"""
Revised Exercise Routes - Configuration-Driven Registration
=============================================================

Wires RevisedExercise API routes using DomainRouteConfig.
Part of the five-phase learning loop: Exercise → Submission → Feedback → RevisedExercise → ...
"""

from adapters.inbound.revised_exercises_api import create_revised_exercises_api_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

REVISED_EXERCISES_CONFIG = DomainRouteConfig(
    domain_name="revised_exercises",
    primary_service_attr="revised_exercises",
    api_factory=create_revised_exercises_api_routes,
    ui_factory=None,  # No UI routes yet — API-only
    api_related_services={
        "user_service": "user_service",
    },
)


def create_revised_exercises_routes(app, rt, services, _sync_service=None):
    """Wire revised exercise API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, REVISED_EXERCISES_CONFIG)


__all__ = ["create_revised_exercises_routes"]
