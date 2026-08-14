"""
Exercise Routes - Configuration-Driven Registration
======================================================

Wires Exercise API and UI routes using DomainRouteConfig.
Exercises provide reusable LLM instruction templates for any submission type.

Formerly assignments_routes.py — renamed per of Ku hierarchy refactoring.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.exercises_api import create_exercises_api_routes
from adapters.inbound.exercises_ui import create_exercises_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import (
    CRUDRouteConfig,
    DomainRouteConfig,
    register_domain_routes,
)
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.exercises.exercise_request import ExerciseCreateRequest, ExerciseUpdateRequest

if TYPE_CHECKING:
    from services_bootstrap import Services


EXERCISES_CONFIG = DomainRouteConfig(
    domain_name="exercises",
    primary_service_attr="exercises",
    api_factory=create_exercises_api_routes,
    ui_factory=create_exercises_ui_routes,
    api_related_services={
        "transcript_service": "content_enrichment",
        "entry_report_service": "entry_report",
        "user_service": "user",
        "intelligence_tier": "intelligence_tier",
    },
    ui_related_services={
        "transcript_service": "content_enrichment",
        "user_service": "user",
    },
    crud=CRUDRouteConfig(
        create_schema=ExerciseCreateRequest,
        update_schema=ExerciseUpdateRequest,
        uid_prefix="ex",
        scope=ContentScope.USER_OWNED,
        require_role=UserRole.TEACHER,
        user_service_attr="user",
    ),
)


def create_exercises_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire exercise API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, EXERCISES_CONFIG)


__all__ = ["create_exercises_routes"]
