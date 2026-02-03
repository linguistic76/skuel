"""
Transcription Routes - Clean Architecture Factory
=================================================

Minimal factory that wires transcription API routes using DomainRouteConfig.
"""

from adapters.inbound.transcription_api import create_transcription_api_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

TRANSCRIPTION_CONFIG = DomainRouteConfig(
    domain_name="transcription",
    primary_service_attr="transcription",
    api_factory=create_transcription_api_routes,
    ui_factory=None,  # No UI routes for transcription
    api_related_services={},
)


def create_transcription_routes(app, rt, services, _sync_service=None):
    """Wire transcription API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TRANSCRIPTION_CONFIG)


__all__ = ["create_transcription_routes"]
