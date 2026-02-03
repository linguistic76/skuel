"""
SEL Routes - Configuration-Driven Registration
===============================================

Factory that wires SEL API and UI routes using DomainRouteConfig.

SEL is the paramount feature of SKUEL, providing personalized learning
experiences across the 5 SEL competencies.

Architecture:
    - API Routes: sel_api.py (JSON + HTMX fragments)
    - UI Routes: sel_ui.py (6 pages with drawer navigation)
    - Components: sel_components.py (SELJourneyOverview, AdaptiveKUCard)
    - Layout: DaisyUI drawer navigation
"""

from adapters.inbound.sel_api import create_sel_api_routes
from adapters.inbound.sel_ui import create_sel_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

SEL_CONFIG = DomainRouteConfig(
    domain_name="sel",
    primary_service_attr="adaptive_sel",
    api_factory=create_sel_api_routes,
    ui_factory=create_sel_ui_routes,
    api_related_services={},  # Self-contained, no additional services
)


def create_sel_routes(app, rt, services, _sync_service=None):
    """Wire SEL API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, SEL_CONFIG)


__all__ = ["create_sel_routes"]
