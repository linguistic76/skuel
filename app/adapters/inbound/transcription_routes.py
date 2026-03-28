"""
Transcription Routes - Clean Architecture Factory
=================================================

Minimal factory that wires transcription API routes using DomainRouteConfig.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.transcription_api import create_transcription_api_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


TRANSCRIPTION_CONFIG = DomainRouteConfig(
    domain_name="transcription",
    primary_service_attr="transcription",
    api_factory=create_transcription_api_routes,
    ui_factory=None,  # No UI routes for transcription
    api_related_services={},
)


def create_transcription_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire transcription API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TRANSCRIPTION_CONFIG)


__all__ = ["create_transcription_routes"]
