"""
Form Template Routes - Configuration-Driven Registration
==========================================================

Wires FormTemplate API routes using DomainRouteConfig.
Admin-only CRUD (via CRUDRouteFactory) + PathStep linking (manual).
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.form_templates_api import create_form_templates_api_routes
from adapters.inbound.route_factories import (
    CRUDRouteConfig,
    DomainRouteConfig,
    register_domain_routes,
)
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.forms.form_template_request import (
    FormTemplateCreateRequest,
    FormTemplateUpdateRequest,
)

if TYPE_CHECKING:
    from services_bootstrap import Services

FORM_TEMPLATES_CONFIG = DomainRouteConfig(
    domain_name="form-templates",
    primary_service_attr="form_templates",
    api_factory=create_form_templates_api_routes,
    ui_factory=None,  # No dedicated UI routes — forms render inline in path steps
    api_related_services={
        "user_service": "user_service",
    },
    crud=CRUDRouteConfig(
        create_schema=FormTemplateCreateRequest,
        update_schema=FormTemplateUpdateRequest,
        uid_prefix="ft",
        scope=ContentScope.SHARED,
        require_role=UserRole.ADMIN,
        user_service_attr="user_service",
    ),
)


def create_form_templates_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire form template API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, FORM_TEMPLATES_CONFIG)


__all__ = ["create_form_templates_routes"]
