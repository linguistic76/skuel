"""
Form Template Routes - Configuration-Driven Registration
==========================================================

Wires FormTemplate API routes using DomainRouteConfig.
Admin-only CRUD (via CRUDRouteFactory) + lesson linking (manual).
"""

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

FORM_TEMPLATES_CONFIG = DomainRouteConfig(
    domain_name="form-templates",
    primary_service_attr="form_templates",
    api_factory=create_form_templates_api_routes,
    ui_factory=None,  # No dedicated UI routes — forms render inline in lessons
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


def create_form_templates_routes(app, rt, services, _sync_service=None):
    """Wire form template API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, FORM_TEMPLATES_CONFIG)


__all__ = ["create_form_templates_routes"]
