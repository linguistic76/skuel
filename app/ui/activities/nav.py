"""Activity Domain sidebar navigation.

Renders a collapsible sidebar with all 6 Activity Domains + hub link.
Used on /profile hub and every individual domain page.

Usage:
    from ui.activities.nav import render_activity_sidebar_page

    return await render_activity_sidebar_page(
        content=my_content,
        active="tasks",
        request=request,
    )
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

ACTIVITY_STORAGE_KEY = "activity-sidebar"

ACTIVITY_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Tasks", "/tasks", "tasks", icon="check-square"),
    SidebarItem("Goals", "/goals", "goals", icon="target"),
    SidebarItem("Habits", "/habits", "habits", icon="repeat"),
    SidebarItem("Events", "/events", "events", icon="calendar"),
    SidebarItem("Choices", "/choices", "choices", icon="git-branch"),
    SidebarItem("Principles", "/principles", "principles", icon="compass"),
]


async def render_activity_sidebar_page(
    content: Any,
    active: str,
    request: "Request | None" = None,
) -> "FT":
    """Wrap content in Activity Domain sidebar page.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "tasks", "activities").
        request: The request object for auth detection.
    """
    return await SidebarPage(
        content=content,
        items=ACTIVITY_SIDEBAR_ITEMS,
        active=active,
        title="Tasks+",
        title_icon="check-square",
        storage_key=ACTIVITY_STORAGE_KEY,
        request=request,
        active_page="activity",
        title_href="/tasks",
    )
