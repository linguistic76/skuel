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

    # Hub page (with sidebar)
    return BasePage(
        content,
        page_type=PageType.HUB,
        title="Profile Hub",
        request=request,
        sidebar=sidebar_content,
    )
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Body, Button, Div, Head, Html, Link, Main, Meta, P, Script, Title

from ui.layouts.navbar import create_navbar, create_navbar_for_request
from ui.layouts.page_types import PAGE_CONFIG, PageType
from ui.theme import ALPINE_VERSION, DAISYUI_VERSION, HTMX_VERSION

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


def build_head(
    title: str,
    extra_css: list[str] | None = None,
) -> "FT":
    """Build complete HTML head for any SKUEL page.

    This is the single source of truth for <head> content. Used by BasePage,
    ActivityLayout, SharedUIComponents, and any code that returns a full Html document.

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
        # DaisyUI CSS
        Link(
            href=f"https://cdn.jsdelivr.net/npm/daisyui@{DAISYUI_VERSION}/dist/full.min.css",
            rel="stylesheet",
            type="text/css",
        ),
        # HTMX for hypermedia
        Script(src=f"https://unpkg.com/htmx.org@{HTMX_VERSION}"),
        # Alpine.js (self-hosted, version-pinned)
        Script(src=f"/static/vendor/alpinejs/alpine.{ALPINE_VERSION}.min.js", defer=True),
        # Vis.js Network (self-hosted, v9.1.9) - Lateral Relationships
        Link(rel="stylesheet", href="/static/vendor/vis-network/vis-network.min.css"),
        Script(src="/static/vendor/vis-network/vis-network.min.js"),
        # SKUEL CSS
        Link(rel="stylesheet", href="/static/css/output.css"),
        Link(rel="stylesheet", href="/static/css/main.css"),
        Link(rel="stylesheet", href="/static/css/hierarchy.css"),
        # Extra CSS for specific pages
        *css_links,
        # SKUEL JavaScript (Alpine components) - LOAD ONLY ONCE
        Script(src="/static/js/focus_trap.js"),
        Script(src="/static/js/skuel.js"),
    )


async def _build_navbar(
    request: "Request | None",
    active_page: str,
    user_display_name: str,
    is_authenticated: bool,
    is_admin: bool,
) -> "FT":
    """Build navbar, preferring request-based for auto-detection."""
    if request is not None:
        # Get notification_service from app state if available
        notification_service = getattr(
            getattr(getattr(request, "app", None), "state", None),
            "services",
            None,
        )
        ns = (
            getattr(notification_service, "notification_service", None)
            if notification_service
            else None
        )
        return await create_navbar_for_request(
            request, active_page=active_page, notification_service=ns
        )
    return create_navbar(
        current_user=user_display_name,
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
    sidebar: Any = None,
    extra_css: list[str] | None = None,
    user_display_name: str = "",
    is_authenticated: bool = True,
    is_admin: bool = False,
) -> "FT":
    """Unified page wrapper for consistent UX across SKUEL.

    Provides:
    - Consistent HTML head (HTMX, Alpine.js, DaisyUI, Tailwind)
    - Navbar with active page highlighting
    - Page layout based on type (HUB with sidebar, STANDARD centered)
    - Modal container for overlays
    - Consistent data-theme

    Args:
        content: Main page content
        title: Page title (shown in browser tab as "Title - SKUEL")
        page_type: Layout type (HUB for sidebar, STANDARD for centered)
        request: Starlette request (preferred - auto-detects auth/admin)
        active_page: Current page key for navbar highlighting
        sidebar: Sidebar content (only used with PageType.HUB)
        extra_css: Additional CSS file paths to include
        user_display_name: Fallback user name if no request
        is_authenticated: Fallback auth state if no request
        is_admin: Fallback admin state if no request

    Returns:
        Complete Html document with consistent structure
    """
    config = PAGE_CONFIG[page_type]

    navbar = await _build_navbar(
        request=request,
        active_page=active_page,
        user_display_name=user_display_name,
        is_authenticated=is_authenticated,
        is_admin=is_admin,
    )

    # Build main content area based on page type
    if page_type == PageType.HUB and sidebar is not None:
        # Hub layout: sidebar + content
        main_area = Div(
            # Sidebar (always visible on lg+)
            Div(
                sidebar,
                cls=f"hidden lg:block {config['sidebar_width']} shrink-0 bg-base-100 border-r border-base-200 min-h-[calc(100vh-64px)] sticky top-16",
            ),
            # Content area
            Div(
                Main(
                    content,
                    id="main-content",
                    cls=config["content_padding"],
                ),
                cls=config["container"],
            ),
            cls="flex",
        )
    elif page_type == PageType.CUSTOM:
        # Custom layout: page manages its own container and padding
        main_area = Main(content, id="main-content")
    else:
        # Standard layout: centered content
        main_area = Main(
            Div(
                content,
                cls=f"{config['container']} {config['content_padding']}",
            ),
            id="main-content",
            cls="min-h-screen",
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
            # Modal container for overlays
            Div(id="modal"),
            # Live region for screen reader announcements (Task 10: WCAG 2.1 Level AA)
            # Automatically announces HTMX operations (create, update, delete, errors)
            # Manual announcements: window.SKUEL.announce(message, priority)
            # Custom announcements: Add data-announce="Custom message" to HTMX target
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
                                "×",
                                **{"@click": "dismiss(toast.id)"},
                                cls="ml-4 text-lg hover:opacity-70 transition-opacity",
                                type="button",
                            ),
                            cls="flex items-center justify-between",
                        ),
                        cls="alert shadow-lg max-w-sm transition-all",
                        **{
                            ":class": """{
                                'alert-success': toast.type === 'success',
                                'alert-error': toast.type === 'error',
                                'alert-info': toast.type === 'info',
                                'alert-warning': toast.type === 'warning'
                            }""",
                        },
                    )
                )
            ),
            cls="bg-base-100",
        ),
        **{
            "data-theme": "light",
            "x-data": "",
            "x-init": "var t = localStorage.getItem('skuel-theme'); if (t) $el.setAttribute('data-theme', t)",
        },
    )


__all__ = ["BasePage", "build_head"]
