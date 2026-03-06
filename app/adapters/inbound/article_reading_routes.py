"""
Article Reading Routes - Configuration-Driven Registration
===========================================================

Wires Article reading UI and API routes for the reading interface.

Routes:
- UI: /article/{uid} - Article detail page with reading interface
- API: /api/article/{uid}/mark-read, /api/article/{uid}/bookmark, /api/article/{uid}/navigation
"""

from adapters.inbound.article_reading_api import create_article_reading_api_routes
from adapters.inbound.article_reading_ui import create_article_reading_ui_routes


def create_article_reading_routes(app, rt, services, _sync_service=None):
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
    api_routes = create_article_reading_api_routes(
        app=app,
        rt=rt,
        ku_interaction_service=services.article.interaction,
        ku_service=services.article,
    )
    routes.extend(api_routes)

    # UI routes
    ui_routes = create_article_reading_ui_routes(
        app=app,
        rt=rt,
        ku_service=services.article,
        ku_interaction_service=services.article.interaction,
        exercises_service=services.exercises,
    )
    routes.extend(ui_routes)

    return routes


__all__ = ["create_article_reading_routes"]
