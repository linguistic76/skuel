"""Insights Routes - Event-Driven Insights Dashboard
=====================================================

Wires Insights API and UI routes using DomainRouteConfig.

Phase 1 (January 2026): Insight dashboard with dismiss/action functionality.
Phase 4, Task 17 (January 2026): Action tracking and history page.

Routes:
- GET /insights - Insights dashboard with filtering
- GET /insights/stats - Insight statistics
- GET /insights/history - Action history page (Phase 4, Task 17)
- POST /api/insights/{uid}/dismiss - Dismiss insight (with optional notes)
- POST /api/insights/{uid}/action - Mark insight as actioned (with optional notes)
- GET /api/insights/active - Get active insights (JSON)
- GET /api/insights/stats - Get insight stats (JSON)
"""

from typing import Any

from adapters.inbound.insights_api import create_insights_api_routes
from adapters.inbound.insights_history_ui import create_insights_history_routes
from adapters.inbound.insights_ui import create_insights_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.insights")

INSIGHTS_CONFIG = DomainRouteConfig(
    domain_name="insights",
    primary_service_attr="insight_store",
    api_factory=create_insights_api_routes,
    ui_factory=create_insights_ui_routes,
    api_related_services={},
    ui_related_services={},
)


def create_insights_routes(app: Any, rt: Any, services: Any, _sync_service=None) -> list[Any]:
    """
    Wire insights API and UI routes using configuration-driven registration.

    Uses DomainRouteConfig for standard API + UI routes, then adds history routes separately.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with insight_store
        _sync_service: Optional sync service (unused, for signature compatibility)

    Returns:
        List of all registered route functions
    """
    # Register standard API + UI routes via DomainRouteConfig
    routes = register_domain_routes(app, rt, services, INSIGHTS_CONFIG)

    # Additional history routes (Phase 4, Task 17)
    if services and services.insight_store:
        history_routes = create_insights_history_routes(app, rt, services.insight_store)
        routes.extend(history_routes)
        logger.info(f"✅ Insights history routes registered: {len(history_routes)} endpoints")

    return routes


__all__ = ["create_insights_routes"]
