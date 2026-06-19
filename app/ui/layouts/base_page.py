"""Unified base page wrapper for SKUEL.

Provides consistent HTML structure, head includes, and layout for all pages.

Usage:
    from ui.layouts.base_page import BasePage
    from ui.layouts.page_types import PageType

    # Standard page (centered content)
    return BasePage(
        content,
        title="Tasks",
        request=request,
    )

    # Custom page (full-width, page manages its own layout — e.g. SidebarPage)
    return BasePage(
        content,
        page_type=PageType.CUSTOM,
        title="Study",
        request=request,
    )
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Body, Button, Div, Head, Html, Link, Main, Meta, P, Script, Title

from ui.layouts.navbar import (
    create_bottom_nav,
    create_bottom_nav_for_request,
    create_navbar,
    create_navbar_for_request,
)
from ui.layouts.page_types import PAGE_CONFIG, PageType
from ui.theme import (
    ALPINE_VERSION,
    BRAND_THEME,
    HTMX_VERSION,
    _local_headers_offline_safe,
    pwa_headers,
)

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

# Cache MonsterUI headers at import time. Use the offline-safe helper so startup
# doesn't hit the CDN when vendor files are already on disk (upstream local_headers()
# re-downloads every call and crashes when DNS is unreachable).
_MU_HEADERS = _local_headers_offline_safe(
    BRAND_THEME, static_dir="static/vendor/monsterui", radii="sm"
)


def build_head(
    title: str,
    extra_css: list[str] | None = None,
) -> "FT":
    """Build complete HTML head for any SKUEL page.

    This is the single source of truth for <head> content. Used by BasePage
    and any code that returns a full Html document.

    Args:
        title: Page title (appended with " - SKUEL")
        extra_css: Additional CSS file paths to include

    Returns:
        Head element with all required includes

    Note:
        BasePage returns complete Html() documents, so it provides its own <head>.
        Routes that return partial HTML use fast_app headers instead.
    """
    css_links = []
    if extra_css:
        css_links = [Link(rel="stylesheet", href=path) for path in extra_css]

    return Head(
        Meta(charset="UTF-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1.0, viewport-fit=cover"),
        Title(f"{title} - SKUEL"),
        # MonsterUI headers (FrankenUI CSS/JS + Tailwind + Lucide icons) — cached at import
        *_MU_HEADERS,
        # HTMX for hypermedia (self-hosted — see ui/theme.py:monster_headers)
        Script(src=f"/static/vendor/htmx.org/htmx.{HTMX_VERSION}.min.js"),
        # Alpine.js (self-hosted, version-pinned)
        Script(src=f"/static/vendor/alpinejs/alpine.{ALPINE_VERSION}.min.js", defer=True),
        # Vis.js Network (self-hosted, v9.1.9) - Lateral Relationships
        Link(rel="stylesheet", href="/static/vendor/vis-network/vis-network.min.css"),
        Script(src="/static/vendor/vis-network/vis-network.min.js"),
        # SKUEL CSS
        Link(rel="stylesheet", href="/static/css/main.css"),
        Link(rel="stylesheet", href="/static/css/hierarchy.css"),
        # Extra CSS for specific pages
        *css_links,
        # SKUEL JavaScript (Alpine components) - LOAD ONLY ONCE
        Script(src="/static/js/focus_trap.js"),
        Script(src="/static/js/skuel.js"),
        # PWA: manifest, icons, meta tags
        *pwa_headers(),
    )


async def _build_navbar(
    request: "Request | None",
    active_page: str,
    user_display_name: str,
    is_authenticated: bool,
    is_admin: bool,
) -> "FT":
    """Build slim top navbar, preferring request-based for auto-detection."""
    if request is not None:
        return await create_navbar_for_request(request, active_page=active_page)
    return create_navbar(
        current_user=user_display_name,
        is_authenticated=is_authenticated,
        active_page=active_page,
        is_admin=is_admin,
    )


async def _build_bottom_nav(
    request: "Request | None",
    active_page: str,
    is_authenticated: bool,
    is_admin: bool,
) -> "FT":
    """Build mobile bottom nav, preferring request-based for auto-detection."""
    if request is not None:
        return await create_bottom_nav_for_request(request, active_page=active_page)
    return create_bottom_nav(
        is_authenticated=is_authenticated,
        active_page=active_page,
        is_admin=is_admin,
    )


async def BasePage(
    content: Any,
    title: str = "SKUEL",
    page_type: PageType = PageType.STANDARD,
    request: "Request | None" = None,
    active_page: str = "",
    extra_css: list[str] | None = None,
    user_display_name: str = "",
    is_authenticated: bool = True,
    is_admin: bool = False,
) -> "FT":
    """Unified page wrapper for consistent UX across SKUEL.

    Provides:
    - Consistent HTML head (MonsterUI, HTMX, Alpine.js)
    - Navbar with active page highlighting
    - Page layout based on type (STANDARD centered, CUSTOM full-width)
    - Modal container for overlays
    - Consistent theming

    Args:
        content: Main page content
        title: Page title (shown in browser tab as "Title - SKUEL")
        page_type: Layout type (STANDARD centered, CUSTOM full-width)
        request: Starlette request (preferred - auto-detects auth/admin)
        active_page: Current page key for navbar highlighting
        extra_css: Additional CSS file paths to include
        user_display_name: Fallback user name if no request
        is_authenticated: Fallback auth state if no request
        is_admin: Fallback admin state if no request

    Returns:
        Complete Html document with consistent structure
    """
    config = PAGE_CONFIG[page_type]

    # Determine effective admin/auth state for layout decisions
    effective_is_admin = is_admin
    effective_is_authenticated = is_authenticated
    if request is not None:
        from adapters.inbound.auth import get_is_admin
        from adapters.inbound.auth import is_authenticated as check_auth

        effective_is_admin = get_is_admin(request)
        effective_is_authenticated = check_auth(request)

    navbar = await _build_navbar(
        request=request,
        active_page=active_page,
        user_display_name=user_display_name,
        is_authenticated=effective_is_authenticated,
        is_admin=effective_is_admin,
    )

    bottom_nav = await _build_bottom_nav(
        request=request,
        active_page=active_page,
        is_authenticated=effective_is_authenticated,
        is_admin=effective_is_admin,
    )

    # Mobile bottom nav adds 4rem (h-16) to the viewport. Pad main content so it
    # isn't hidden under the nav. Only needed for authenticated non-admin users on
    # mobile; sm:pb-0 removes it on desktop where there is no bottom nav.
    bottom_pad = "" if effective_is_admin or not effective_is_authenticated else "pb-16 sm:pb-0"

    # Build main content area based on page type
    if page_type == PageType.CUSTOM:
        # Custom layout: page manages its own container and padding
        main_area = Main(content, id="main-content", cls=bottom_pad)
    else:
        # Standard layout: centered content
        main_area = Main(
            Div(
                content,
                cls=f"{config['container']} {config['content_padding']}",
            ),
            id="main-content",
            cls=f"min-h-screen {bottom_pad}",
        )

    return Html(
        build_head(title, extra_css),
        Body(
            # Skip link for keyboard navigation (WCAG 2.1 Level AA)
            A(
                "Skip to main content",
                href="#main-content",
                cls="skip-link",
            ),
            navbar,
            main_area,
            bottom_nav,
            # Modal container for overlays
            Div(id="modal"),
            # Live region for screen reader announcements (Task 10: WCAG 2.1 Level AA)
            Div(
                id="live-region",
                role="status",
                cls="sr-only",
                **{"aria-live": "polite", "aria-atomic": "true"},
            ),
            # Toast notification container
            Div(
                **{"x-data": "toastManager", "x-cloak": True, "x-show": "toasts.length > 0"},
                cls="fixed top-4 right-4 z-50 space-y-2",
            )(
                # Template for rendering toasts
                Div(
                    **{"x-for": "toast in toasts", ":key": "toast.id"},
                )(
                    Div(
                        Div(
                            P(**{"x-text": "toast.message"}, cls="text-sm font-medium"),
                            Button(
                                "x",
                                **{"@click": "dismiss(toast.id)"},
                                cls="ml-4 text-lg hover:opacity-70 transition-opacity",
                                type="button",
                            ),
                            cls="flex items-center justify-between",
                        ),
                        cls="rounded-lg border px-4 py-3 shadow-lg max-w-sm transition-all",
                        **{
                            ":class": """{
                                'bg-green-50 border-green-200 text-green-800': toast.type === 'success',
                                'bg-red-50 border-red-200 text-red-800': toast.type === 'error',
                                'bg-blue-50 border-blue-200 text-blue-800': toast.type === 'info',
                                'bg-yellow-50 border-yellow-200 text-yellow-800': toast.type === 'warning'
                            }""",
                        },
                    )
                )
            ),
            # PWA: offline status banner
            Div(
                P(
                    "You are offline. Some features may be unavailable.",
                    cls="text-sm font-medium text-center",
                ),
                cls="fixed bottom-16 sm:bottom-0 inset-x-0 bg-yellow-500 text-yellow-950 px-4 py-2 z-50",
                **{"x-data": "offlineIndicator", "x-show": "isOffline", "x-cloak": ""},
            ),
            # PWA: service worker registration
            Script("""
                if ('serviceWorker' in navigator) {
                    navigator.serviceWorker.register('/service-worker.js');
                }
            """),
            cls="bg-background text-foreground",
        ),
        **{
            "x-data": "",
            "x-init": """
                var t = localStorage.getItem('skuel-theme');
                if (t === 'dark') document.documentElement.classList.add('dark');
            """,
        },
    )


def AuthPage(
    content: Any,
    title: str = "SKUEL",
) -> "FT":
    """Lightweight page wrapper for unauthenticated pages (login, register).

    Loads the full MonsterUI CSS stack via build_head() but renders no navbar,
    no modals, no toasts, no PWA. Use for auth flows where users are not
    logged in.

    Args:
        content: Page content (centered card/form)
        title: Page title (shown in browser tab as "Title - SKUEL")

    Returns:
        Complete Html document with minimal chrome
    """
    return Html(
        build_head(title),
        Body(
            content,
            cls="bg-background text-foreground",
        ),
    )


__all__ = ["AuthPage", "BasePage", "build_head"]
