"""Workbench sidebar navigation.

Renders a collapsible sidebar for Workbench pages:
Upload, Submit, Upload History.

Usage:
    from ui.workbench.nav import render_workbench_sidebar_page

    return await render_workbench_sidebar_page(
        content=my_content,
        active="upload",
        request=request,
    )
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

WORKBENCH_STORAGE_KEY = "workbench-sidebar"

WORKBENCH_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Upload", "/upload", "upload", icon="upload-cloud"),
    SidebarItem("Submit", "/submit", "submit", icon="send"),
    SidebarItem("History", "/workbench/history", "history", icon="clock"),
]


async def render_workbench_sidebar_page(
    content: Any,
    active: str,
    request: "Request | None" = None,
) -> "FT":
    """Wrap content in Workbench sidebar page.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "upload", "submit", "history").
        request: The request object for auth detection.
    """
    return await SidebarPage(
        content=content,
        items=WORKBENCH_SIDEBAR_ITEMS,
        active=active,
        title="Workbench",
        storage_key=WORKBENCH_STORAGE_KEY,
        request=request,
        active_page="workbench",
        title_href="/workbench",
    )
