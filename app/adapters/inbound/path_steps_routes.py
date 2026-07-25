"""
Path Steps Routes - Configuration-Driven Registration
=====================================================

Standalone DomainRouteConfig for Path Steps (PS).
Called from pathways_routes.py since PS lives under the Pathways umbrella.
Registers both API and UI routes.
"""

from adapters.inbound.path_steps_api import create_path_steps_api_routes
from adapters.inbound.path_steps_ui import create_path_steps_ui_routes
from adapters.inbound.route_factories import (
    DomainRouteConfig,
    IntelligenceRouteConfig,
)
from core.models.enums import ContentScope

PS_CONFIG = DomainRouteConfig(
    domain_name="path-steps",
    primary_service_attr="ps",
    api_factory=create_path_steps_api_routes,
    ui_factory=create_path_steps_ui_routes,
    api_related_services={
        "user_service": "user",
        "user_progress_service": "user_progress",
    },
    ui_related_services={
        "ps_engagement_service": "ps_engagement",
        "user_service": "user",
        "tasks_service": "tasks",
    },
    intelligence=IntelligenceRouteConfig(scope=ContentScope.SHARED),
)

__all__ = ["PS_CONFIG"]
