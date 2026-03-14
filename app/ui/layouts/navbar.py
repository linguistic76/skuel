"""
Navbar Component - SKUEL Patterns (MonsterUI)
==============================================

Navigation bar using Tailwind utilities + Alpine.js.
Alpine.js handles UI state, FastHTML handles rendering.

Usage:
    from ui.layouts.navbar import create_navbar_for_request

    navbar = create_navbar_for_request(request, active_page="calendar")
"""

from typing import Any

from fasthtml.common import A, Button, Div, Nav, Span
from monsterui.franken import UkIcon
from starlette.requests import Request

from ui.layouts.nav_config import (
    ADMIN_NAV_ITEM,
    ICON_NAV_ITEMS,
    MAIN_NAV_ITEMS,
    IconNavItem,
    NavItem,
)


def _icon_nav_link(item: IconNavItem, active_page: str) -> A:
    """Create a circular letter icon link for the navbar (e.g., 'A' for Activities)."""
    is_active = item.page_key == active_page
    active_cls = "bg-primary/20 text-primary ring-1 ring-primary/30"
    inactive_cls = "bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground"

    return A(
        Span(item.label, cls="sr-only"),
        Div(
            item.letter,
            cls=f"size-8 rounded-full flex items-center justify-center font-semibold text-sm "
            f"{active_cls if is_active else inactive_cls}",
            aria_hidden="true",
        ),
        href=item.href,
        cls="inline-flex items-center justify-center size-10 rounded-full hover:bg-accent",
    )


def _nav_link(item: NavItem, active_page: str, mobile: bool = False) -> A:
    """Create a navigation link with active state styling and keyboard focus."""
    is_active = item.page_key == active_page

    if mobile:
        base_cls = (
            "block rounded-md px-3 py-2 text-base font-medium focus:outline-none focus:bg-accent"
        )
        active_cls = "bg-accent text-accent-foreground"
        inactive_cls = "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
    else:
        base_cls = "rounded-md px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary"
        active_cls = "bg-accent text-accent-foreground"
        inactive_cls = "text-muted-foreground hover:bg-accent hover:text-accent-foreground"

    cls = f"{base_cls} {active_cls if is_active else inactive_cls}"

    return A(item.label, href=item.href, cls=cls)


def _bell_icon():
    """Notification bell icon (decorative - button has sr-only label)."""
    return UkIcon("bell", cls="size-6", aria_hidden="true")


def _hamburger_icon():
    """Hamburger menu icon (decorative - button has sr-only label)."""
    return UkIcon("menu", cls="size-6", aria_hidden="true")


def _close_icon():
    """Close X icon (decorative - button has sr-only label)."""
    return UkIcon("x", cls="size-6", aria_hidden="true")


def _search_icon():
    """Search magnifying glass icon (decorative - link has sr-only label)."""
    return UkIcon("search", cls="size-6", aria_hidden="true")


def _search_button(active_page: str = "") -> A:
    """Create search icon button that navigates to /search."""
    is_active = active_page == "search"
    active_cls = "text-foreground" if is_active else "text-muted-foreground hover:text-foreground"
    return A(
        Span("Search", cls="sr-only"),
        _search_icon(),
        href="/search",
        cls=f"inline-flex items-center justify-center size-10 rounded-full hover:bg-accent {active_cls}",
    )


def _notification_button(unread_count: int = 0) -> Button:
    """Create notification bell button with optional badge."""
    button_content = [
        Span("View notifications", cls="sr-only"),
        _bell_icon(),
    ]

    if unread_count > 0:
        badge = Div(
            Span(
                str(unread_count) if unread_count < 100 else "99+",
                cls="text-xs font-bold text-white",
            ),
            cls="absolute -top-1 -right-1 size-5 rounded-full bg-yellow-500 flex items-center justify-center",
        )
        button_content.append(badge)

    return Button(
        *button_content,
        type="button",
        cls="inline-flex items-center justify-center size-10 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground relative",
        **{"hx-get": "/notifications"},
    )


def _mobile_menu_button() -> Button:
    """Create hamburger/close toggle button for mobile with keyboard navigation."""
    return Button(
        Span("Open menu", cls="sr-only"),
        Span(_hamburger_icon(), **{"x-show": "!mobileMenuOpen"}),
        Span(_close_icon(), **{"x-show": "mobileMenuOpen", "x-cloak": ""}),
        type="button",
        cls="inline-flex items-center justify-center size-10 rounded-md hover:bg-accent sm:hidden",
        **{
            "@click": "toggleMobile()",
            "@keydown.down.prevent": "toggleMobile()",
            "aria-label": "Toggle menu",
            ":aria-expanded": "mobileMenuOpen.toString()",
            "aria-haspopup": "true",
        },
    )


def _avatar_hue(name: str) -> int:
    """Deterministic hue (0-359) from a name string for per-user avatar color."""
    h = 0
    for c in name:
        h = (h * 31 + ord(c)) % 360
    return h


def _logout_icon():
    """Sign-out icon."""
    return UkIcon("log-out", cls="size-6", aria_hidden="true")


def _logout_button() -> A:
    """Sign-out icon button that navigates to /logout."""
    return A(
        Span("Sign out", cls="sr-only"),
        _logout_icon(),
        href="/logout",
        cls="inline-flex items-center justify-center size-10 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground",
    )


def _avatar_link(current_user: str) -> A:
    """Profile avatar as a direct link to /profile (no dropdown)."""
    initial = current_user[0].upper() if current_user else "U"
    hue = _avatar_hue(current_user)

    avatar = Div(
        initial,
        cls="size-8 rounded-full flex items-center justify-center text-white font-medium text-sm",
        style=f"background-color: hsl({hue}, 65%, 45%);",
        aria_hidden="true",
    )

    return A(
        Span("Go to profile", cls="sr-only"),
        avatar,
        href="/profile",
        cls="inline-flex items-center justify-center size-10 rounded-full hover:bg-accent",
    )


def _admin_profile_section(current_user: str) -> Div:
    """Simplified profile section for admin users."""
    initial = current_user[0].upper() if current_user else "A"
    hue = _avatar_hue(current_user)

    avatar = Div(
        initial,
        cls="size-8 rounded-full flex items-center justify-center text-white font-medium text-sm",
        style=f"background-color: hsl({hue}, 65%, 45%);",
        aria_hidden="true",
    )

    return Div(
        A(
            Span("Go to admin dashboard", cls="sr-only"),
            avatar,
            href="/admin",
            cls="inline-flex items-center justify-center size-10 rounded-full hover:bg-accent",
        ),
        A(
            "Sign out",
            href="/logout",
            cls="text-sm text-muted-foreground hover:text-foreground px-2 py-1 rounded hover:bg-accent",
        ),
        cls="hidden sm:flex items-center gap-2",
    )


def _auth_buttons() -> Div:
    """Create login/signup buttons for unauthenticated users."""
    return Div(
        A(
            "Login",
            href="/login",
            cls="text-sm text-muted-foreground hover:text-foreground px-3 py-2 rounded hover:bg-accent",
        ),
        A(
            "Sign Up",
            href="/register",
            cls="text-sm bg-primary text-primary-foreground px-3 py-2 rounded hover:bg-primary/90",
        ),
        cls="flex items-center gap-2",
    )


def create_navbar(
    current_user: str | None = None,
    is_authenticated: bool = False,
    active_page: str = "",
    is_admin: bool = False,
    is_teacher: bool = False,
    unread_insights: int = 0,
) -> Nav:
    """
    Create the navigation bar.

    Args:
        current_user: Current user's display name or UID
        is_authenticated: Whether user is logged in
        active_page: Current page slug for highlighting
        is_admin: Whether user has admin role
        is_teacher: Whether user has teacher role or higher
        unread_insights: Number of unread insights

    Returns:
        FastHTML Nav element with Alpine.js state management
    """

    def _should_show_item(item: NavItem) -> bool:
        if item.requires_admin and not is_admin:
            return False
        if item.hide_for_admin and is_admin:
            return False
        return not (item.requires_teacher and not (is_teacher or is_admin))

    nav_items = [item for item in MAIN_NAV_ITEMS if _should_show_item(item)]
    if is_admin:
        nav_items.insert(0, ADMIN_NAV_ITEM)

    # Icon navigation links (Activities, Learn)
    icon_links: list[A] = []
    if is_authenticated and not is_admin:
        icon_links = [_icon_nav_link(item, active_page) for item in ICON_NAV_ITEMS]

    # Desktop navigation links
    desktop_links = Div(
        *[_nav_link(item, active_page) for item in nav_items],
        cls="hidden sm:flex sm:space-x-1",
    )

    # Mobile navigation links
    mobile_nav_items = list(nav_items)
    mobile_links = Div(
        Div(
            *(
                [
                    _nav_link(
                        NavItem(item.label, item.href, item.page_key),
                        active_page,
                        mobile=True,
                    )
                    for item in ICON_NAV_ITEMS
                ]
                if is_authenticated and not is_admin
                else []
            ),
            *[_nav_link(item, active_page, mobile=True) for item in mobile_nav_items],
            cls="space-y-1 px-2 pt-2 pb-3",
            role="menu",
            **{"aria-orientation": "vertical"},
        ),
        cls="sm:hidden",
        **{"x-show": "mobileMenuOpen", "x-transition": "", "x-cloak": ""},
    )

    # Profile section
    if is_authenticated and current_user and is_admin:
        profile_section = _admin_profile_section(current_user)
    elif is_authenticated and current_user:
        profile_section = Div(
            _avatar_link(current_user),
            _logout_button(),
            _search_button(active_page),
            _notification_button(unread_insights),
            cls="flex items-center gap-2",
        )
    else:
        profile_section = _auth_buttons()

    return Nav(
        Div(
            # Left column: Mobile menu button + Logo + Icon Nav + Profile + Notifications
            Div(
                _mobile_menu_button(),
                A(
                    "SKUEL",
                    href="/",
                    cls="text-xl font-bold text-primary flex-shrink-0",
                ),
                *icon_links,
                profile_section,
                cls="flex items-center gap-2 flex-1",
            ),
            # Center column: Desktop navigation links
            desktop_links,
            # Right column: Empty for centering balance
            Div(cls="flex-1 hidden sm:block"),
            cls="flex items-center h-16 flex-1 px-4 sm:px-6 lg:px-8",
        ),
        mobile_links,
        **{"x-data": "navbar()"},
        cls="bg-background border-b border-border sticky top-0 z-50",
    )


async def create_navbar_for_request(
    request: Request,
    active_page: str = "",
    insight_store: Any = None,
    notification_service: Any = None,
) -> Nav:
    """
    Create navbar with automatic user/admin detection from session.

    Args:
        request: Starlette/FastHTML request object
        active_page: Current page slug for highlighting
        insight_store: Optional InsightStore for fetching unread insight count
        notification_service: Optional NotificationService for unread notification count

    Returns:
        FastHTML Nav element with proper authentication state
    """

    from adapters.inbound.auth import (
        get_current_user,
        get_is_admin,
        get_is_teacher,
        is_authenticated,
    )

    # Get unread insight count
    unread_insights = 0
    if is_authenticated(request) and insight_store:
        try:
            from adapters.inbound.auth import require_authenticated_user

            user_uid = require_authenticated_user(request)
            stats_result = await insight_store.get_insight_stats(user_uid)
            if not stats_result.is_error:
                unread_insights = stats_result.value.get("active_insights", 0)
        except Exception:
            pass

    # Get unread notification count
    unread_notifications = 0
    if is_authenticated(request) and notification_service:
        try:
            from adapters.inbound.auth import require_authenticated_user

            user_uid = require_authenticated_user(request)
            count_result = await notification_service.get_unread_count(user_uid)
            if not count_result.is_error:
                unread_notifications = count_result.value
        except Exception:
            pass

    return create_navbar(
        current_user=get_current_user(request),
        is_authenticated=is_authenticated(request),
        active_page=active_page,
        is_admin=get_is_admin(request),
        is_teacher=get_is_teacher(request),
        unread_insights=unread_insights + unread_notifications,
    )


__all__ = ["create_navbar", "create_navbar_for_request"]
