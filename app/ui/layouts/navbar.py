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

from adapters.inbound.fasthtml_types import Request
from ui.layouts.nav_config import (
    ACTIVITY_DROPDOWN_ITEMS,
    CURRICULUM_DROPDOWN_ITEMS,
    ICON_NAV_ITEMS,
    MAIN_NAV_ITEMS,
    STUDY_DROPDOWN_ITEMS,
    DropdownItem,
    IconNavItem,
    NavItem,
)

# Mapping from icon page_key to its dropdown items
_DROPDOWN_ITEMS_MAP: dict[str, tuple[DropdownItem, ...]] = {
    "curriculum": CURRICULUM_DROPDOWN_ITEMS,
    "study": STUDY_DROPDOWN_ITEMS,
}


def _icon_content(item: IconNavItem) -> tuple[Any, str]:
    """Return (content, extra_css) for an IconNavItem's circular button."""
    if item.icon:
        return UkIcon(item.icon, cls="size-5", aria_hidden="true"), ""
    is_emoji = len(item.letter) > 1 or not item.letter.isascii()
    text_cls = "text-base" if is_emoji else "font-semibold text-sm"
    return item.letter, text_cls


def _icon_nav_link(item: IconNavItem, active_page: str) -> Any:
    """Create a circular letter icon link, with optional hover dropdown."""
    if item.has_dropdown:
        return _icon_nav_dropdown(item, active_page)

    is_active = item.page_key == active_page
    active_cls = "bg-primary/20 text-primary ring-1 ring-primary/30"
    inactive_cls = "bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground"

    content, text_cls = _icon_content(item)

    return A(
        Span(item.label, cls="sr-only"),
        Div(
            content,
            cls=f"size-8 rounded-full flex items-center justify-center {text_cls} "
            f"{active_cls if is_active else inactive_cls}",
            aria_hidden="true",
        ),
        href=item.href,
        cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent",
    )


def _icon_nav_dropdown(item: IconNavItem, active_page: str) -> Div:
    """Create an icon button with a hover dropdown for activity domains."""
    is_active = item.page_key == active_page
    active_cls = "bg-primary/20 text-primary ring-1 ring-primary/30"
    inactive_cls = "bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground"

    content, text_cls = _icon_content(item)

    trigger = Div(
        Span(item.label, cls="sr-only"),
        Div(
            content,
            cls=f"size-8 rounded-full flex items-center justify-center {text_cls} cursor-default "
            f"{active_cls if is_active else inactive_cls}",
            aria_hidden="true",
        ),
        cls="inline-flex items-center justify-center size-11 rounded-full",
        role="button",
        aria_haspopup="true",
        tabindex="0",
    )

    dropdown_items = [
        A(
            UkIcon(di.icon, cls="size-4", aria_hidden="true") if di.icon else None,
            Span(di.label),
            href=di.href,
            cls="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-accent rounded-md",
        )
        for di in _DROPDOWN_ITEMS_MAP.get(item.page_key, ())
    ]

    dropdown_menu = Div(
        *dropdown_items,
        cls="absolute left-0 top-full mt-1 w-44 bg-background border border-border rounded-lg shadow-lg py-1 z-50 "
        "opacity-0 invisible group-hover:opacity-100 group-hover:visible "
        "transition-all duration-150",
        role="menu",
    )

    return Div(
        trigger,
        dropdown_menu,
        cls="relative group",
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
        cls=f"inline-flex items-center justify-center size-11 rounded-full hover:bg-accent {active_cls}",
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
        cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground relative",
        **{"hx-get": "/notifications"},
    )


def _mobile_menu_button() -> Button:
    """Create hamburger/close toggle button for mobile with keyboard navigation."""
    return Button(
        Span("Open menu", cls="sr-only"),
        Span(_hamburger_icon(), **{"x-show": "!mobileMenuOpen"}),
        Span(_close_icon(), **{"x-show": "mobileMenuOpen", "x-cloak": ""}),
        type="button",
        cls="inline-flex items-center justify-center size-11 rounded-md hover:bg-accent sm:hidden",
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


def _avatar_circle(current_user: str, fallback: str = "U") -> Div:
    """Render the colored avatar circle with the user's initial."""
    initial = current_user[0].upper() if current_user else fallback
    hue = _avatar_hue(current_user)
    return Div(
        initial,
        cls="size-8 rounded-full flex items-center justify-center font-medium text-sm",
        style=f"background-color: hsl({hue}, 15%, 88%); color: hsl({hue}, 15%, 50%);",
        aria_hidden="true",
    )


def _logout_menu_item(
    cls: str = "flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-accent rounded-md",
) -> A:
    """Sign-out link with icon and text, used in both avatar dropdown and admin section."""
    return A(
        UkIcon("log-out", cls="size-4", aria_hidden="true"),
        Span("Sign out"),
        href="/logout",
        cls=cls,
    )


def _avatar_dropdown(current_user: str, active_page: str) -> Div:
    """Profile avatar with click-toggle dropdown showing profile + activity domain links.

    Click on avatar opens/closes the dropdown. Profile link is the first item.
    Uses Alpine.js x-data/x-show pattern (same as mobile menu) for reliable show/hide.
    """
    trigger = Button(
        Span("Open user menu", cls="sr-only"),
        _avatar_circle(current_user),
        type="button",
        cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent",
        **{
            "@click": "avatarOpen = !avatarOpen",
            "aria-haspopup": "true",
            ":aria-expanded": "avatarOpen.toString()",
        },
    )

    item_cls = (
        "flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-accent rounded-md"
    )
    close = {"@click": "avatarOpen = false"}

    profile_item = A(
        UkIcon("user", cls="size-4", aria_hidden="true"),
        Span("Profile"),
        href="/profile",
        cls=item_cls,
        **close,
    )

    # Activity domain links
    activity_links = [
        A(
            UkIcon(icon, cls="size-4", aria_hidden="true"),
            Span(label),
            href=href,
            cls=item_cls,
            **close,
        )
        for label, href, icon in [
            ("Tasks", "/tasks", "check-square"),
            ("Goals", "/goals", "target"),
            ("Habits", "/habits", "repeat"),
            ("Events", "/events", "calendar"),
            ("Choices", "/choices", "git-branch"),
            ("Principles", "/principles", "compass"),
        ]
    ]

    logout_item = _logout_menu_item()

    dropdown_menu = Div(
        profile_item,
        Div(cls="my-1 border-t border-border"),
        *activity_links,
        Div(cls="my-1 border-t border-border"),
        logout_item,
        cls="absolute left-0 top-full mt-1 w-48 bg-background border border-border rounded-lg shadow-lg py-1 z-50",
        role="menu",
        **{
            "x-show": "avatarOpen",
            "x-transition": "",
            "@click.outside": "avatarOpen = false",
            "x-cloak": "",
        },
    )

    return Div(
        trigger,
        dropdown_menu,
        cls="relative",
        **{"x-data": "{ avatarOpen: false }"},
    )


def _admin_profile_section(current_user: str) -> Div:
    """Simplified profile section for admin users (desktop only)."""
    return Div(
        A(
            Span("Go to home", cls="sr-only"),
            _avatar_circle(current_user, fallback="A"),
            href="/",
            cls="inline-flex items-center justify-center size-11 rounded-full hover:bg-accent",
        ),
        _logout_menu_item(
            cls="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground px-2 py-1 rounded hover:bg-accent",
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

    # Icon navigation links — shown when not admin; public items shown to all users
    icon_links: list[Any] = []
    if not is_admin:
        icon_links = [
            _icon_nav_link(item, active_page)
            for item in ICON_NAV_ITEMS
            if not item.requires_auth or is_authenticated
        ]

    # Desktop navigation links
    desktop_links = Div(
        *[_nav_link(item, active_page) for item in nav_items],
        cls="hidden sm:flex sm:space-x-1",
    )

    # Mobile navigation links — expand all dropdowns (activity + icon nav) into individual links
    mobile_nav_items = list(nav_items)
    mobile_icon_links: list[Any] = []
    if is_admin:
        for label, href, key in [
            ("Admin", "/admin", "admin"),
            ("Teaching", "/teaching/students", "teaching"),
        ]:
            mobile_icon_links.append(_nav_link(NavItem(label, href, key), active_page, mobile=True))
        mobile_icon_links.append(
            A(
                UkIcon("log-out", cls="size-4", aria_hidden="true"),
                Span("Sign out"),
                href="/logout",
                cls="flex items-center gap-2 rounded-md px-3 py-2 text-base font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )
        )
    else:
        if is_authenticated:
            # Activity domains only shown to authenticated users
            for di in ACTIVITY_DROPDOWN_ITEMS:
                mobile_icon_links.append(
                    _nav_link(
                        NavItem(
                            f"{di.icon} {di.label}" if di.icon else di.label,
                            di.href,
                            di.label.lower(),
                        ),
                        active_page,
                        mobile=True,
                    )
                )
        # Icon nav items — respect requires_auth flag
        for item in ICON_NAV_ITEMS:
            if item.requires_auth and not is_authenticated:
                continue
            if item.has_dropdown:
                for di in _DROPDOWN_ITEMS_MAP.get(item.page_key, ()):
                    mobile_icon_links.append(
                        _nav_link(
                            NavItem(
                                f"{di.icon} {di.label}" if di.icon else di.label,
                                di.href,
                                di.label.lower(),
                            ),
                            active_page,
                            mobile=True,
                        )
                    )
            else:
                mobile_icon_links.append(
                    _nav_link(
                        NavItem(item.label, item.href, item.page_key),
                        active_page,
                        mobile=True,
                    )
                )
    mobile_links = Div(
        Div(
            *mobile_icon_links,
            *[_nav_link(item, active_page, mobile=True) for item in mobile_nav_items],
            cls="space-y-1 px-2 pt-2 pb-3",
            role="menu",
            **{"aria-orientation": "vertical"},
        ),
        cls="sm:hidden",
        **{"x-show": "mobileMenuOpen", "x-transition": "", "x-cloak": ""},
    )

    # Left section: avatar (non-admin authenticated users)
    left_avatar: Any = None
    if is_authenticated and current_user and not is_admin:
        left_avatar = _avatar_dropdown(current_user, active_page)

    # Right section: search + notifications (or admin profile / auth buttons)
    if is_authenticated and current_user and is_admin:
        right_section: Any = _admin_profile_section(current_user)
    elif is_authenticated:
        right_section = Div(
            _search_button(active_page),
            _notification_button(unread_insights),
            cls="flex items-center gap-2",
        )
    else:
        right_section = _auth_buttons()

    # Build left column items
    left_col: list[Any] = [_mobile_menu_button()]
    if is_admin:
        left_col.append(
            A(
                Span("SKUEL", cls="text-lg font-bold text-primary"),
                href="/",
                cls="hidden sm:inline-flex items-center justify-center px-2 py-1 rounded hover:bg-accent",
            )
        )
    if left_avatar is not None:
        left_col.append(left_avatar)
    left_col.extend(icon_links)

    return Nav(
        Div(
            # Left column: Mobile menu button + Avatar + Icon Nav
            Div(
                *left_col,
                cls="flex items-center gap-2 flex-1",
            ),
            # Center column: Desktop navigation links
            desktop_links,
            # Right column: Search + Notifications
            Div(
                right_section,
                cls="flex items-center justify-end flex-1",
            ),
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
        except Exception:  # safety-net: badge count must not crash navbar
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
        except Exception:  # safety-net: badge count must not crash navbar
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
