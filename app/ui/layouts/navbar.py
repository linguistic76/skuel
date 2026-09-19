"""
Navbar Component - SKUEL Patterns
==============================================

The global chrome — one top bar and one bottom nav for every role.

Layout:
- Phone (<sm): slim top bar (brand + askesis + inbox + bell + avatar) + a
  fixed bottom nav of the ``ICON_NAV_ITEMS`` section doors; sign-out is a
  row on /settings
- sm+: the same bar plus the ``ICON_NAV_ITEMS`` centre links and the
  sign-out icon; no bottom nav
- lg+: the role-gated doors (``MAIN_NAV_ITEMS``) join the centre links;
  below lg they are rows on /settings

Every item is a direct link — the navbar carries no dropdown. The periodic notes
are reached from the Tasks+ sidebar's Journal row (today's note) and, inside a
note, the period rail (``ui/journals/chat_page.py``).

Usage:
    from ui.layouts.navbar import create_navbar, create_bottom_nav
    from ui.layouts.navbar import create_navbar_for_request, create_bottom_nav_for_request
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, Nav, Span

from core.utils.auth_context import current_auth_state
from ui.components import Icon
from ui.layouts.nav_config import ICON_NAV_ITEMS, MAIN_NAV_ITEMS, IconNavItem, NavItem

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import Request


def _visible_icon_items(*, is_authenticated: bool) -> list[IconNavItem]:
    """The section doors this viewer sees — the same list for the desktop
    centre links and the phone bottom nav, so both surfaces stay in lockstep
    with nav_config. The only gate is authentication: every authenticated
    role sees every door."""
    return [item for item in ICON_NAV_ITEMS if is_authenticated or not item.requires_auth]


def _visible_main_items(*, is_admin: bool, is_teacher: bool) -> list[NavItem]:
    """The role-gated doors this viewer sees — the same list for the desktop
    centre links and the phone rows on /settings."""
    return [
        item for item in MAIN_NAV_ITEMS if item.visible_to(is_admin=is_admin, is_teacher=is_teacher)
    ]


# The role doors join the centre links at lg+ only: at 640 the four section
# doors plus the icon cluster fill the bar, and Teaching + Admin do not fit
# in any font. Below lg they are the ``role_nav_rows`` on /settings.
_ROLE_LINK_BREAKPOINT_CLS = "hidden lg:block"
_ROLE_ROW_BREAKPOINT_CLS = "lg:hidden"


def _nav_link(label: str, href: str, *, is_active: bool, extra_cls: str = "") -> A:
    """Desktop text nav link with active state."""
    active_cls = "bg-accent text-accent-foreground"
    inactive_cls = "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
    cls = f"rounded-md px-2 py-2 text-sm font-medium focus:outline-hidden focus:ring-2 focus:ring-primary {active_cls if is_active else inactive_cls} {extra_cls}".rstrip()
    return A(label, href=href, cls=cls, **({"aria-current": "page"} if is_active else {}))


def _signout_button() -> A:
    """Sign-out icon button — desktop only.

    It is the one top-bar icon whose destination is an action rather than a
    surface, and an account action is what the settings page is for: phones
    reach it from ``signout_row`` on /settings, so exactly one door exists at
    every width.
    """
    return A(
        Span("Sign out", cls="sr-only"),
        Icon("log-out", cls="size-6", aria_hidden="true"),
        href="/logout",
        cls="hidden sm:inline-flex items-center justify-center size-11 rounded-full hover:bg-accent text-muted-foreground hover:text-foreground",
    )


# A /settings row is a top-bar item's counterpart below the width that item
# appears at; each row carries its own item's breakpoint.
_SETTINGS_ROW_CLS = (
    "flex items-center justify-center gap-2 mb-4 px-3 py-2 rounded-md"
    " border border-border text-sm text-muted-foreground hover:bg-accent"
    " hover:text-foreground"
)


def signout_row() -> A:
    """Sign out — the phone's only door, since the navbar icon is desktop-only.

    ``sm:hidden`` mirrors ``_signout_button``'s ``hidden sm:inline-flex``:
    exactly one sign-out door at every width, never two. Rendered FIRST on
    /settings, outside any HTMX fragment or ``x-cloak`` — signing out never
    waits for a fragment or for Alpine.
    """
    return A(
        Icon("log-out", cls="size-4", aria_hidden="true"),
        Span("Sign out"),
        href="/logout",
        cls=f"sm:hidden {_SETTINGS_ROW_CLS}",
    )


def role_nav_rows(*, is_admin: bool, is_teacher: bool) -> list[A]:
    """The role-gated section doors as rows for /settings below lg.

    The centre links carry ``MAIN_NAV_ITEMS`` at lg+ and the bottom nav
    carries none, so below lg these rows are an admin's or teacher's only
    door to their section — the same spec, filtered by the same predicate,
    ``lg:hidden`` where the centre links are ``hidden lg:block``.
    """
    return [
        A(item.label, href=item.href, cls=f"{_ROLE_ROW_BREAKPOINT_CLS} {_SETTINGS_ROW_CLS}")
        for item in _visible_main_items(is_admin=is_admin, is_teacher=is_teacher)
    ]


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


def _account_button(current_user: str, active_page: str) -> A:
    """Avatar circle linking to /settings — the account page (preferences,
    devices, and on phones the sign-out and role rows)."""
    is_active = active_page == "settings"
    ring = " ring-2 ring-primary" if is_active else ""
    return A(
        Span("Settings", cls="sr-only"),
        _avatar_circle(current_user),
        href="/settings",
        cls=("inline-flex items-center justify-center size-11 rounded-full hover:bg-accent" + ring),
        **({"aria-current": "page"} if is_active else {}),
    )


def _auth_buttons() -> Div:
    """Login/signup buttons for unauthenticated users."""
    return Div(
        A(
            "Login",
            href="/login",
            cls="text-sm text-muted-foreground hover:text-foreground px-3 py-2 rounded-sm hover:bg-accent",
        ),
        A(
            "Sign Up",
            href="/register",
            cls="text-sm bg-primary text-primary-foreground px-3 py-2 rounded-sm hover:bg-primary/90",
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
    Create the slim top navigation bar — the same bar for every role.

    Phone: brand + askesis + inbox + bell + avatar (the section doors live
    in the bottom nav, sign-out and the role doors on /settings).
    sm+: the same, plus the section-door centre links and sign-out.
    lg+: the role doors join the centre links.

    Args:
        current_user: Current user's display name or UID
        is_authenticated: Whether user is logged in
        active_page: Current page's section key for highlighting
        is_admin: Whether user has admin role
        is_teacher: Whether user has teacher role or higher

    Returns:
        FastHTML Nav element (slim top bar)
    """
    # Centre links: the section doors (sm+), then the role-gated doors (lg+)
    # — both from the one spec the bottom nav and the /settings rows render.
    desktop_links = Div(
        *[
            _nav_link(item.label, item.href, is_active=item.lights(active_page))
            for item in _visible_icon_items(is_authenticated=is_authenticated)
        ],
        *[
            _nav_link(
                item.label,
                item.href,
                is_active=item.page_key == active_page,
                extra_cls=_ROLE_LINK_BREAKPOINT_CLS,
            )
            for item in _visible_main_items(is_admin=is_admin, is_teacher=is_teacher)
        ],
        cls="hidden sm:flex items-center gap-1",
    )

    # Right section
    if is_authenticated:
        right_section: Any = Div(
            _askesis_button(active_page),
            _shared_inbox_button(active_page),
            _notification_badge_placeholder(),
            _account_button(current_user or "", active_page),
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
                cls="text-sm font-bold text-primary px-2 py-1 rounded-sm hover:bg-accent",
            ),
            # Center: desktop nav links
            desktop_links,
            # Right: utilities
            Div(right_section, cls="flex items-center justify-end flex-1"),
            cls="flex items-center h-full px-4 sm:px-6",
        ),
        cls="h-14 bg-background border-b border-border sticky top-0 z-40",
        **{"aria-label": "Main navigation"},
    )


def _bottom_nav_tab(item: IconNavItem, active_page: str) -> A:
    """One tab: icon over label — the label IS the accessible name."""
    is_active = item.lights(active_page)
    color_cls = "text-primary" if is_active else "text-muted-foreground"
    extra: dict[str, Any] = {"aria-current": "page"} if is_active else {}
    return A(
        Icon(item.icon, cls="size-5", aria_hidden="true"),
        Span(item.label, cls="text-xs mt-0.5"),
        href=item.href,
        cls=(
            "flex flex-col items-center justify-center gap-0.5 flex-1 py-2"
            f" {color_cls} hover:text-foreground transition-colors"
        ),
        **extra,
    )


def create_bottom_nav(is_authenticated: bool = False, active_page: str = "") -> Nav:
    """
    Create the phone-only fixed bottom navigation bar.

    Shown below sm for every viewer: the ``ICON_NAV_ITEMS`` section doors
    (the same spec as the desktop centre links) — four tabs for every
    authenticated role, the two ``requires_auth=False`` doors for an
    anonymous visitor.
    The bar is 4rem tall plus the device's home-indicator inset: it pads
    itself by ``env(safe-area-inset-bottom)`` and its height is a MINIMUM,
    so the inset grows the bar under the tabs instead of squeezing them.
    ``base_page.py`` pads main content and offsets the offline banner by
    the same ``4rem + env()`` so nothing ends under the bar.

    Args:
        is_authenticated: Whether user is logged in
        active_page: Current page's section key for active tab highlighting

    Returns:
        FastHTML Nav element
    """
    return Nav(
        *[
            _bottom_nav_tab(item, active_page)
            for item in _visible_icon_items(is_authenticated=is_authenticated)
        ],
        cls="fixed bottom-0 inset-x-0 z-40 sm:hidden bg-background border-t border-border flex items-stretch min-h-16",
        style="padding-bottom: env(safe-area-inset-bottom)",
        **{"aria-label": "Primary navigation"},
    )


def create_navbar_for_request(
    request: Request,
    active_page: str = "",
) -> Nav:
    """
    Create top navbar with automatic user/role detection from the
    middleware-set auth context (AuthContextMiddleware mirrors the session
    per request; the request is kept so routes need no changes).

    Badge counts (notifications, insights) are lazy-loaded via HTMX from
    /api/navbar/notification-badge — not fetched here to keep page render fast.

    Args:
        request: Starlette/FastHTML request object
        active_page: Current page's section key for highlighting

    Returns:
        FastHTML Nav element (slim top bar)
    """
    auth = current_auth_state()
    return create_navbar(
        current_user=auth.user_uid,
        is_authenticated=auth.is_authenticated,
        active_page=active_page,
        is_admin=auth.is_admin,
        is_teacher=auth.is_teacher,
    )


def create_bottom_nav_for_request(
    request: Request,
    active_page: str = "",
) -> Nav:
    """
    Create the phone bottom nav with automatic auth detection from the
    middleware-set auth context (request kept so routes need no changes).

    Args:
        request: Starlette/FastHTML request object
        active_page: Current page's section key for active tab highlighting

    Returns:
        FastHTML Nav element
    """
    auth = current_auth_state()
    return create_bottom_nav(is_authenticated=auth.is_authenticated, active_page=active_page)


__all__ = [
    "create_bottom_nav",
    "create_bottom_nav_for_request",
    "create_navbar",
    "create_navbar_for_request",
    "role_nav_rows",
    "signout_row",
    "_notification_button",
    "_notification_badge_placeholder",
]
