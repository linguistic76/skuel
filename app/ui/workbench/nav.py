"""Submissions sidebar navigation.

Renders a collapsible sidebar for Submissions pages:
Submit, Journals, Submission History, Obsidian Sync.
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

SUBMISSIONS_STORAGE_KEY = "submissions-sidebar"

SUBMISSIONS_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Submit", "/submit", "submit", icon="send"),
    SidebarItem("Journals", "/submit/journals", "journals", icon="book-open"),
    SidebarItem("History", "/submissions/history", "history", icon="clock"),
    SidebarItem("Obsidian Sync", "/settings/vault", "vault-sync", icon="refresh-cw"),
]


async def render_submissions_sidebar_page(
    content: Any,
    active: str,
    request: "Request | None" = None,
) -> "FT":
    """Wrap content in Submissions sidebar page.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "upload", "submit", "history").
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
        title_href="/profile?tab=submissions",
    )
