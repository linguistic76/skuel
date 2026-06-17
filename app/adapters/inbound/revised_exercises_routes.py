"""
Revised Exercise Routes - Configuration-Driven Registration
=============================================================

Wires RevisedExercise API routes using DomainRouteConfig.
CRUD via CRUDRouteFactory (teacher-only), domain-specific routes via API factory.
Part of the four-phase learning loop: Exercise → UserEntry → EntryReport → RevisedExercise → ...
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.revised_exercises_api import create_revised_exercises_api_routes
from adapters.inbound.route_factories import (
    CRUDRouteConfig,
    DomainRouteConfig,
    register_domain_routes,
)
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.exercises.revised_exercise_request import (
    RevisedExerciseCreateRequest,
    RevisedExerciseUpdateRequest,
)

if TYPE_CHECKING:
    from services_bootstrap import Services

REVISED_EXERCISES_CONFIG = DomainRouteConfig(
    domain_name="revised-exercises",
    primary_service_attr="revised_exercises",
    api_factory=create_revised_exercises_api_routes,
    ui_factory=None,  # No UI routes yet — API-only
    api_related_services={
        "user_service": "user",
    },
    crud=CRUDRouteConfig(
        create_schema=RevisedExerciseCreateRequest,
        update_schema=RevisedExerciseUpdateRequest,
        uid_prefix="re",
        scope=ContentScope.USER_OWNED,
        require_role=UserRole.TEACHER,
        user_service_attr="user",
    ),
)


def create_revised_exercises_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire revised exercise API routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, REVISED_EXERCISES_CONFIG)


__all__ = ["create_revised_exercises_routes"]
