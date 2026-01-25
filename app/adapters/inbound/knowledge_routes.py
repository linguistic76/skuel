"""
Knowledge Routes - Configuration-Driven Registration
====================================================

Wires Knowledge API and UI routes using DomainRouteConfig pattern.

Benefits:
- Consistent with other domain route files
- Soft-fail service validation
- Minimal boilerplate
- Clean separation of concerns

Version: 2.0 (Migrated to DomainRouteConfig pattern)
"""

from adapters.inbound.knowledge_api import create_knowledge_api_routes
from adapters.inbound.knowledge_ui import create_knowledge_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

# Configuration for Knowledge (KU) routes
KNOWLEDGE_CONFIG = DomainRouteConfig(
    domain_name="knowledge",
    primary_service_attr="ku",  # services.ku
    api_factory=create_knowledge_api_routes,
    ui_factory=create_knowledge_ui_routes,
    api_related_services={},
)


def create_knowledge_routes(app, rt, services, _sync_service=None):
    """
    Wire knowledge API and UI routes using configuration-driven registration.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with knowledge service
        _sync_service: Optional sync service (unused, for signature compatibility)

    Returns:
        List of all registered route functions
    """
    return register_domain_routes(app, rt, services, KNOWLEDGE_CONFIG)


__all__ = ["create_knowledge_routes"]
