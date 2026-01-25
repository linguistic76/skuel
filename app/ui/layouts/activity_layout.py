"""
Activity Domain Standalone Layout
=================================

Shared standalone page layout for all Activity Domains (Tasks, Goals, Habits,
Events, Choices, Principles). Each domain uses the same three-view tab pattern.

Returns a complete Html document with explicit headers. This ensures
navigation works correctly by avoiding FastHTML's default HTMX wrapping.

Version: 2.0 - Returns Html document (not Div) for navigation compatibility

Usage:
    from ui.layouts.activity_layout import create_activity_page

    content = GoalsViewComponents.render_list_view(...)
    return create_activity_page(content, "goals", request=request)
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fasthtml.common import Body, Div, Head, Html, Link, Meta, Script, Title

from ui.layouts.navbar import create_navbar, create_navbar_for_request

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


# Domain display names for page titles
DOMAIN_TITLES: dict[str, str] = {
    "tasks": "Tasks",
    "goals": "Goals",
    "habits": "Habits",
    "events": "Events",
    "choices": "Choices",
    "principles": "Principles",
}

# CSS files to include per domain (calendar CSS for time-based domains)
DOMAIN_CSS: dict[str, list[str]] = {
    "tasks": ["/static/css/calendar.css"],
    "goals": ["/static/css/calendar.css"],
    "habits": ["/static/css/calendar.css"],
    "events": ["/static/css/calendar.css"],
    "choices": [],  # Analytics view, no calendar
    "principles": [],  # Analytics view, no calendar
}


@dataclass
class ActivityLayout:
    """
    Shared activity domain layout without sidebar.

    Returns a complete Html document with explicit headers. This ensures
    navigation works correctly by avoiding FastHTML's default HTMX version.

    Features:
    - Top navbar with navigation
    - Full-width content area (no sidebar)
    - Centered container with responsive padding
    - Domain-specific CSS includes
    - Explicit HTMX/Alpine.js headers for navigation compatibility
    """

    domain: str
    request: "Request | None" = None
    user_display_name: str = ""
    is_authenticated: bool = True
    is_admin: bool = False

    @property
    def title(self) -> str:
        """Get display title for the domain."""
        return DOMAIN_TITLES.get(self.domain, self.domain.title())

    def render(self, content: Any) -> "FT":
        """
        Render the activity domain page layout.

        Returns a complete Html document with explicit headers.
        This ensures navigation works correctly.

        Args:
            content: The main page content (tabs + view content)

        Returns:
            Complete Html document with navbar and content
        """
        # Prefer request-based navbar (auto-detects user, admin from session)
        if self.request is not None:
            navbar = create_navbar_for_request(self.request, active_page=self.domain)
        else:
            # Fallback for backwards compatibility
            navbar = create_navbar(
                current_user=self.user_display_name,
                is_authenticated=self.is_authenticated,
                active_page=self.domain,
                is_admin=self.is_admin,
            )

        # Get domain-specific CSS files
        css_links = [
            Link(rel="stylesheet", href=css_path) for css_path in DOMAIN_CSS.get(self.domain, [])
        ]

        return Html(
            Head(
                Meta(charset="UTF-8"),
                Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
                Title(f"{self.title} - SKUEL"),
                # DaisyUI CSS
                Link(
                    href="https://cdn.jsdelivr.net/npm/daisyui@4.4.19/dist/full.min.css",
                    rel="stylesheet",
                    type="text/css",
                ),
                # Tailwind CSS CDN (for JIT compilation of all utility classes)
                Script(src="https://cdn.tailwindcss.com"),
                # HTMX - using 1.9.10 to match other working pages
                Script(src="https://unpkg.com/htmx.org@1.9.10"),
                # Alpine.js
                Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
                # SKUEL custom CSS
                Link(rel="stylesheet", href="/static/css/output.css"),
                Link(rel="stylesheet", href="/static/css/skuel.css"),
                # Domain-specific CSS
                *css_links,
                # SKUEL JavaScript (Alpine components)
                Script(src="/static/js/skuel.js"),
            ),
            Body(
                navbar,
                # Main content area with full width
                Div(
                    content,
                    cls="min-h-screen bg-base-100",
                ),
                # Modal container for edit forms and other modals
                Div(id="modal"),
                cls="bg-base-200",
            ),
            **{"data-theme": "light"},
        )


def create_activity_page(
    content: Any,
    domain: str,
    request: "Request | None" = None,
    user_display_name: str = "",
    is_authenticated: bool = True,
    is_admin: bool = False,
) -> "FT":
    """
    Create a standalone activity domain page.

    Returns a complete Html document with explicit headers. This ensures
    navigation works correctly by avoiding FastHTML's default HTMX wrapping.

    Args:
        content: Main page content (tabs + view content)
        domain: Domain name (tasks, goals, habits, events, choices, principles)
        request: Starlette request object (preferred - auto-detects auth from session)
        user_display_name: Current user's display name (fallback if no request)
        is_authenticated: Whether user is logged in (fallback if no request)
        is_admin: Whether user has admin role (fallback if no request)

    Returns:
        Complete Html document with activity domain page layout

    Usage:
        content = Div(
            GoalsViewComponents.render_view_tabs(active_view="list"),
            GoalsViewComponents.render_list_view(goals, filters, stats),
            cls="p-6 lg:p-8 max-w-6xl mx-auto",  # Standard SKUEL container
        )
        return create_activity_page(content, "goals", request=request)
    """
    layout = ActivityLayout(
        domain=domain,
        request=request,
        user_display_name=user_display_name,
        is_authenticated=is_authenticated,
        is_admin=is_admin,
    )
    return layout.render(content)


__all__ = ["ActivityLayout", "create_activity_page", "DOMAIN_TITLES", "DOMAIN_CSS"]
