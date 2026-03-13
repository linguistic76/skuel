"""
Activity Domain Standalone Layout
=================================

Shared standalone page layout for all Activity Domains (Tasks, Goals, Habits,
Events, Choices, Principles). Each domain uses the same three-view tab pattern
with a cross-domain sidebar for navigation.

Uses SidebarPage for consistent sidebar + content layout.

Usage:
    from ui.layouts.activity_layout import create_activity_page

    content = GoalsViewComponents.render_list_view(...)
    return await create_activity_page(content, "goals", request=request)
"""

from typing import TYPE_CHECKING, Any

from ui.activities.sidebar import ACTIVITY_SIDEBAR_ITEMS
from ui.patterns.sidebar import SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


# Domain display names for page titles
DOMAIN_TITLES: dict[str, str] = {
    "tasks": "Tasks",
    "goals": "Goals",
    "habits": "Habits",
    "events": "Events",
    "choices": "Choices",
    "principles": "Principles",
}

# CSS files to include per domain (calendar CSS for time-based domains)
DOMAIN_CSS: dict[str, list[str]] = {
    "tasks": ["/static/css/calendar.css"],
    "goals": ["/static/css/calendar.css"],
    "habits": ["/static/css/calendar.css"],
    "events": ["/static/css/calendar.css"],
    "choices": [],  # Analytics view, no calendar
    "principles": [],  # Analytics view, no calendar
}


async def create_activity_page(
    content: Any,
    domain: str,
    request: "Request | None" = None,
    user_display_name: str = "",
    is_authenticated: bool = True,
    is_admin: bool = False,
) -> "FT":
    """
    Create a standalone activity domain page with sidebar navigation.

    Returns a complete Html document via SidebarPage with cross-domain
    sidebar navigation for switching between activity domains.

    Args:
        content: Main page content (tabs + view content)
        domain: Domain name (tasks, goals, habits, events, choices, principles)
        request: Starlette request object (preferred - auto-detects auth from session)
        user_display_name: Unused, kept for backward compatibility
        is_authenticated: Unused, kept for backward compatibility
        is_admin: Unused, kept for backward compatibility

    Returns:
        Complete Html document with sidebar and activity domain page layout
    """
    title = DOMAIN_TITLES.get(domain, domain.title())

    return await SidebarPage(
        content=content,
        items=ACTIVITY_SIDEBAR_ITEMS,
        active=domain,
        title="Activities",
        storage_key="activities-sidebar",
        page_title=title,
        request=request,
        active_page="activities",
        title_href="/activities",
    )


__all__ = ["create_activity_page", "DOMAIN_TITLES", "DOMAIN_CSS"]
