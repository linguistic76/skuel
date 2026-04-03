"""Activity Domains hub route — /activities.

Shows all 6 Activity Domains as HTMX-loaded preview blocks
within the Activity sidebar layout.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import RouteList
from ui.activities.activity_hub import ActivityHubView
from ui.activities.nav import render_activity_sidebar_page

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap import Services


def create_activity_hub_routes(
    app: "FastHTMLApp", rt: "RouteDecorator", services: "Services"
) -> RouteList:
    """Register /activities hub route."""

    @rt("/activities")
    async def activities_page(request: Request) -> Any:
        """Activity Domains hub — all 6 domains at a glance."""
        require_authenticated_user(request)
        content = ActivityHubView()
        return await render_activity_sidebar_page(
            content=content,
            active="activities",
            request=request,
        )

    return [activities_page]
