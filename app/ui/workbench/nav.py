"""Submissions sidebar navigation.

Renders a collapsible sidebar for Submissions pages:
Exercise, Journal, Sync, History, Knowledge.
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

SUBMISSIONS_STORAGE_KEY = "submissions-sidebar"

SUBMISSIONS_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Exercise", "/submissions/exercise", "exercise", icon="send"),
    SidebarItem("Journal", "/submissions/journal", "journal", icon="book-open"),
    SidebarItem("Sync", "/submissions/sync", "sync", icon="refresh-cw"),
    SidebarItem("History", "/submissions/history", "history", icon="clock"),
    SidebarItem("Knowledge", "/submissions/knowledge", "knowledge", icon="brain"),
]


async def render_submissions_sidebar_page(
    content: Any,
    active: str,
    request: "Request | None" = None,
) -> "FT":
    """Wrap content in Submissions sidebar page.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "exercise", "journal",
            "sync", "history", "knowledge").
        request: The request object for auth detection.
    """
    return await SidebarPage(
        content=content,
        items=SUBMISSIONS_SIDEBAR_ITEMS,
        active=active,
        title="Submissions",
        storage_key=SUBMISSIONS_STORAGE_KEY,
        request=request,
        active_page="submissions",
        title_href="/submissions",
    )
