"""Insights Routes - Event-Driven Insights Dashboard
=====================================================

Wires Insights API and UI routes.

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
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.insights")


def create_insights_routes(app: Any, rt: Any, services: Any, _sync_service=None) -> list[Any]:
    """Wire insights API and UI routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with insight_store
        _sync_service: Optional sync service (unused, for signature compatibility)

    Returns:
        List of all registered route functions
    """
    # Validate that insight_store exists
    if not hasattr(services, "insight_store"):
        logger.error("❌ InsightStore not found in services - insights routes disabled")
        return []

    insight_store = services.insight_store

    # Create API routes
    api_routes = create_insights_api_routes(app, rt, insight_store)
    logger.info(f"✅ Insights API routes created ({len(api_routes)} routes)")

    # Create UI routes
    ui_routes = create_insights_ui_routes(app, rt, insight_store)
    logger.info(f"✅ Insights UI routes created ({len(ui_routes)} routes)")

    # Create history routes (Phase 4, Task 17)
    history_routes = create_insights_history_routes(app, rt, insight_store)
    logger.info(f"✅ Insights history routes created ({len(history_routes)} routes)")

    all_routes = api_routes + ui_routes + history_routes
    logger.info(f"✅ Total insights routes registered: {len(all_routes)}")

    return all_routes


__all__ = ["create_insights_routes"]
