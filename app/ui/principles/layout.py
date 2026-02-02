"""
Principles Standalone Layout
============================

Standalone page layout for Principles domain with three-view tabs.
Uses Analytics as third tab (not Calendar).

Usage:
    from ui.principles.layout import create_principles_page

    content = PrinciplesViewComponents.render_list_view(...)
    return create_principles_page(content, user_uid)
"""

from typing import TYPE_CHECKING, Any

from ui.layouts.activity_layout import create_activity_page

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


async def create_principles_page(
    content: Any,
    user_display_name: str = "",
    is_authenticated: bool = True,
    is_admin: bool = False,
    request: "Request | None" = None,
) -> "FT":
    """
    Create a standalone principles page with three-view tabs.

    Args:
        content: Main page content (tabs + view content)
        user_display_name: Current user's display name (fallback if no request)
        is_authenticated: Whether user is logged in (fallback if no request)
        is_admin: Whether user has admin role (fallback if no request)
        request: Starlette request object (preferred - auto-detects auth from session)

    Returns:
        Complete principles page layout
    """
    return await create_activity_page(
        content=content,
        domain="principles",
        request=request,
        user_display_name=user_display_name,
        is_authenticated=is_authenticated,
        is_admin=is_admin,
    )


__all__ = ["create_principles_page"]
