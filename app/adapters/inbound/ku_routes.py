"""
Ku Routes - Configuration-Driven Registration
==============================================

Wires Ku UI routes using DomainRouteConfig pattern.
KuService serves the /ku page — separate from Lesson routes.
"""

from typing import Any

from adapters.inbound.ku_ui import create_ku_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes


def _ku_api_routes(_app: Any, _rt: Any, _service: Any, **_kw: Any) -> list[Any]:
    """Ku API routes placeholder — Ku CRUD uses the existing ku_api.py."""
    return []


KU_CONFIG = DomainRouteConfig(
    domain_name="ku",
    primary_service_attr="ku",  # services.ku -> KuService
    api_factory=_ku_api_routes,
    ui_factory=create_ku_ui_routes,
)


def create_ku_routes(app, rt, services, _sync_service=None):
    """Wire Ku UI routes."""
    return register_domain_routes(app, rt, services, KU_CONFIG)


__all__ = ["create_ku_routes"]
