"""Profile Hub page layout with DaisyUI drawer sidebar.

Uses DaisyUI drawer for responsive sidebar navigation across the 6 Activity Domains.

Version: 2.0 - Returns content only (no full HTML wrapper)
The main app's bootstrap.py provides Theme headers, HTMX, and Alpine.js.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fasthtml.common import A as Anchor
from fasthtml.common import (
    Div,
    Input,
    Label,
    Li,
    Main,
    P,
    Span,
    Ul,
)

from ui.layouts.navbar import create_navbar

if TYPE_CHECKING:
    from fasthtml.common import FT


@dataclass
class ProfileDomainItem:
    """Sidebar item for a domain."""

    name: str  # "Tasks", "Habits", etc.
    slug: str  # "tasks", "habits", etc.
    icon: str  # Emoji icon
    count: int  # Total items
    active_count: int  # Active/pending items
    status: str  # "healthy", "warning", "critical"
    href: str  # "/profile/tasks"


# Default domain configuration
DEFAULT_DOMAIN_ICONS = {
    # Activity Domains
    "tasks": "✅",
    "events": "📅",
    "goals": "🎯",
    "habits": "🔄",
    "principles": "⚖️",
    "choices": "🔀",
    # Curriculum Domains
    "learning": "📚",
}

DEFAULT_DOMAIN_NAMES = {
    # Activity Domains
    "tasks": "Tasks",
    "events": "Events",
    "goals": "Goals",
    "habits": "Habits",
    "principles": "Principles",
    "choices": "Choices",
    # Curriculum Domains
    "learning": "Learning",
}

# Order of domains in sidebar (Activity Domains)
DOMAIN_ORDER = ["tasks", "events", "goals", "habits", "principles", "choices"]

# Curriculum domains (separate section)
CURRICULUM_ORDER = ["learning"]


def _status_badge(status: str) -> "FT":
    """Status indicator dot."""
    color_map = {
        "healthy": "bg-success",
        "warning": "bg-warning",
        "critical": "bg-error",
    }
    color = color_map.get(status, "bg-base-content/50")
    return Span(cls=f"w-2 h-2 rounded-full {color}", title=f"Status: {status}")


def _count_badge(count: int, active: int | None = None) -> "FT":
    """Count badge showing total (optionally with active subset)."""
    text = f"{active}/{count}" if active is not None and active > 0 else str(count)
    return Span(text, cls="badge badge-sm badge-ghost")


def _domain_menu_item(domain: ProfileDomainItem, is_active: bool) -> "FT":
    """Single domain navigation item."""
    active_cls = "menu-active" if is_active else ""

    return Li(
        Anchor(
            Span(domain.icon, cls="text-lg"),
            Span(domain.name, cls="flex-1"),
            Div(
                _count_badge(domain.count, domain.active_count),
                _status_badge(domain.status),
                cls="flex items-center gap-2",
            ),
            href=domain.href,
            cls=f"flex items-center gap-2 {active_cls}",
            **{"hx-boost": "false"},  # Ensure standard navigation
        )
    )


@dataclass
class ProfileLayout:
    """Profile page layout with DaisyUI drawer sidebar.

    Features:
    - Left sidebar: 6 Activity Domain + Curriculum navigation with counts and status
    - Center: Main content (overview or domain-specific view)
    - Responsive: Always open on lg+, drawer toggle on mobile

    Note: Returns content only (no full HTML wrapper).
    The main app's bootstrap.py provides Theme headers, HTMX, and Alpine.js.
    """

    title: str
    domains: list[ProfileDomainItem]  # Activity domains
    active_domain: str = ""  # Empty = overview
    user_display_name: str = ""
    is_authenticated: bool = True  # Profile hub requires auth
    is_admin: bool = False
    curriculum_domains: list[ProfileDomainItem] | None = None  # Curriculum domains

    def render(self, content: Any) -> "FT":
        """Render the profile layout with sidebar.

        Args:
            content: Main content (HTML component)

        Returns:
            FastHTML content (Div with navbar + sidebar layout)
            NOT a full HTML document - FastHTML wraps this automatically
        """
        return Div(
            # Top Navbar
            create_navbar(
                current_user=self.user_display_name,
                is_authenticated=self.is_authenticated,
                active_page="profile/hub",
                is_admin=self.is_admin,
            ),
            # Mobile drawer (checkbox + overlay + sidebar)
            Input(
                type="checkbox",
                id="profile-drawer",
                cls="peer hidden",
            ),
            # Mobile overlay (appears when drawer is open)
            Label(
                htmlFor="profile-drawer",
                cls="fixed inset-0 z-30 bg-black/50 hidden peer-checked:block lg:hidden",
                **{"aria-label": "close sidebar"},
            ),
            # Mobile sidebar (slides in from left)
            Div(
                self._build_sidebar_menu(),
                cls="fixed left-0 top-0 z-40 h-full w-64 -translate-x-full transform bg-base-200 transition-transform duration-300 peer-checked:translate-x-0 lg:hidden",
            ),
            # Main layout (desktop sidebar + content)
            Div(
                # Desktop sidebar (always visible on lg+)
                Div(
                    self._build_sidebar_menu(),
                    cls="hidden lg:block w-64 shrink-0 bg-base-200 min-h-[calc(100vh-64px)] sticky top-16",
                ),
                # Main content area
                Div(
                    # Mobile menu button
                    Label(
                        Span("☰", cls="text-xl"),
                        Span("Menu", cls="ml-2"),
                        htmlFor="profile-drawer",
                        cls="btn btn-ghost lg:hidden mb-4",
                    ),
                    # Page content
                    Main(
                        Div(content, cls="max-w-6xl mx-auto"),
                        cls="p-6 lg:p-8",
                    ),
                    cls="flex-1 min-w-0",
                ),
                cls="flex",
            ),
            cls="min-h-screen bg-base-100",
            **{"data-theme": "light"},
        )

    def _build_sidebar_menu(self) -> "FT":
        """Build the sidebar navigation menu."""
        display_name = self.user_display_name or "Your Profile"
        is_overview_active = self.active_domain == ""

        # Build activity domain items
        activity_items = [_domain_menu_item(d, d.slug == self.active_domain) for d in self.domains]

        # Build curriculum section if provided
        curriculum_section = []
        if self.curriculum_domains:
            curriculum_section = [
                # Curriculum section header
                Li(
                    Span(
                        "Curriculum",
                        cls="text-xs font-semibold uppercase tracking-wider opacity-60",
                    ),
                    cls="menu-title",
                ),
                # Curriculum navigation items
                *[
                    _domain_menu_item(d, d.slug == self.active_domain)
                    for d in self.curriculum_domains
                ],
            ]

        return Ul(
            # Profile header
            Li(
                Anchor(
                    display_name,
                    href="/profile",
                    cls="text-xl font-bold text-primary hover:text-primary-focus",
                    **{"hx-boost": "false"},
                ),
                P("Profile", cls="text-xs opacity-60 mt-1"),
                cls="px-4 py-4",
            ),
            # Divider
            Li(cls="divider my-0"),
            # Overview link
            Li(
                Anchor(
                    Span("📊", cls="text-lg"),
                    "Overview",
                    href="/profile",
                    cls=f"flex items-center gap-2 {'menu-active' if is_overview_active else ''}",
                    **{"hx-boost": "false"},
                )
            ),
            # Activity Domains section header
            Li(
                Span(
                    "Activity Domains",
                    cls="text-xs font-semibold uppercase tracking-wider opacity-60",
                ),
                cls="menu-title",
            ),
            # Activity domain navigation items
            *activity_items,
            # Curriculum section (if provided)
            *curriculum_section,
            cls="menu bg-base-200 min-h-full w-72 p-4",
        )


def create_profile_page(
    content: Any,
    domains: list[ProfileDomainItem],
    active_domain: str = "",
    user_display_name: str = "",
    title: str = "Profile",
    is_authenticated: bool = True,
    is_admin: bool = False,
    curriculum_domains: list[ProfileDomainItem] | None = None,
) -> "FT":
    """Convenience function to create a profile page.

    Args:
        content: Main content HTML
        domains: List of ProfileDomainItem for sidebar (Activity Domains)
        active_domain: Currently active domain slug (empty = overview)
        user_display_name: User's display name for header
        title: Page title
        is_authenticated: Whether user is authenticated (for navbar)
        is_admin: Whether user has admin role (shows Admin Dashboard in navbar)
        curriculum_domains: List of ProfileDomainItem for curriculum section

    Returns:
        FastHTML content (navbar + drawer + content)
        NOT a full HTML document - FastHTML wraps this automatically
    """
    layout = ProfileLayout(
        title=title,
        domains=domains,
        active_domain=active_domain,
        user_display_name=user_display_name,
        is_authenticated=is_authenticated,
        is_admin=is_admin,
        curriculum_domains=curriculum_domains,
    )
    return layout.render(content)


__all__ = [
    "CURRICULUM_ORDER",
    "DEFAULT_DOMAIN_ICONS",
    "DEFAULT_DOMAIN_NAMES",
    "DOMAIN_ORDER",
    "ProfileDomainItem",
    "ProfileLayout",
    "create_profile_page",
]
