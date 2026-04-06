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
