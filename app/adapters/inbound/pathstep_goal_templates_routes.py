"""
PathStep Goal Template Routes — Configuration-Driven Registration
==================================================================

CRUD + PS-attachment endpoints for GoalTemplate (Phase 5). See
``pathstep_task_templates_routes.py`` for the shape rationale.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound._pathstep_template_routes_helpers import (
    make_pathstep_template_route_config,
)
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import register_domain_routes
from core.models.templates.goal_template_request import (
    GoalTemplateCreateRequest,
    GoalTemplateUpdateRequest,
)

if TYPE_CHECKING:
    from services_bootstrap import Services


PATHSTEP_GOAL_TEMPLATES_CONFIG = make_pathstep_template_route_config(
    domain_name="pathstep-goal-templates",
    primary_service_attr="goal_templates",
    create_schema=GoalTemplateCreateRequest,
    update_schema=GoalTemplateUpdateRequest,
    uid_prefix="gt",
)


def create_pathstep_goal_templates_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: "Services | None",
    _sync_service: Any = None,
) -> None:
    """Wire GoalTemplate CRUD + PS-attachment routes."""
    register_domain_routes(app, rt, services, PATHSTEP_GOAL_TEMPLATES_CONFIG)


__all__ = ["create_pathstep_goal_templates_routes"]
