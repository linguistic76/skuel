"""Teaching sidebar navigation.

Renders a collapsible sidebar for Teaching child pages:
Students, Groups, Review Queue, Forms.

Usage:
    from ui.teaching.nav import render_teaching_sidebar_page

    return render_teaching_sidebar_page(
        content=my_content,
        active="students",
        request=request,
    )
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

TEACHING_STORAGE_KEY = "teaching-sidebar"

TEACHING_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Students", "/teaching/students", "students", icon="users"),
    SidebarItem("Groups", "/teaching/groups", "groups", icon="users"),
    SidebarItem("Review Queue", "/teaching/queue", "queue", icon="inbox"),
    SidebarItem("Forms", "/teaching/forms", "forms", icon="file-text"),
]


def render_teaching_sidebar_page(
    content: Any,
    active: str,
    request: "Request | None" = None,
) -> "FT":
    """Wrap content in Teaching sidebar page.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "students", "groups", "queue").
        request: The request object for auth detection.
    """
    return SidebarPage(
        content=content,
        items=TEACHING_SIDEBAR_ITEMS,
        active=active,
        title="Teaching",
        storage_key=TEACHING_STORAGE_KEY,
        request=request,
        active_page="teaching",
        title_href="/teaching/students",
        title_icon="graduation-cap",
    )
