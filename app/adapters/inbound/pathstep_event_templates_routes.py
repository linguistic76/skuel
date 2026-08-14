"""
PathStep Event Template Routes — Configuration-Driven Registration
===================================================================

CRUD + PS-attachment endpoints for EventTemplate (Phase 5). See
``pathstep_task_templates_routes.py`` for the shape rationale.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound._pathstep_template_routes_helpers import (
    make_pathstep_template_route_config,
)
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import register_domain_routes
from core.models.templates.event_template_request import (
    EventTemplateCreateRequest,
    EventTemplateUpdateRequest,
)

if TYPE_CHECKING:
    from services_bootstrap import Services


PATHSTEP_EVENT_TEMPLATES_CONFIG = make_pathstep_template_route_config(
    domain_name="pathstep-event-templates",
    primary_service_attr="event_templates",
    create_schema=EventTemplateCreateRequest,
    update_schema=EventTemplateUpdateRequest,
    uid_prefix="et",
)


def create_pathstep_event_templates_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: "Services | None",
    _sync_service: Any = None,
) -> None:
    """Wire EventTemplate CRUD + PS-attachment routes."""
    register_domain_routes(app, rt, services, PATHSTEP_EVENT_TEMPLATES_CONFIG)


__all__ = ["create_pathstep_event_templates_routes"]
