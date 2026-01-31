"""
Navbar Component - SKUEL Patterns
=================================

Dark themed navigation using DaisyUI patterns.
Alpine.js handles UI state, FastHTML handles rendering.

Version: 3.2 - Explicit hx-boost=false on all navigation links

ARCHITECTURE NOTE:
    HTMX boost from Theme.blue.headers() requires explicit hx-boost="false"
    on anchor links to ensure standard HTML navigation. The global bootstrap
    cancellation script has timing issues on some page types.

Usage:
    from ui.layouts.navbar import create_navbar_for_request

    navbar = create_navbar_for_request(request, active_page="calendar")
"""

from typing import Any

from fasthtml.common import A, Button, Div, Nav, NotStr, Span
from starlette.requests import Request

from ui.layouts.nav_config import (
    ADMIN_NAV_ITEM,
    MAIN_NAV_ITEMS,
    PROFILE_MENU_ITEMS,
    NavItem,
)


def _nav_link(item: NavItem, active_page: str, mobile: bool = False) -> A:
    """Create a navigation link with active state styling."""
    is_active = item.page_key == active_page

    if mobile:
        base_cls = "block rounded-md px-3 py-2 text-base font-medium"
        active_cls = "bg-base-300 text-base-content"
        inactive_cls = "text-base-content/70 hover:bg-base-300 hover:text-base-content"
    else:
        base_cls = "rounded-md px-3 py-2 text-sm font-medium"
        active_cls = "bg-base-300 text-base-content"
        inactive_cls = "text-base-content/70 hover:bg-base-300 hover:text-base-content"

    cls = f"{base_cls} {active_cls if is_active else inactive_cls}"

    # Explicit hx-boost=false ensures standard HTML navigation
    return A(item.label, href=item.href, cls=cls, **{"hx-boost": "false"})


def _bell_icon() -> NotStr:
    """Create the notification bell SVG icon."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
        'stroke-width="1.5" stroke="currentColor" class="size-6">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75'
        "a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0"
        'm5.714 0a3 3 0 1 1-5.714 0"/>'
        "</svg>"
    )


def _hamburger_icon() -> NotStr:
    """Create the hamburger menu SVG icon."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
        'stroke-width="1.5" stroke="currentColor" class="size-6">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/>'
        "</svg>"
    )


def _close_icon() -> NotStr:
    """Create the close X SVG icon."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
        'stroke-width="1.5" stroke="currentColor" class="size-6">'
        '<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>'
        "</svg>"
    )


def _notification_button(unread_count: int = 0) -> Button:
    """Create notification bell button with optional badge.

    Args:
        unread_count: Number of unread insights/notifications

    Returns:
        Button with bell icon and optional count badge
    """
    # Build button content
    button_content = [
        Span("View notifications", cls="sr-only"),
        _bell_icon(),
    ]

    # Add badge if there are unread items (Phase 1 integration)
    if unread_count > 0:
        from fasthtml.common import NotStr

        badge = Div(
            Span(
                str(unread_count) if unread_count < 100 else "99+",
                cls="text-xs font-bold text-white",
            ),
            cls="absolute -top-1 -right-1 size-5 rounded-full bg-warning flex items-center justify-center",
        )
        button_content.append(badge)

    return Button(
        *button_content,
        type="button",
        cls="btn btn-ghost btn-circle text-base-content/70 hover:text-base-content relative",
        **{"hx-get": "/insights", "hx-boost": "false"},  # Navigate to insights on click
    )


def _mobile_menu_button() -> Button:
    """Create hamburger/close toggle button for mobile."""
    return Button(
        Span("Open menu", cls="sr-only"),
        # Show hamburger when closed, X when open
        Span(_hamburger_icon(), **{"x-show": "!mobileMenuOpen"}),
        Span(_close_icon(), **{"x-show": "mobileMenuOpen", "x-cloak": ""}),
        type="button",
        cls="btn btn-ghost btn-square sm:hidden",
        **{
            "@click": "toggleMobile()",
            "aria-label": "Toggle menu",
            ":aria-expanded": "mobileMenuOpen.toString()",
        },
    )


def _profile_dropdown(current_user: str) -> Div:
    """Create profile dropdown using Alpine.js state."""
    user_initial = current_user[0].upper() if current_user else "U"

    return Div(
        # Trigger button
        Button(
            Span("Open user menu", cls="sr-only"),
            Div(
                user_initial,
                cls="size-8 rounded-full bg-primary flex items-center justify-center text-primary-content font-medium text-sm",
            ),
            type="button",
            cls="btn btn-ghost btn-circle",
            **{"@click": "toggleProfile()", "data-profile-trigger": "true"},
        ),
        # Dropdown menu - explicit hx-boost=false for standard navigation
        Div(
            *[
                A(
                    item.label,
                    href=item.href,
                    cls="block px-4 py-2 text-sm text-base-content hover:bg-base-200 first:rounded-t-lg last:rounded-b-lg",
                    **{"hx-boost": "false"},
                )
                for item in PROFILE_MENU_ITEMS
            ],
            id="profile-dropdown",
            cls="absolute right-0 z-50 mt-2 w-48 origin-top-right rounded-lg bg-base-100 shadow-lg ring-1 ring-black/5",
            **{"x-show": "profileMenuOpen", "x-transition": "", "x-cloak": ""},
        ),
        cls="relative",
    )


def _auth_buttons() -> Div:
    """Create login/signup buttons for unauthenticated users."""
    return Div(
        A("Login", href="/login", cls="btn btn-ghost btn-sm", **{"hx-boost": "false"}),
        A("Sign Up", href="/register", cls="btn btn-primary btn-sm", **{"hx-boost": "false"}),
        cls="flex items-center gap-2",
    )


def create_navbar(
    current_user: str | None = None,
    is_authenticated: bool = False,
    active_page: str = "",
    is_admin: bool = False,
    unread_insights: int = 0,
) -> Nav:
    """
    Create the navigation bar using SKUEL patterns.

    Args:
        current_user: Current user's display name or UID
        is_authenticated: Whether user is logged in
        active_page: Current page slug for highlighting (e.g., "profile/hub", "calendar")
        is_admin: Whether user has admin role (shows Admin Dashboard link)
        unread_insights: Number of unread insights (Phase 1 integration)

    Returns:
        FastHTML Nav element with Alpine.js state management
    """
    # Build navigation items list
    nav_items = list(MAIN_NAV_ITEMS)
    if is_admin:
        nav_items.insert(0, ADMIN_NAV_ITEM)

    # Desktop navigation links
    desktop_links = Div(
        *[_nav_link(item, active_page) for item in nav_items],
        cls="hidden sm:flex sm:space-x-1",
    )

    # Mobile navigation links (shown when mobileMenuOpen)
    mobile_links = Div(
        Div(
            *[_nav_link(item, active_page, mobile=True) for item in nav_items],
            cls="space-y-1 px-2 pt-2 pb-3",
        ),
        cls="sm:hidden",
        **{"x-show": "mobileMenuOpen", "x-transition": "", "x-cloak": ""},
    )

    # Profile section (authenticated vs not)
    if is_authenticated and current_user:
        profile_section = Div(
            _notification_button(unread_insights),  # Pass unread count (Phase 1 integration)
            _profile_dropdown(current_user),
            cls="flex items-center gap-2",
        )
    else:
        profile_section = _auth_buttons()

    return Nav(
        # Main navbar container
        Div(
            Div(
                # Left: Mobile menu button
                _mobile_menu_button(),
                # Logo - explicit hx-boost=false for standard navigation
                Div(
                    A(
                        "SKUEL",
                        href="/",
                        cls="text-xl font-bold text-primary",
                        **{"hx-boost": "false"},
                    ),
                    cls="flex-shrink-0 ml-2 sm:ml-0",
                ),
                # Center: Desktop navigation
                Div(
                    desktop_links,
                    cls="hidden sm:flex sm:flex-1 sm:justify-center",
                ),
                # Right: Profile section
                Div(
                    profile_section,
                    cls="flex items-center",
                ),
                cls="flex items-center justify-between h-16",
            ),
            cls="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8",
        ),
        # Mobile menu (collapsible)
        mobile_links,
        # Alpine.js state management
        **{"x-data": "navbar()"},
        cls="navbar bg-base-200 sticky top-0 z-50",
    )


async def create_navbar_for_request(
    request: Request, active_page: str = "", insight_store: Any = None
) -> Nav:
    """
    Create navbar with automatic user/admin detection from session.

    This is the recommended way to create navbars in routes. It automatically
    reads user_uid, is_authenticated, and is_admin from the session.

    Args:
        request: Starlette/FastHTML request object
        active_page: Current page slug for highlighting (e.g., "calendar", "search")
        insight_store: Optional InsightStore for fetching unread insight count (Phase 1)

    Returns:
        FastHTML Nav element with proper authentication state
    """
    from typing import Any

    from core.auth import get_current_user, get_is_admin, is_authenticated

    # Get unread insight count (Phase 1 integration)
    unread_insights = 0
    if is_authenticated(request) and insight_store:
        try:
            from core.auth import require_authenticated_user

            user_uid = require_authenticated_user(request)
            # Get total active insights count
            stats_result = await insight_store.get_insight_stats(user_uid)
            if not stats_result.is_error:
                unread_insights = stats_result.value.get("active_insights", 0)
        except Exception:
            pass  # Silently fail - navbar should always render

    return create_navbar(
        current_user=get_current_user(request),
        is_authenticated=is_authenticated(request),
        active_page=active_page,
        is_admin=get_is_admin(request),
        unread_insights=unread_insights,
    )


__all__ = ["create_navbar", "create_navbar_for_request"]
