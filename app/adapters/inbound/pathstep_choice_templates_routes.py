"""
PathStep Choice Template Routes — Configuration-Driven Registration
====================================================================

CRUD + PS-attachment endpoints for ChoiceTemplate (Phase 5). See
``pathstep_task_templates_routes.py`` for the shape rationale.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound._pathstep_template_routes_helpers import (
    make_pathstep_template_route_config,
)
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import register_domain_routes
from core.models.templates.choice_template_request import (
    ChoiceTemplateCreateRequest,
    ChoiceTemplateUpdateRequest,
)

if TYPE_CHECKING:
    from services_bootstrap import Services


PATHSTEP_CHOICE_TEMPLATES_CONFIG = make_pathstep_template_route_config(
    domain_name="pathstep-choice-templates",
    primary_service_attr="choice_templates",
    create_schema=ChoiceTemplateCreateRequest,
    update_schema=ChoiceTemplateUpdateRequest,
    uid_prefix="ct",
)


def create_pathstep_choice_templates_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: "Services | None",
    _sync_service: Any = None,
) -> None:
    """Wire ChoiceTemplate CRUD + PS-attachment routes."""
    register_domain_routes(app, rt, services, PATHSTEP_CHOICE_TEMPLATES_CONFIG)


__all__ = ["create_pathstep_choice_templates_routes"]
