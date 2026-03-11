"""Activity page layout with sidebar.

Used by individual activity domain pages (/activities/tasks, etc.).
NOT used by the /activities landing page.
"""

from typing import TYPE_CHECKING, Any

from ui.activities.sidebar import ACTIVITY_SIDEBAR_ITEMS
from ui.patterns.sidebar import SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


async def create_activities_page(
    content: Any,
    active_domain: str,
    request: "Request | None" = None,
    title: str = "Activities",
) -> "FT":
    """Wrap content in the Activity sidebar layout.

    Args:
        content: Main content HTML
        active_domain: Currently active domain slug (e.g., "tasks", "goals")
        request: Starlette request for navbar auto-detection
        title: Page title for browser tab
    """
    return await SidebarPage(
        content=content,
        items=ACTIVITY_SIDEBAR_ITEMS,
        active=active_domain,
        title="Activities",
        subtitle="",
        storage_key="activities-sidebar",
        page_title=title,
        request=request,
        active_page="activities",
        title_href="/activities",
    )
