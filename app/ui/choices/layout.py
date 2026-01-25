"""
Choices Standalone Layout
=========================

Standalone page layout for Choices domain with three-view tabs.
Uses Analytics as third tab (not Calendar).

Usage:
    from ui.choices.layout import create_choices_page

    content = ChoicesViewComponents.render_list_view(...)
    return create_choices_page(content, user_uid)
"""

from typing import TYPE_CHECKING, Any

from ui.layouts.activity_layout import create_activity_page

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


def create_choices_page(
    content: Any,
    user_display_name: str = "",
    is_authenticated: bool = True,
    is_admin: bool = False,
    request: "Request | None" = None,
) -> "FT":
    """
    Create a standalone choices page with three-view tabs.

    Args:
        content: Main page content (tabs + view content)
        user_display_name: Current user's display name (fallback if no request)
        is_authenticated: Whether user is logged in (fallback if no request)
        is_admin: Whether user has admin role (fallback if no request)
        request: Starlette request object (preferred - auto-detects auth from session)

    Returns:
        Complete choices page layout
    """
    return create_activity_page(
        content=content,
        domain="choices",
        request=request,
        user_display_name=user_display_name,
        is_authenticated=is_authenticated,
        is_admin=is_admin,
    )


__all__ = ["create_choices_page"]
