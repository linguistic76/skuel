"""Activity Domains hub route — /activities.

Shows all 6 Activity Domains as HTMX-loaded preview blocks
without a sidebar (hub pages have no sidebar).
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import RouteList
from ui.activities.activity_hub import ActivityHubView

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
        from ui.layouts.base_page import BasePage

        content = ActivityHubView()
        return await BasePage(
            content=content,
            title="Activity Domains",
            request=request,
            active_page="activities",
        )

    return [activities_page]
