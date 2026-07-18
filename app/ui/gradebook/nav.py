"""GradeBook sidebar navigation.

Renders a collapsible sidebar for GradeBook pages:
Entry Reports, Activity Reports, Revisions.
(My Submissions moved to Submissions sidebar — see ui/workbench/nav.py)

Usage:
    from ui.gradebook.nav import render_gradebook_sidebar_page

    return render_gradebook_sidebar_page(
        content=my_content,
        active="submissions",
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
    SidebarItem("Entry Reports", "/entry-reports", "entry-reports", icon="clipboard-check"),
    SidebarItem("Activity Reports", "/activity-reports", "activity-reports", icon="bar-chart-2"),
    SidebarItem("Revisions", "/revised-exercises", "revised-exercises", icon="refresh-cw"),
]


def render_gradebook_sidebar_page(
    content: Any,
    active: str,
    request: "Request | None" = None,
) -> "FT":
    """Wrap content in GradeBook sidebar page.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "submissions", "submit").
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
