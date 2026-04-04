"""Activity Domains hub route — redirects to /profile.

The Activity Domains content is now embedded directly in /profile.
This route exists for backward compatibility (bookmarks, links).
"""

from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse

from adapters.inbound.fasthtml_types import RouteList

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap import Services


def create_activity_hub_routes(
    app: "FastHTMLApp", rt: "RouteDecorator", services: "Services"
) -> RouteList:
    """Register /activities redirect."""

    @rt("/activities")
    async def activities_redirect() -> RedirectResponse:
        """Redirect to /profile where Activity Domains now live."""
        return RedirectResponse("/profile", status_code=301)

    return [activities_redirect]
