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

from fasthtml.common import A, Button, Div, Li, Nav, NotStr, Span, Ul
from starlette.requests import Request

from ui.layouts.nav_config import (
    ADMIN_NAV_ITEM,
    MAIN_NAV_ITEMS,
    PROFILE_DROPDOWN_ITEMS,
    NavItem,
)


def _nav_link(item: NavItem, active_page: str, mobile: bool = False) -> A:
    """Create a navigation link with active state styling and keyboard focus."""
    is_active = item.page_key == active_page

    if mobile:
        base_cls = (
            "block rounded-md px-3 py-2 text-base font-medium focus:outline-none focus:bg-base-300"
        )
        active_cls = "bg-base-300 text-base-content"
        inactive_cls = "text-base-content/70 hover:bg-base-300 hover:text-base-content"
    else:
        base_cls = "rounded-md px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary"
        active_cls = "bg-base-300 text-base-content"
        inactive_cls = "text-base-content/70 hover:bg-base-300 hover:text-base-content"

    cls = f"{base_cls} {active_cls if is_active else inactive_cls}"

    # Explicit hx-boost=false ensures standard HTML navigation
    return A(item.label, href=item.href, cls=cls, **{"hx-boost": "false"})


def _bell_icon() -> NotStr:
    """Create the notification bell SVG icon (decorative - button has sr-only label)."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
        'stroke-width="1.5" stroke="currentColor" class="size-6" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75'
        "a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0"
        'm5.714 0a3 3 0 1 1-5.714 0"/>'
        "</svg>"
    )


def _hamburger_icon() -> NotStr:
    """Create the hamburger menu SVG icon (decorative - button has sr-only label)."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
        'stroke-width="1.5" stroke="currentColor" class="size-6" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/>'
        "</svg>"
    )


def _close_icon() -> NotStr:
    """Create the close X SVG icon (decorative - button has sr-only label)."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
        'stroke-width="1.5" stroke="currentColor" class="size-6" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>'
        "</svg>"
    )


def _search_icon() -> NotStr:
    """Create the search magnifying glass SVG icon (decorative - link has sr-only label)."""
    return NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
        'stroke-width="1.5" stroke="currentColor" class="size-6" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"/>'
        "</svg>"
    )


def _search_button(active_page: str = "") -> A:
    """Create search icon button that navigates to /search."""
    is_active = active_page == "search"
    active_cls = "text-base-content" if is_active else "text-base-content/70 hover:text-base-content"
    return A(
        Span("Search", cls="sr-only"),
        _search_icon(),
        href="/search",
        cls=f"btn btn-ghost btn-circle {active_cls}",
        **{"hx-boost": "false"},
    )


def _curriculum_button(active_page: str = "") -> A:
    """Create green C icon button that navigates to /curriculum."""
    is_active = active_page == "curriculum"
    active_cls = "ring-2 ring-green-500" if is_active else ""
    return A(
        Span("Curriculum", cls="sr-only"),
        Span(
            "C",
            cls="text-lg font-bold text-green-600",
            aria_hidden="true",
        ),
        href="/curriculum",
        cls=f"btn btn-ghost btn-circle {active_cls}",
        **{"hx-boost": "false"},
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
        **{"hx-get": "/notifications", "hx-boost": "false"},  # Navigate to notifications on click
    )


def _mobile_menu_button() -> Button:
    """Create hamburger/close toggle button for mobile with keyboard navigation."""
    return Button(
        Span("Open menu", cls="sr-only"),
        # Show hamburger when closed, X when open
        Span(_hamburger_icon(), **{"x-show": "!mobileMenuOpen"}),
        Span(_close_icon(), **{"x-show": "mobileMenuOpen", "x-cloak": ""}),
        type="button",
        cls="btn btn-ghost btn-square sm:hidden",
        **{
            "@click": "toggleMobile()",
            "@keydown.down.prevent": "toggleMobile()",
            "aria-label": "Toggle menu",
            ":aria-expanded": "mobileMenuOpen.toString()",
            "aria-haspopup": "true",
        },
    )


def _avatar_hue(name: str) -> int:
    """Deterministic hue (0–359) from a name string for per-user avatar color."""
    h = 0
    for c in name:
        h = (h * 31 + ord(c)) % 360
    return h


_DOMAIN_ICONS: dict[str, str] = {
    "profile": "👤",
    "settings": "⚙️",
    "logout": "🚪",
}


def _dropdown_link(item: NavItem, active_page: str) -> Li:
    """Single dropdown menu item with domain icon."""
    is_active = item.page_key == active_page
    icon = _DOMAIN_ICONS.get(item.page_key, "")
    active_cls = "active" if is_active else ""

    return Li(
        A(
            Span(icon, cls="text-base", aria_hidden="true"),
            item.label,
            href=item.href,
            cls=active_cls,
            **{"hx-boost": "false"},
        )
    )


def _profile_dropdown(current_user: str, active_page: str) -> Div:
    """Profile avatar with dropdown menu (Profile, Settings, Sign out).

    Desktop: DaisyUI dropdown appears on click via CSS :focus-within.
    Mobile: Hidden — items appear in hamburger menu instead.
    """
    initial = current_user[0].upper() if current_user else "U"
    hue = _avatar_hue(current_user)

    avatar = Div(
        initial,
        cls="size-8 rounded-full flex items-center justify-center text-white font-medium text-sm",
        style=f"background-color: hsl({hue}, 65%, 45%);",
        aria_hidden="true",
    )

    menu_items = [_dropdown_link(item, active_page) for item in PROFILE_DROPDOWN_ITEMS]

    return Div(
        Div(
            avatar,
            tabindex="0",
            role="button",
            cls="btn btn-ghost btn-circle",
            aria_label="Profile menu",
        ),
        Ul(
            *menu_items,
            tabindex="0",
            cls="dropdown-content menu bg-base-100 rounded-box z-[1] w-48 p-2 shadow-lg border border-base-200",
        ),
        cls="dropdown hidden sm:block",
    )


def _admin_profile_section(current_user: str) -> Div:
    """Simplified profile section for admin users — no activity domain dropdown.

    Admin accounts focus on administration, not personal activity tracking.
    Shows avatar + sign out link only.
    """
    initial = current_user[0].upper() if current_user else "A"
    hue = _avatar_hue(current_user)

    avatar = Div(
        initial,
        cls="size-8 rounded-full flex items-center justify-center text-white font-medium text-sm",
        style=f"background-color: hsl({hue}, 65%, 45%);",
        aria_hidden="true",
    )

    return Div(
        Div(avatar, cls="flex items-center"),
        A(
            "Sign out",
            href="/logout",
            cls="btn btn-ghost btn-sm text-base-content/70 hover:text-base-content",
            **{"hx-boost": "false"},
        ),
        cls="hidden sm:flex items-center gap-2",
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
    is_teacher: bool = False,
    unread_insights: int = 0,
) -> Nav:
    """
    Create the navigation bar using SKUEL patterns.

    Args:
        current_user: Current user's display name or UID
        is_authenticated: Whether user is logged in
        active_page: Current page slug for highlighting (e.g., "profile/hub", "calendar")
        is_admin: Whether user has admin role (shows Admin Dashboard link)
        is_teacher: Whether user has teacher role or higher (shows Teaching link)
        unread_insights: Number of unread insights (Phase 1 integration)

    Returns:
        FastHTML Nav element with Alpine.js state management
    """

    def _should_show_item(item: NavItem) -> bool:
        if item.requires_admin and not is_admin:
            return False
        return not (item.requires_teacher and not (is_teacher or is_admin))

    # Build navigation items list, filtering role-gated items
    nav_items = [item for item in MAIN_NAV_ITEMS if _should_show_item(item)]
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
            role="menu",
            **{"aria-orientation": "vertical"},
        ),
        cls="sm:hidden",
        **{"x-show": "mobileMenuOpen", "x-transition": "", "x-cloak": ""},
    )

    # Mobile account links (shown in hamburger menu for authenticated users)
    # Activity Domains are in the profile sidebar, not the navbar mobile menu
    mobile_domain_links: Div | str = ""
    if is_authenticated:
        mobile_domain_links = Div(
            Div(
                Span(
                    "Account",
                    cls="text-xs font-semibold uppercase tracking-wider opacity-60 px-3 pt-3 pb-1 block",
                ),
                *[_nav_link(item, active_page, mobile=True) for item in PROFILE_DROPDOWN_ITEMS],
                cls="space-y-1 px-2 pb-3 border-t border-base-200 mt-2 pt-2",
            ),
            cls="sm:hidden",
            **{"x-show": "mobileMenuOpen", "x-transition": "", "x-cloak": ""},
        )

    # Profile section (authenticated vs not)
    # Admin users get simplified profile — no activity domain dropdown
    if is_authenticated and current_user and is_admin:
        profile_section = Div(
            _admin_profile_section(current_user),
            _search_button(active_page),
            _curriculum_button(active_page),
            _notification_button(unread_insights),
            cls="flex items-center gap-2",
        )
    elif is_authenticated and current_user:
        profile_section = Div(
            _profile_dropdown(current_user, active_page),
            _search_button(active_page),
            _curriculum_button(active_page),
            _notification_button(unread_insights),
            cls="flex items-center gap-2",
        )
    else:
        profile_section = _auth_buttons()

    return Nav(
        # Main navbar container — 3-column layout: Logo+Profile | Centered Nav | Balance
        Div(
            # Left column: Mobile menu button + Logo + Profile + Notifications
            Div(
                _mobile_menu_button(),
                A(
                    "SKUEL",
                    href="/",
                    cls="text-xl font-bold text-primary flex-shrink-0",
                    **{"hx-boost": "false"},
                ),
                profile_section,
                cls="flex items-center gap-2 flex-1",
            ),
            # Center column: Desktop navigation links (centered via equal flex-1 siblings)
            desktop_links,
            # Right column: Empty for centering balance
            Div(cls="flex-1 hidden sm:block"),
            cls="flex items-center h-16 flex-1 px-4 sm:px-6 lg:px-8",
        ),
        # Mobile menu (collapsible)
        mobile_links,
        # Mobile activity domains (below main nav items)
        mobile_domain_links,
        # Alpine.js state management
        **{"x-data": "navbar()"},
        cls="navbar bg-white border-b border-gray-200 sticky top-0 z-50",
    )


async def create_navbar_for_request(
    request: Request,
    active_page: str = "",
    insight_store: Any = None,
    notification_service: Any = None,
) -> Nav:
    """
    Create navbar with automatic user/admin detection from session.

    This is the recommended way to create navbars in routes. It automatically
    reads user_uid, is_authenticated, and is_admin from the session.

    Args:
        request: Starlette/FastHTML request object
        active_page: Current page slug for highlighting (e.g., "calendar", "search")
        insight_store: Optional InsightStore for fetching unread insight count (Phase 1)
        notification_service: Optional NotificationService for unread notification count

    Returns:
        FastHTML Nav element with proper authentication state
    """

    from core.auth import get_current_user, get_is_admin, get_is_teacher, is_authenticated

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

    # Get unread notification count
    unread_notifications = 0
    if is_authenticated(request) and notification_service:
        try:
            from core.auth import require_authenticated_user

            user_uid = require_authenticated_user(request)
            count_result = await notification_service.get_unread_count(user_uid)
            if not count_result.is_error:
                unread_notifications = count_result.value
        except Exception:
            pass  # Silently fail - navbar should always render

    return create_navbar(
        current_user=get_current_user(request),
        is_authenticated=is_authenticated(request),
        active_page=active_page,
        is_admin=get_is_admin(request),
        is_teacher=get_is_teacher(request),
        unread_insights=unread_insights + unread_notifications,
    )


__all__ = ["create_navbar", "create_navbar_for_request"]
