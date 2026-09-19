"""
System UI Routes
================

System UI routes for the root landing and error pages.
"""

from typing import Any

from starlette.responses import RedirectResponse

from adapters.inbound.auth import is_authenticated
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.system import render_404_page, render_login_landing_page

logger = get_logger("skuel.routes.system.ui")


def create_system_ui_routes(
    app: Any,
    rt: Any,
    system_service: Any,
    services: Any = None,
) -> None:
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

    @rt("/")
    def home(request: Request) -> Any:
        """Root — the landing is /today for every authenticated role (the
        post-login redirect and the PWA start_url resolve to the same page,
        ADR-058); anonymous visitors get the login landing."""
        if is_authenticated(request):
            return RedirectResponse("/today", status_code=303)

        logger.info("Unauthenticated user at root, showing login page")
        return render_login_landing_page()

    @rt("/404")
    def not_found() -> Any:
        """404 Not Found page."""
        return render_404_page()

    logger.info("System UI routes registered")


__all__ = ["create_system_ui_routes"]
