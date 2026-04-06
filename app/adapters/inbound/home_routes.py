"""Home hub route — post-login landing page.

Routes:
- GET /home — hub page with 6 navigational cards (Profile, Explore, Library, GradeBook, Workbench, Search)
"""

from typing import TYPE_CHECKING, Any

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
    """Register home hub route."""
    user_service = services.user_service

    @rt("/home")
    async def home_hub(request: Request) -> Any:
        """Home hub — post-login landing with Focus+Velocity, Submissions, GradeBook, and cards."""
        user_uid = require_authenticated_user(request)
        from ui.home_hub import HomeHub
        from ui.layouts.base_page import BasePage

        context = None
        if user_service is not None:
            context_result = await user_service.get_rich_unified_context(user_uid)
            if not context_result.is_error:
                context = context_result.value

        return await BasePage(
            content=HomeHub(context),
            title="Home",
            request=request,
            active_page="home",
        )
