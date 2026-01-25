"""
Events Standalone Layout
========================

Standalone page layout for Events domain with three-view tabs.
Events is calendar-first (Calendar | List | Create).

Usage:
    from ui.events.layout import create_events_page

    content = EventsViewComponents.render_calendar_view(...)
    return create_events_page(content, user_uid)
"""

from typing import TYPE_CHECKING, Any

from ui.layouts.activity_layout import create_activity_page

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


def create_events_page(
    content: Any,
    user_display_name: str = "",
    is_authenticated: bool = True,
    is_admin: bool = False,
    request: "Request | None" = None,
) -> "FT":
    """
    Create a standalone events page with three-view tabs.

    Args:
        content: Main page content (tabs + view content)
        user_display_name: Current user's display name (fallback if no request)
        is_authenticated: Whether user is logged in (fallback if no request)
        is_admin: Whether user has admin role (fallback if no request)
        request: Starlette request object (preferred - auto-detects auth from session)

    Returns:
        Complete events page layout
    """
    return create_activity_page(
        content=content,
        domain="events",
        request=request,
        user_display_name=user_display_name,
        is_authenticated=is_authenticated,
        is_admin=is_admin,
    )


__all__ = ["create_events_page"]
