"""Library sidebar navigation.

Renders a collapsible sidebar for Library pages:
Exercises, Resources, Ku, Path Steps.

Usage:
    from ui.library.nav import render_library_sidebar_page

    return render_library_sidebar_page(
        content=my_content,
        active="exercises",
        request=request,
    )
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

LIBRARY_STORAGE_KEY = "library-sidebar"

LIBRARY_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Exercises", "/library/exercises", "exercises", icon="book-open"),
    SidebarItem("Resources", "/library/resources", "resources", icon="bookmark"),
    SidebarItem("Ku", "/library/ku", "ku", icon="brain"),
    SidebarItem("Path Steps", "/library/path-steps", "path-steps", icon="map"),
]


def render_library_sidebar_page(
    content: Any,
    active: str,
    request: "Request | None" = None,
) -> "FT":
    """Wrap content in Library sidebar page.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "exercises", "resources").
        request: The request object for auth detection.
    """
    return SidebarPage(
        content=content,
        items=LIBRARY_SIDEBAR_ITEMS,
        active=active,
        title="Library",
        storage_key=LIBRARY_STORAGE_KEY,
        request=request,
        active_page="library",
        title_href="/library",
    )
