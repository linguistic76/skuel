"""
Revised Exercise Routes - Configuration-Driven Registration
=============================================================

Wires RevisedExercise API routes using DomainRouteConfig.
CRUD via CRUDRouteFactory (teacher-only), domain-specific routes via API factory.
Part of the five-phase learning loop: Exercise → Submission → Report → RevisedExercise → ...
"""

from adapters.inbound.revised_exercises_api import create_revised_exercises_api_routes
from adapters.inbound.route_factories import (
    CRUDRouteConfig,
    DomainRouteConfig,
    register_domain_routes,
)
from core.models.exercises.revised_exercise_request import (
    RevisedExerciseCreateRequest,
    RevisedExerciseUpdateRequest,
)

REVISED_EXERCISES_CONFIG = DomainRouteConfig(
    domain_name="revised-exercises",
    primary_service_attr="revised_exercises",
    api_factory=create_revised_exercises_api_routes,
    ui_factory=None,  # No UI routes yet — API-only
    api_related_services={
        "user_service": "user_service",
    },
    crud=CRUDRouteConfig(
        create_schema=RevisedExerciseCreateRequest,
        update_schema=RevisedExerciseUpdateRequest,
        uid_prefix="re",
        scope="user_owned",
        require_role="teacher",
        user_service_attr="user_service",
    ),
)


def create_revised_exercises_routes(app, rt, services, _sync_service=None):
    """Wire revised exercise API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, REVISED_EXERCISES_CONFIG)


__all__ = ["create_revised_exercises_routes"]
