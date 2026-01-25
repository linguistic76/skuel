"""
Goals Standalone Layout
=======================

Standalone page layout for Goals domain with three-view tabs.

Usage:
    from ui.goals.layout import create_goals_page

    content = GoalsViewComponents.render_list_view(...)
    return create_goals_page(content, user_uid)
"""

from typing import TYPE_CHECKING, Any

from ui.layouts.activity_layout import create_activity_page

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


def create_goals_page(
    content: Any,
    user_display_name: str = "",
    is_authenticated: bool = True,
    is_admin: bool = False,
    request: "Request | None" = None,
) -> "FT":
    """
    Create a standalone goals page with three-view tabs.

    Args:
        content: Main page content (tabs + view content)
        user_display_name: Current user's display name (fallback if no request)
        is_authenticated: Whether user is logged in (fallback if no request)
        is_admin: Whether user has admin role (fallback if no request)
        request: Starlette request object (preferred - auto-detects auth from session)

    Returns:
        Complete goals page layout

    Usage:
        content = Div(
            GoalsViewComponents.render_view_tabs(active_view="list"),
            GoalsViewComponents.render_list_view(goals, filters, stats),
            cls="p-4 lg:p-8 max-w-7xl mx-auto",
        )
        return create_goals_page(content, "goals", request=request)
    """
    return create_activity_page(
        content=content,
        domain="goals",
        request=request,
        user_display_name=user_display_name,
        is_authenticated=is_authenticated,
        is_admin=is_admin,
    )


__all__ = ["create_goals_page"]
