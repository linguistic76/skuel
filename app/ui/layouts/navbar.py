"""
Navbar Component - SKUEL Patterns (MonsterUI)
==============================================

Navigation bar using Tailwind utilities.

Layout:
- Mobile: slim top bar (brand + bell + signout) + fixed bottom nav (Hub/Tasks+/Explore/Search)
- Desktop: slim top bar (brand + text nav links + search + bell + signout)

Usage:
    from ui.layouts.navbar import create_navbar, create_bottom_nav
    from ui.layouts.navbar import create_navbar_for_request, create_bottom_nav_for_request
"""

from typing import Any

from fasthtml.common import A, Div, Nav, Span
from monsterui.franken import UkIcon

from adapters.inbound.fasthtml_types import Request
from ui.layouts.nav_config import (
    ICON_NAV_ITEMS,
    MAIN_NAV_ITEMS,
    IconNavItem,
    NavItem,
)


def _nav_link(item: NavItem, active_page: str) -> A:
    """Desktop text nav link with active state."""
    is_active = item.page_key == active_page
    active_cls = "bg-accent text-accent-foreground"
    inactive_cls = "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
    cls = f"rounded-md px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary {active_cls if is_active else inactive_cls}"
    return A(item.label, href=item.href, cls=cls)


def _search_button(active_page: str = "", desktop_only: bool = False) -> A:
    """Search icon button linking to /search."""
    is_active = active_page == "search"
    color_cls = "text-foreground" if is_active else "text-muted-foreground hover:text-foreground"
    visibility = "hidden sm:inline-flex" if desktop_only else "inline-flex"
    return A(
        Span("Search", cls="sr-only"),
        UkIcon("search", cls="size-6", aria_hidden="true"),
        href="/search",
        cls=f"{visibility} items-center justify-center size-11 rounded-full hover:bg-accent {color_cls}",
    )


def _signout_button() -> A:
    """Sign-out icon button."""
    return A(
        Span("Sign out", cls="sr-only"),
        UkIcon("log-out", cls="size-6", aria_hidden="true"),
        href="/logout",
        cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground",
    )


def _notification_button(unread_count: int = 0) -> Any:
    """Notification bell icon button with optional unread badge."""
    from fasthtml.common import Button

    button_content: list[Any] = [
        Span("View notifications", cls="sr-only"),
        UkIcon("bell", cls="size-6", aria_hidden="true"),
    ]
    if unread_count > 0:
        button_content.append(
            Div(
                Span(
                    str(unread_count) if unread_count < 100 else "99+",
                    cls="text-xs font-bold text-white",
                ),
                cls="absolute -top-1 -right-1 size-5 rounded-full bg-yellow-500 flex items-center justify-center",
            )
        )
    return Button(
        *button_content,
        type="button",
        cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground relative",
        **{"hx-get": "/notifications"},
    )


def _notification_badge_placeholder() -> Any:
    """Bell button placeholder — renders immediately with 0 count, lazy-loads actual count."""
    return Div(
        _notification_button(0),
        id="notification-bell",
        hx_get="/api/navbar/notification-badge",
        hx_trigger="load",
        hx_swap="outerHTML",
        cls="relative",
    )


def _avatar_hue(name: str) -> int:
    """Deterministic hue (0-359) from a name string for per-user avatar color."""
    h = 0
    for c in name:
        h = (h * 31 + ord(c)) % 360
    return h


def _avatar_circle(current_user: str, fallback: str = "U") -> Div:
    """Colored avatar circle with the user's initial."""
    initial = current_user[0].upper() if current_user else fallback
    hue = _avatar_hue(current_user)
    return Div(
        initial,
        cls="size-8 rounded-full flex items-center justify-center font-medium text-sm",
        style=f"background-color: hsl({hue}, 15%, 88%); color: hsl({hue}, 15%, 50%);",
        aria_hidden="true",
    )


def _admin_right_section(current_user: str) -> Div:
    """Admin right section: avatar link + sign out."""
    return Div(
        A(
            Span("Go to home", cls="sr-only"),
            _avatar_circle(current_user, fallback="A"),
            href="/",
            cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent",
        ),
        A(
            UkIcon("log-out", cls="size-4", aria_hidden="true"),
            Span("Sign out"),
            href="/logout",
            cls="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground px-2 py-1 rounded hover:bg-accent",
        ),
        cls="flex items-center gap-2",
    )


def _auth_buttons() -> Div:
    """Login/signup buttons for unauthenticated users."""
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
    Create the slim top navigation bar.

    Mobile: brand + bell + signout (search lives in bottom nav).
    Desktop: brand + text nav links + search + bell + signout.

    Args:
        current_user: Current user's display name or UID
        is_authenticated: Whether user is logged in
        active_page: Current page slug for highlighting
        is_admin: Whether user has admin role
        is_teacher: Whether user has teacher role or higher
        unread_insights: Number of unread insights/notifications

    Returns:
        FastHTML Nav element (slim top bar)
    """
    if is_admin:
        # Admin: brand on left, avatar + signout on right
        return Nav(
            Div(
                A(
                    Span("SKUEL", cls="text-lg font-bold text-primary"),
                    href="/",
                    cls="hidden sm:inline-flex items-center justify-center px-2 py-1 rounded hover:bg-accent",
                ),
                Div(
                    _admin_right_section(current_user or "") if current_user else Div(),
                    cls="flex items-center justify-end flex-1",
                ),
                cls="flex items-center h-14 flex-1 px-4 sm:px-6 lg:px-8",
            ),
            cls="bg-background border-b border-border sticky top-0 z-40",
        )

    # --- Regular user top bar ---

    # Desktop center: text links derived from ICON_NAV_ITEMS + teacher link
    def _should_show(item: IconNavItem) -> bool:
        # Hub is omitted — the SKUEL brand link already goes to /home
        if item.page_key == "home":
            return False
        return not (item.requires_auth and not is_authenticated)

    desktop_links = Div(
        *[
            _nav_link(NavItem(item.label, item.href, item.page_key), active_page)
            for item in ICON_NAV_ITEMS
            if _should_show(item)
        ],
        *[
            _nav_link(item, active_page)
            for item in MAIN_NAV_ITEMS
            if not (item.requires_admin and not is_admin)
            and not (item.requires_teacher and not (is_teacher or is_admin))
            and not (item.hide_for_admin and is_admin)
        ],
        cls="hidden sm:flex items-center gap-1",
    )

    # Right section
    if is_authenticated:
        right_section: Any = Div(
            _search_button(active_page, desktop_only=True),
            _notification_badge_placeholder(),
            _signout_button(),
            cls="flex items-center gap-1",
        )
    else:
        right_section = _auth_buttons()

    return Nav(
        Div(
            # Left: brand
            A(
                "SKUEL",
                href="/home" if is_authenticated else "/",
                cls="text-sm font-bold text-primary px-2 py-1 rounded hover:bg-accent",
            ),
            # Center: desktop nav links
            desktop_links,
            # Right: utilities
            Div(right_section, cls="flex items-center justify-end flex-1"),
            cls="flex items-center h-14 px-4 sm:px-6",
        ),
        cls="bg-background border-b border-border sticky top-0 z-40",
        **{"aria-label": "Main navigation"},
    )


def create_bottom_nav(
    is_authenticated: bool = False,
    active_page: str = "",
    is_admin: bool = False,
) -> Any:
    """
    Create the mobile-only fixed bottom navigation bar.

    Shown only on mobile (sm:hidden) for authenticated non-admin users.
    Four tabs: Hub | Tasks+ | Explore | Search.
    Respects iOS safe-area-inset-bottom for notched devices.

    Args:
        is_authenticated: Whether user is logged in
        active_page: Current page slug for active tab highlighting
        is_admin: Whether user has admin role

    Returns:
        FastHTML Nav element or empty Div if not applicable
    """
    if not is_authenticated or is_admin:
        return Div()

    items = [
        ("home", "home", "Hub", "/home"),
        ("check-square", "tasks", "Tasks+", "/tasks"),
        ("compass", "explore", "Explore", "/explore"),
        ("search", "search", "Search", "/search"),
    ]

    nav_items = []
    for icon_name, page_key, label, href in items:
        is_active = active_page == page_key
        color_cls = "text-primary" if is_active else "text-muted-foreground"
        extra: dict[str, Any] = {"aria-current": "page"} if is_active else {}
        nav_items.append(
            A(
                UkIcon(icon_name, cls="size-5", aria_hidden="true"),
                Span(label, cls="text-xs mt-0.5"),
                Span(f"Go to {label}", cls="sr-only"),
                href=href,
                cls=f"flex flex-col items-center justify-center gap-0.5 flex-1 py-2 {color_cls} hover:text-foreground transition-colors",
                **extra,
            )
        )

    return Nav(
        *nav_items,
        cls="fixed bottom-0 inset-x-0 z-40 sm:hidden bg-background border-t border-border flex items-stretch h-16",
        style="padding-bottom: env(safe-area-inset-bottom)",
        **{"aria-label": "Primary navigation"},
    )


async def create_navbar_for_request(
    request: Request,
    active_page: str = "",
    insight_store: Any = None,
    notification_service: Any = None,
) -> Nav:
    """
    Create top navbar with automatic user/admin detection from session.

    Badge counts (notifications, insights) are lazy-loaded via HTMX from
    /api/navbar/notification-badge — not fetched here to keep page render fast.

    Args:
        request: Starlette/FastHTML request object
        active_page: Current page slug for highlighting
        insight_store: Unused — retained for signature compatibility
        notification_service: Unused — retained for signature compatibility

    Returns:
        FastHTML Nav element (slim top bar)
    """
    from adapters.inbound.auth import (
        get_current_user,
        get_is_admin,
        get_is_teacher,
        is_authenticated,
    )

    return create_navbar(
        current_user=get_current_user(request),
        is_authenticated=is_authenticated(request),
        active_page=active_page,
        is_admin=get_is_admin(request),
        is_teacher=get_is_teacher(request),
        unread_insights=0,
    )


async def create_bottom_nav_for_request(
    request: Request,
    active_page: str = "",
) -> Any:
    """
    Create mobile bottom nav with automatic auth/admin detection from session.

    Args:
        request: Starlette/FastHTML request object
        active_page: Current page slug for active tab highlighting

    Returns:
        FastHTML Nav element or empty Div
    """
    from adapters.inbound.auth import get_is_admin, is_authenticated

    return create_bottom_nav(
        is_authenticated=is_authenticated(request),
        active_page=active_page,
        is_admin=get_is_admin(request),
    )


__all__ = [
    "create_bottom_nav",
    "create_bottom_nav_for_request",
    "create_navbar",
    "create_navbar_for_request",
    "_notification_button",
    "_notification_badge_placeholder",
]
