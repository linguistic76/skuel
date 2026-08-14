"""
PathStep Principle Template Routes — Configuration-Driven Registration
=======================================================================

CRUD + PS-attachment endpoints for PrincipleTemplate (Phase 5). See
``pathstep_task_templates_routes.py`` for the shape rationale.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound._pathstep_template_routes_helpers import (
    make_pathstep_template_route_config,
)
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import register_domain_routes
from core.models.templates.principle_template_request import (
    PrincipleTemplateCreateRequest,
    PrincipleTemplateUpdateRequest,
)

if TYPE_CHECKING:
    from services_bootstrap import Services


PATHSTEP_PRINCIPLE_TEMPLATES_CONFIG = make_pathstep_template_route_config(
    domain_name="pathstep-principle-templates",
    primary_service_attr="principle_templates",
    create_schema=PrincipleTemplateCreateRequest,
    update_schema=PrincipleTemplateUpdateRequest,
    uid_prefix="pt",
)


def create_pathstep_principle_templates_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: "Services | None",
    _sync_service: Any = None,
) -> None:
    """Wire PrincipleTemplate CRUD + PS-attachment routes."""
    register_domain_routes(app, rt, services, PATHSTEP_PRINCIPLE_TEMPLATES_CONFIG)


__all__ = ["create_pathstep_principle_templates_routes"]
