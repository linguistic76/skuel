"""
Learning Steps Routes - Configuration-Driven Registration
=========================================================

Standalone DomainRouteConfig for Learning Steps (LS).
Called from pathways_routes.py since LS lives under the Pathways umbrella.

Version: 3.0 (Migrated to DomainRouteConfig pattern)
"""

from adapters.inbound.learning_steps_api import create_learning_steps_api_routes
from adapters.inbound.route_factories import (
    DomainRouteConfig,
    IntelligenceRouteConfig,
)
from core.models.enums import ContentScope

LS_CONFIG = DomainRouteConfig(
    domain_name="learning-steps",
    primary_service_attr="ls",  # services.ls
    api_factory=create_learning_steps_api_routes,
    api_related_services={
        "user_service": "user_service",
    },
    intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED),
)

__all__ = ["LS_CONFIG"]
