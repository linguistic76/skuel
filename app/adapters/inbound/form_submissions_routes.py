"""
Form Submission Routes - Configuration-Driven Registration
============================================================

Wires FormSubmission API and UI routes using DomainRouteConfig.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.form_submissions_api import create_form_submissions_api_routes
from adapters.inbound.form_submissions_ui import create_form_submissions_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


FORM_SUBMISSIONS_CONFIG = DomainRouteConfig(
    domain_name="form_submissions",
    primary_service_attr="form_submissions",
    api_factory=create_form_submissions_api_routes,
    ui_factory=create_form_submissions_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
    ui_related_services={
        "user_service": "user_service",
    },
)


def create_form_submissions_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire form submission routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, FORM_SUBMISSIONS_CONFIG)


__all__ = ["create_form_submissions_routes"]
