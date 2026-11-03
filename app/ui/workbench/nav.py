"""Submissions sidebar navigation.

Renders a collapsible sidebar for Submissions pages:
Sync, Submit, Journal, History, Knowledge.
"""

from typing import TYPE_CHECKING

from ui.layouts.base_page import HtmlDocument
from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

SUBMISSIONS_STORAGE_KEY = "submissions-sidebar"

SUBMISSIONS_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Sync", "/submissions/sync", "sync", icon="refresh-cw"),
    SidebarItem("Submit", "/submissions/submit", "submit", icon="send"),
    SidebarItem("Journal", "/submissions/journal", "journal", icon="book-open"),
    SidebarItem("History", "/submissions/history", "history", icon="clock"),
    SidebarItem("Knowledge", "/submissions/knowledge", "knowledge", icon="brain"),
]


def render_submissions_sidebar_page(
    content: FT,
    active: str,
    request: Request | None = None,
) -> HtmlDocument:
    """Wrap content in Submissions sidebar page.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "submit", "journal",
            "sync", "history", "knowledge").
        request: The request object for auth detection.
    """
    return SidebarPage(
        content=content,
        items=SUBMISSIONS_SIDEBAR_ITEMS,
        active=active,
        title="Submissions",
        storage_key=SUBMISSIONS_STORAGE_KEY,
        request=request,
        active_page="submissions",
        title_href="/submissions",
    )
