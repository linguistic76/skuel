"""
Groups Routes - Clean Architecture Factory
============================================

Wires Group API and UI routes using DomainRouteConfig.
CRUD via CRUDRouteFactory (TEACHER for mutations, any-auth for reads).
Membership operations stay manual in groups_api.py.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.groups_api import create_groups_api_routes
from adapters.inbound.groups_ui import create_groups_ui_routes
from adapters.inbound.route_factories import (
    CRUDRouteConfig,
    DomainRouteConfig,
    register_domain_routes,
)
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.group.group_request import GroupCreateRequest, GroupUpdateRequest

if TYPE_CHECKING:
    from services_bootstrap import Services


GROUPS_CONFIG = DomainRouteConfig(
    domain_name="groups",
    primary_service_attr="group_service",
    api_factory=create_groups_api_routes,
    ui_factory=create_groups_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
    crud=CRUDRouteConfig(
        create_schema=GroupCreateRequest,
        update_schema=GroupUpdateRequest,
        uid_prefix="group",
        scope=ContentScope.USER_OWNED,
        require_role=UserRole.TEACHER,
        role_gates_reads=False,
        user_service_attr="user_service",
    ),
)


def create_groups_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire group API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, GROUPS_CONFIG)


__all__ = ["create_groups_routes"]
