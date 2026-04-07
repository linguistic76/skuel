"""Askesis sidebar navigation."""

from typing import Any

from adapters.inbound.fasthtml_types import Request
from ui.patterns.sidebar import SidebarItem, SidebarPage

ASKESIS_TITLE = "Askesis"
ASKESIS_STORAGE_KEY = "askesis-sidebar"
ASKESIS_ACTIVE_PAGE = "askesis"

ASKESIS_SIDEBAR_ITEMS = [
    SidebarItem(
        "New Chat", "/askesis/new-chat", "new-chat", description="Start a fresh conversation"
    ),
    SidebarItem(
        "Chat History", "/askesis/history", "history", description="View past conversations"
    ),
    SidebarItem("Dashboard", "/askesis", "dashboard", description="AI assistant overview"),
    SidebarItem(
        "Analytics", "/askesis/analytics", "analytics", description="Intelligence insights"
    ),
    SidebarItem("Settings", "/askesis/settings", "settings", description="Configure assistant"),
]


async def render_askesis_page(
    request: Request, *, content: Any, active: str, page_title: str
) -> Any:
    """Render Askesis sidebar pages with consistent defaults."""
    return await SidebarPage(
        content=content,
        items=ASKESIS_SIDEBAR_ITEMS,
        active=active,
        title=ASKESIS_TITLE,
        storage_key=ASKESIS_STORAGE_KEY,
        page_title=page_title,
        request=request,
        active_page=ASKESIS_ACTIVE_PAGE,
    )
