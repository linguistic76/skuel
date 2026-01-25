"""
System Routes - Clean Architecture Factory
==========================================

Minimal factory that wires System API and UI routes following
the proven clean architecture pattern.

This replaces the monolithic system_routes_impl.py with clean separation:
- system_api.py: Pure JSON API endpoints (health, metrics, diagnostics)
- system_ui.py: Component-based system UI (home page, 404 page)
- This file: Minimal wiring factory
"""

from adapters.inbound.system_api import create_system_api_routes
from adapters.inbound.system_ui import create_system_ui_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.system")


def create_system_routes(app, rt, services, sync_service=None):
    """
    Clean factory that wires system API and UI routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container
        sync_service: Optional sync service
    """

    # Wire API routes (JSON endpoints for health, metrics, diagnostics)
    api_routes = create_system_api_routes(app, rt, services, sync_service)

    # Wire UI routes (home page and 404 page)
    ui_routes = create_system_ui_routes(app, rt, services)

    logger.info("✅ System routes registered (clean architecture)")
    logger.info(f"   - API routes: {len(api_routes)} endpoints")
    logger.info(f"   - UI routes: {len(ui_routes)} endpoints")
    logger.info("   - Pattern: validate → service → respond")
    logger.info("   - Architecture: Clean separation of API and UI")


# Export the route creation function
__all__ = ["create_system_routes"]
