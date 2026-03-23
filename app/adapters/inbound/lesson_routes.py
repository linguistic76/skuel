"""
Lesson Routes - Configuration-Driven Registration
====================================================

Wires Lesson API and UI routes using DomainRouteConfig pattern.

Version: 4.0 (Renamed from Article to Lesson)
"""

from adapters.inbound.lesson_api import create_lesson_api_routes
from adapters.inbound.lesson_ui import create_lesson_ui_routes
from adapters.inbound.route_factories import (
    CRUDRouteConfig,
    DomainRouteConfig,
    IntelligenceRouteConfig,
    register_domain_routes,
)
from core.models.entity_requests import EntityUpdateRequest
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.lesson.lesson_request import LessonCreateRequest

LESSON_CONFIG = DomainRouteConfig(
    domain_name="lesson",
    primary_service_attr="lesson",  # services.lesson
    api_factory=create_lesson_api_routes,
    ui_factory=create_lesson_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
    crud=CRUDRouteConfig(
        create_schema=LessonCreateRequest,
        update_schema=EntityUpdateRequest,
        uid_prefix="l",
        scope=ContentScope.SHARED,
        require_role=UserRole.ADMIN,
        user_service_attr="user_service",
    ),
    intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED),
)


def create_lesson_routes(app, rt, services, _sync_service=None):
    """Wire Lesson API and UI routes."""
    return register_domain_routes(app, rt, services, LESSON_CONFIG)


__all__ = ["create_lesson_routes"]
