"""Activity Review sidebar navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import Request

ACTIVITY_REVIEW_SIDEBAR_ITEMS = [
    SidebarItem("Queue", "/activity-review/queue", "queue", icon="\U0001f4cb"),
    SidebarItem("New Review", "/activity-review/new", "new", icon="\u270d\ufe0f"),
]


def activity_review_sidebar_page(
    active: str, content: Any, request: Request, *, page_title: str
) -> Any:
    """Create sidebar page for Activity Review routes."""
    return SidebarPage(
        content=content,
        items=ACTIVITY_REVIEW_SIDEBAR_ITEMS,
        active=active,
        title="Activity Review",
        subtitle="Admin feedback on Activity Domains",
        storage_key="activity-review-sidebar",
        page_title=page_title,
        request=request,
        active_page="activity-review",
        title_href="/activity-review",
    )
