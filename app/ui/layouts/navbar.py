"""
Navbar Component - SKUEL Patterns
==============================================

Navigation bar using Tailwind utilities.

Layout:
- Mobile: slim top bar (brand + bell + signout) + fixed bottom nav derived
  from ``ICON_NAV_ITEMS`` with Search appended
- Desktop: slim top bar (brand + text nav links + search + bell + signout)

Usage:
    from ui.layouts.navbar import create_navbar, create_bottom_nav
    from ui.layouts.navbar import create_navbar_for_request, create_bottom_nav_for_request
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, Nav, Span

from ui.components import Icon
from ui.layouts.nav_config import (
    ICON_NAV_ITEMS,
    MAIN_NAV_ITEMS,
    IconNavItem,
    NavItem,
)

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import Request


def _visible_icon_items(
    *,
    is_authenticated: bool,
    is_admin: bool,
    is_teacher: bool,
    include_today: bool,
) -> list[IconNavItem]:
    """Filter ICON_NAV_ITEMS by the viewer's auth/role flags.

    Shared by desktop text links and the mobile bottom nav so both surfaces
    stay in lockstep with nav_config. Desktop excludes Today because the brand
    link already goes to /today; mobile keeps it (include_today=True).
    """
    visible: list[IconNavItem] = []
    for item in ICON_NAV_ITEMS:
        if item.page_key == "today" and not include_today:
            continue
        if item.requires_auth and not is_authenticated:
            continue
        if item.hide_for_admin and is_admin:
            continue
        if item.hide_for_teacher and (is_teacher or is_admin):
            continue
        visible.append(item)
    return visible


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
        Icon("search", cls="size-6", aria_hidden="true"),
        href="/search",
        cls=f"{visibility} items-center justify-center size-11 rounded-full hover:bg-accent {color_cls}",
    )


def _signout_button() -> A:
    """Sign-out icon button."""
    return A(
        Span("Sign out", cls="sr-only"),
        Icon("log-out", cls="size-6", aria_hidden="true"),
        href="/logout",
        cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground",
    )


def _notification_button(unread_count: int = 0) -> A:
    """Notification bell icon link (to /notifications) with optional unread badge."""
    button_content: list[Any] = [
        Span("View notifications", cls="sr-only"),
        Icon("bell", cls="size-6", aria_hidden="true"),
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
    return A(
        *button_content,
        href="/notifications",
        cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground relative",
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


def _shared_inbox_button(active_page: str) -> A:
    """Inbox icon linking to /profile/shared — content shared directly with you."""
    is_active = active_page == "shared"
    color_cls = "text-foreground" if is_active else "text-muted-foreground hover:text-foreground"
    return A(
        Span("Shared with me", cls="sr-only"),
        Icon("inbox", cls="size-6", aria_hidden="true"),
        href="/profile/shared",
        cls=f"inline-flex items-center justify-center size-11 rounded-full hover:bg-accent {color_cls}",
        **({"aria-current": "page"} if is_active else {}),
    )


def _askesis_button(active_page: str) -> A:
    """Flame icon linking to /askesis — the ZPD-aware practice companion."""
    is_active = active_page == "askesis"
    color_cls = "text-foreground" if is_active else "text-muted-foreground hover:text-foreground"
    return A(
        Span("Askesis", cls="sr-only"),
        Icon("flame", cls="size-6", aria_hidden="true"),
        href="/askesis",
        cls=f"inline-flex items-center justify-center size-11 rounded-full hover:bg-accent {color_cls}",
        **({"aria-current": "page"} if is_active else {}),
    )


def _profile_button(current_user: str, active_page: str) -> A:
    """Avatar circle linking to /profile — regular user's entry point to their hub."""
    is_active = active_page == "profile"
    ring = " ring-2 ring-primary" if is_active else ""
    return A(
        Span("Profile", cls="sr-only"),
        _avatar_circle(current_user),
        href="/profile",
        cls=("inline-flex items-center justify-center size-11 rounded-full hover:bg-accent" + ring),
        **({"aria-current": "page"} if is_active else {}),
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
            Icon("log-out", cls="size-4", aria_hidden="true"),
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

    Returns:
        FastHTML Nav element (slim top bar)
    """
    if is_admin:
        # Admin: hamburger (mobile) + brand + avatar/signout
        # Mobile dropdown links to /admin and /teaching/students (no bottom nav for admins)
        return Nav(
            Div(
                # Hamburger button — mobile only
                Div(
                    A(
                        Span("Menu", cls="sr-only"),
                        Icon("menu", cls="size-5", aria_hidden="true"),
                        cls="sm:hidden inline-flex items-center justify-center size-11 rounded-full"
                        " hover:bg-accent text-muted-foreground hover:text-foreground cursor-pointer",
                        **{"@click": "mobileMenuOpen = !mobileMenuOpen", "aria-label": "Open menu"},
                    ),
                    # Mobile dropdown panel — fixed below navbar, sm:hidden
                    Div(
                        A("Admin", href="/admin", cls="block px-4 py-3 text-sm hover:bg-accent"),
                        A(
                            "Teaching",
                            href="/teaching/students",
                            cls="block px-4 py-3 text-sm hover:bg-accent",
                        ),
                        A(
                            "Sign out",
                            href="/logout",
                            cls="block px-4 py-3 text-sm text-destructive hover:bg-accent border-t border-border",
                        ),
                        cls="sm:hidden fixed top-14 inset-x-0 z-50 bg-background border-b border-border shadow-md",
                        **{
                            "x-show": "mobileMenuOpen",
                            "@click.away": "mobileMenuOpen = false",
                            "x-cloak": True,
                        },
                    ),
                    **{"x-data": "{ mobileMenuOpen: false }"},
                ),
                # Brand — always visible
                A(
                    Span("SKUEL", cls="text-lg font-bold text-primary"),
                    href="/",
                    cls="inline-flex items-center justify-center px-2 py-1 rounded hover:bg-accent",
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

    # Desktop center: text links derived from ICON_NAV_ITEMS + teacher link.
    # Today is omitted from desktop because the SKUEL brand link already goes to /today.
    desktop_links = Div(
        *[
            _nav_link(NavItem(item.label, item.href, item.page_key), active_page)
            for item in _visible_icon_items(
                is_authenticated=is_authenticated,
                is_admin=is_admin,
                is_teacher=is_teacher,
                include_today=False,
            )
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
            _askesis_button(active_page),
            _shared_inbox_button(active_page),
            _notification_badge_placeholder(),
            _profile_button(current_user or "", active_page),
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
                href="/explore" if is_authenticated else "/",
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


_SEARCH_TAB = IconNavItem(
    label="Search",
    letter="",
    href="/search",
    page_key="search",
    requires_auth=True,
    icon="search",
)


def _bottom_nav_tab(item: IconNavItem, active_page: str) -> A:
    is_active = active_page == item.page_key
    color_cls = "text-primary" if is_active else "text-muted-foreground"
    extra: dict[str, Any] = {"aria-current": "page"} if is_active else {}
    return A(
        Icon(item.icon or "circle", cls="size-5", aria_hidden="true"),
        Span(item.label, cls="text-xs mt-0.5"),
        Span(f"Go to {item.label}", cls="sr-only"),
        href=item.href,
        cls=(
            "flex flex-col items-center justify-center gap-0.5 flex-1 py-2"
            f" {color_cls} hover:text-foreground transition-colors"
        ),
        **extra,
    )


def create_bottom_nav(
    is_authenticated: bool = False,
    active_page: str = "",
    is_admin: bool = False,
    is_teacher: bool = False,
) -> Any:
    """
    Create the mobile-only fixed bottom navigation bar.

    Shown only on mobile (sm:hidden) for authenticated non-admin users.
    Tabs are derived from ``ICON_NAV_ITEMS`` (same spec as the desktop center
    menu) with Search appended — desktop keeps Search as a separate icon in
    the right section, mobile folds it into the bottom nav.
    Respects iOS safe-area-inset-bottom for notched devices.

    Args:
        is_authenticated: Whether user is logged in
        active_page: Current page slug for active tab highlighting
        is_admin: Whether user has admin role
        is_teacher: Whether user has teacher role or higher

    Returns:
        FastHTML Nav element or empty Div if not applicable
    """
    if not is_authenticated or is_admin:
        return Div()

    items = [
        *_visible_icon_items(
            is_authenticated=is_authenticated,
            is_admin=is_admin,
            is_teacher=is_teacher,
            include_today=True,
        ),
        _SEARCH_TAB,
    ]

    return Nav(
        *[_bottom_nav_tab(item, active_page) for item in items],
        cls="fixed bottom-0 inset-x-0 z-40 sm:hidden bg-background border-t border-border flex items-stretch h-16",
        style="padding-bottom: env(safe-area-inset-bottom)",
        **{"aria-label": "Primary navigation"},
    )


async def create_navbar_for_request(
    request: Request,
    active_page: str = "",
) -> Nav:
    """
    Create top navbar with automatic user/admin detection from session.

    Badge counts (notifications, insights) are lazy-loaded via HTMX from
    /api/navbar/notification-badge — not fetched here to keep page render fast.

    Args:
        request: Starlette/FastHTML request object
        active_page: Current page slug for highlighting

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
    from adapters.inbound.auth import get_is_admin, get_is_teacher, is_authenticated

    return create_bottom_nav(
        is_authenticated=is_authenticated(request),
        active_page=active_page,
        is_admin=get_is_admin(request),
        is_teacher=get_is_teacher(request),
    )


__all__ = [
    "create_bottom_nav",
    "create_bottom_nav_for_request",
    "create_navbar",
    "create_navbar_for_request",
    "_notification_button",
    "_notification_badge_placeholder",
]
