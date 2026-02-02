"""
Habits Standalone Layout
========================

Standalone page layout for Habits domain with three-view tabs.

Usage:
    from ui.habits.layout import create_habits_page

    content = HabitsViewComponents.render_list_view(...)
    return create_habits_page(content, user_uid)
"""

from typing import TYPE_CHECKING, Any

from ui.layouts.activity_layout import create_activity_page

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


async def create_habits_page(
    content: Any,
    user_display_name: str = "",
    is_authenticated: bool = True,
    is_admin: bool = False,
    request: "Request | None" = None,
) -> "FT":
    """
    Create a standalone habits page with three-view tabs.

    Args:
        content: Main page content (tabs + view content)
        user_display_name: Current user's display name (fallback if no request)
        is_authenticated: Whether user is logged in (fallback if no request)
        is_admin: Whether user has admin role (fallback if no request)
        request: Starlette request object (preferred - auto-detects auth from session)

    Returns:
        Complete habits page layout
    """
    return await create_activity_page(
        content=content,
        domain="habits",
        request=request,
        user_display_name=user_display_name,
        is_authenticated=is_authenticated,
        is_admin=is_admin,
    )


__all__ = ["create_habits_page"]
