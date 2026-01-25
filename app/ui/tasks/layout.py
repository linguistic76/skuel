"""
Tasks Standalone Layout
=======================

Standalone page layout for tasks. Delegates to the shared ActivityLayout
for consistency with other Activity Domains.

Version: 2.0 - Delegates to create_activity_page() for Html document consistency

Usage:
    from ui.tasks.layout import create_tasks_page

    content = TasksViewComponents.render_list_view(...)
    return create_tasks_page(content, request=request)
"""

from typing import TYPE_CHECKING, Any

from ui.layouts.activity_layout import create_activity_page

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


def create_tasks_page(
    content: Any,
    user_display_name: str = "",
    title: str = "Tasks",
    is_authenticated: bool = True,
    is_admin: bool = False,
    request: "Request | None" = None,
) -> "FT":
    """
    Create a tasks page using the shared Activity Domain layout.

    Returns a complete Html document with explicit headers. This ensures
    navigation works correctly by avoiding FastHTML's default HTMX wrapping.

    Args:
        content: Main page content (tabs + view content)
        user_display_name: Current user's display name (fallback if no request)
        title: Page title (unused - kept for backward compatibility)
        is_authenticated: Whether user is logged in (fallback if no request)
        is_admin: Whether user has admin role (fallback if no request)
        request: Starlette request object (preferred - auto-detects auth from session)

    Returns:
        Complete Html document with tasks page layout

    Usage:
        content = Div(
            TasksViewComponents.render_view_tabs(active_view="list"),
            TasksViewComponents.render_list_view(tasks, filters, stats),
            cls="p-4 lg:p-8 max-w-7xl mx-auto",
        )
        return create_tasks_page(content, request=request)
    """
    return create_activity_page(
        content=content,
        domain="tasks",
        request=request,
        user_display_name=user_display_name,
        is_authenticated=is_authenticated,
        is_admin=is_admin,
    )


__all__ = ["create_tasks_page"]
