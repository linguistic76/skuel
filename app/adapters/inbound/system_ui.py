"""
System UI Routes
================

System UI routes for home page and error pages.

Version: 2.0 - Simplified root page with login form
"""

__version__ = "2.0"


from typing import Any

from starlette.responses import RedirectResponse

from adapters.inbound.auth import get_is_admin, is_authenticated
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.system import render_404_page, render_admin_hub_content, render_login_landing_page

logger = get_logger("skuel.routes.system.ui")


def create_system_ui_routes(
    app: Any,
    rt: Any,
    system_service: Any,
    services: Any = None,
) -> list[Any]:
    """
    Create system UI routes for the application.

    Args:
        app: The FastHTML app instance
        rt: The router instance
        system_service: System service instance (unused but kept for consistency)
        services: Optional services container (unused)

    Returns:
        List of registered routes
    """
    routes: list[Any] = []

    @rt("/")
    async def home(request: Request) -> Any:
        """Home page - admin hub, profile redirect, or login landing."""
        if is_authenticated(request):
            if get_is_admin(request):
                return await BasePage(
                    content=render_admin_hub_content(),
                    title="Admin Hub",
                    request=request,
                )
            return RedirectResponse("/profile", status_code=303)

        logger.info("Unauthenticated user at root, showing login page")
        return render_login_landing_page()

    @rt("/404")
    def not_found() -> Any:
        """404 Not Found page."""
        return render_404_page()

    routes.extend([home, not_found])

    logger.info(f"System UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_system_ui_routes"]
