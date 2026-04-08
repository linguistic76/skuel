"""Home hub route — post-login landing page + shared HTMX fragments.

Routes:
- GET /home — hub page with navigational cards
- GET /api/personal-header — HTMX fragment: Focus + Velocity header
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services


def create_home_routes(
    app: "FastHTMLApp",
    rt: "RouteDecorator",
    services: "Services",
) -> None:
    """Register home hub route and shared HTMX fragments."""

    @rt("/home")
    async def home_hub(request: Request) -> Any:
        """Home hub — post-login landing with Submissions, GradeBook, and cards."""
        require_authenticated_user(request)
        from ui.home_hub import HomeHub
        from ui.layouts.base_page import BasePage

        return await BasePage(
            content=HomeHub(),
            title="Home",
            request=request,
            active_page="home",
        )

    @rt("/api/navbar/notification-badge")
    async def notification_badge_fragment(request: Request) -> Any:
        """HTMX fragment: notification bell with lazy-loaded unread count."""
        from ui.layouts.navbar import _notification_button

        user_uid = require_authenticated_user(request)
        count = 0
        ns = services.notification_service if services else None
        if ns:
            result = await ns.get_unread_count(user_uid)
            if not result.is_error:
                count = result.value
        return Div(
            _notification_button(count),
            id="notification-bell",
            cls="relative",
        )

    @rt("/api/personal-header")
    async def personal_header_fragment(request: Request) -> Any:
        """HTMX fragment: Focus + Velocity header (lazy-loaded to avoid MEGA_QUERY blocking page render)."""
        user_uid = require_authenticated_user(request)
        user_service = services.user_service
        if not user_service:
            return Div()
        context_result = await user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            return Div()
        from ui.patterns.personal_header import personal_header

        return personal_header(context_result.value)
