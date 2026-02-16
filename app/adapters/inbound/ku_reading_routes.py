"""
KU Reading Routes - Configuration-Driven Registration
======================================================

Wires KU reading UI and API routes for the Phase A reading interface.

Routes:
- UI: /ku/{uid} - KU detail page with reading interface
- API: /api/ku/{uid}/mark-read, /api/ku/{uid}/bookmark, /api/ku/{uid}/navigation
"""

from adapters.inbound.ku_reading_api import create_ku_reading_api_routes
from adapters.inbound.ku_reading_ui import create_ku_reading_ui_routes


def create_ku_reading_routes(app, rt, services, _sync_service=None):
    """
    Wire KU reading UI and API routes.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        services: Service container with ku

    Returns:
        List of registered route functions
    """
    routes = []

    # API routes
    api_routes = create_ku_reading_api_routes(
        app=app,
        rt=rt,
        ku_interaction_service=services.ku.interaction,
        ku_service=services.ku,
    )
    routes.extend(api_routes)

    # UI routes
    ui_routes = create_ku_reading_ui_routes(
        app=app,
        rt=rt,
        ku_service=services.ku,
        ku_interaction_service=services.ku.interaction,
    )
    routes.extend(ui_routes)

    return routes


__all__ = ["create_ku_reading_routes"]
