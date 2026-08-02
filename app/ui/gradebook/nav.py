"""GradeBook sidebar navigation.

Renders a collapsible sidebar for GradeBook surfaces. Since the 3→1
collapse (feedback-loop UX arc 2 C1) the section is one page — the
exchange-lines GradeBook — plus the activity-report request form; report/
revision detail pages render under the same shell with ``active="gradebook"``.

Usage:
    from ui.gradebook.nav import render_gradebook_sidebar_page

    return render_gradebook_sidebar_page(
        content=my_content,
        active="gradebook",
        request=request,
    )
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

GRADEBOOK_STORAGE_KEY = "gradebook-sidebar"

GRADEBOOK_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("GradeBook", "/gradebook", "gradebook", icon="clipboard-check"),
    SidebarItem(
        "Request Activity Report",
        "/submit-activity-report",
        "submit-activity-report",
        icon="bar-chart-2",
    ),
]


def render_gradebook_sidebar_page(
    content: Any,
    active: str,
    request: "Request | None" = None,
) -> "FT":
    """Wrap content in GradeBook sidebar page.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "gradebook").
        request: The request object for auth detection.
    """
    return SidebarPage(
        content=content,
        items=GRADEBOOK_SIDEBAR_ITEMS,
        active=active,
        title="GradeBook",
        storage_key=GRADEBOOK_STORAGE_KEY,
        request=request,
        active_page="gradebook",
        title_href="/gradebook",
    )
