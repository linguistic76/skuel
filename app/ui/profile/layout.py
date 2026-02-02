"""Profile Hub page layout using BasePage with /nous-style sidebar.

Modern implementation using BasePage architecture for consistent UX.
Sidebar collapses smoothly on desktop, slides in as drawer on mobile.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from fasthtml.common import A as Anchor
from fasthtml.common import (
    Button,
    Div,
    Li,
    Main,
    P,
    Span,
    Ul,
)

from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


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
    insight_count: int = 0  # NEW: Active insights for this domain (Phase 1 integration)


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
    color = color_map.get(status, "bg-base-content/60")
    return Span(cls=f"w-2 h-2 rounded-full {color}", title=f"Status: {status}")


def _count_badge(count: int, active: int | None = None) -> "FT":
    """Count badge showing total (optionally with active subset)."""
    text = f"{active}/{count}" if active is not None and active > 0 else str(count)
    return Span(text, cls="badge badge-sm badge-ghost")


def _insight_badge(insight_count: int) -> Optional["FT"]:
    """Insight count badge (bell icon + count) for Profile Hub integration."""
    if insight_count <= 0:
        return None

    from fasthtml.common import NotStr

    # Bell icon SVG (decorative - insight count conveys meaning)
    bell_svg = NotStr(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3" aria-hidden="true">'
        '<path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z"/>'
        "</svg>"
    )

    return Span(
        bell_svg,
        Span(str(insight_count), cls="text-xs font-bold"),
        cls="badge badge-xs badge-warning gap-1",
        title=f"{insight_count} active insight{'s' if insight_count != 1 else ''}",
    )


def _domain_menu_item(domain: ProfileDomainItem, is_active: bool) -> "FT":
    """Single domain navigation item.

    Phase 3, Task 14: Added closeOnMobile() to auto-close drawer on mobile after navigation.
    """
    active_cls = "menu-active" if is_active else ""

    # Build badges - include insight badge if available
    badges = [
        _count_badge(domain.count, domain.active_count),
        _status_badge(domain.status),
    ]

    # Add insight badge if there are insights (Phase 1 integration)
    insight_badge = _insight_badge(domain.insight_count)
    if insight_badge:
        badges.append(insight_badge)

    return Li(
        Anchor(
            Span(domain.icon, cls="text-lg", aria_hidden="true"),  # Decorative emoji
            Span(domain.name, cls="flex-1"),
            Div(
                *badges,
                cls="flex items-center gap-2",
            ),
            href=domain.href,
            cls=f"flex items-center gap-2 {active_cls}",
            x_on_click="closeOnMobile()",  # Close drawer on mobile after click
            **{"hx-boost": "false"},  # Ensure standard navigation
        )
    )


def build_profile_sidebar(
    domains: list[ProfileDomainItem],
    active_domain: str = "",
    user_display_name: str = "",
    curriculum_domains: list[ProfileDomainItem] | None = None,
) -> "FT":
    """Build the profile sidebar navigation using /nous-style pattern.

    Enhanced with WCAG 2.1 Level AA accessibility:
    - role="dialog" for mobile drawer context
    - aria-modal for focus management
    - aria-labelledby linking to sidebar heading
    - aria-expanded on toggle button

    Args:
        domains: Activity domain items for sidebar navigation
        active_domain: Currently active domain slug (empty = overview)
        user_display_name: User's display name for header
        curriculum_domains: Optional curriculum domain items

    Returns:
        Sidebar component with toggle button and navigation
    """
    from fasthtml.common import NotStr

    display_name = user_display_name or "Your Profile"
    is_overview_active = active_domain == ""

    # Build activity domain items
    activity_items = [_domain_menu_item(d, d.slug == active_domain) for d in domains]

    # Build curriculum section if provided
    curriculum_section = []
    if curriculum_domains:
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
            *[_domain_menu_item(d, d.slug == active_domain) for d in curriculum_domains],
        ]

    # Chevron icon for toggle button (decorative - button has aria-label)
    chevron_svg = NotStr(
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path d="M15 18l-6-6 6-6"></path>'
        "</svg>"
    )

    # Build sidebar menu content
    sidebar_menu = Ul(
        # Profile header (P0: Add ID for aria-labelledby)
        Li(
            Anchor(
                display_name,
                href="/profile",
                cls="text-xl font-bold text-primary hover:text-primary-focus",
                id="profile-sidebar-heading",
                **{"hx-boost": "false"},
            ),
            P("Profile", cls="text-xs opacity-60 mt-1"),
            cls="px-4 py-4 sidebar-header-text",
        ),
        # Divider
        Li(cls="divider my-0"),
        # Overview link
        Li(
            Anchor(
                Span("📊", cls="text-lg", aria_hidden="true"),  # Decorative emoji
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
        cls="menu bg-base-200 min-h-full w-full p-4 sidebar-nav",
        id="profile-sidebar-nav",
    )

    return Div(
        Div(
            # P0: Enhanced toggle button with ARIA
            Button(
                chevron_svg,
                onclick="toggleProfileSidebar()",
                cls="sidebar-toggle",
                title="Toggle Sidebar",
                type="button",
                aria_label="Toggle profile sidebar",
                aria_expanded="false",
                aria_controls="profile-sidebar-nav",
            ),
            # Sidebar navigation
            sidebar_menu,
            cls="sidebar-inner",
        ),
        cls="profile-sidebar",
        id="profile-sidebar",
        role="dialog",
        aria_modal="false",
        aria_labelledby="profile-sidebar-heading",
    )


async def create_profile_page(
    content: Any,
    domains: list[ProfileDomainItem],
    active_domain: str = "",
    user_display_name: str = "",
    title: str = "Profile",
    is_authenticated: bool = True,
    is_admin: bool = False,
    curriculum_domains: list[ProfileDomainItem] | None = None,
    unread_insights: int = 0,
    request: "Request | None" = None,
) -> "FT":
    """Create profile page using BasePage with /nous-style sidebar.

    Enhanced with mobile accessibility:
    - Screen reader live region for state announcements
    - ARIA attributes on mobile menu button
    - Focus management on drawer open/close

    Args:
        content: Main content HTML
        domains: List of ProfileDomainItem for sidebar (Activity Domains)
        active_domain: Currently active domain slug (empty = overview)
        user_display_name: User's display name for header
        title: Page title
        is_authenticated: Whether user is authenticated (for navbar)
        is_admin: Whether user has admin role (shows Admin Dashboard in navbar)
        curriculum_domains: List of ProfileDomainItem for curriculum section
        unread_insights: Number of unread insights for navbar badge (Phase 1 integration)
        request: Starlette request (enables BasePage auto-detection of auth/admin)

    Returns:
        Complete HTML page using BasePage with custom sidebar layout
    """
    # Build sidebar navigation
    sidebar = build_profile_sidebar(
        domains=domains,
        active_domain=active_domain,
        user_display_name=user_display_name,
        curriculum_domains=curriculum_domains,
    )

    # Build mobile overlay (like /nous)
    overlay = Div(
        cls="profile-overlay",
        id="profile-overlay",
        onclick="toggleProfileSidebar()",
    )

    # P0: Enhanced mobile menu button with ARIA
    mobile_menu = Div(
        Span("☰", cls="text-xl", aria_hidden="true"),
        Span("Menu", cls="ml-2"),
        cls="btn btn-ghost mobile-menu-button mb-4",
        onclick="toggleProfileSidebar()",
        aria_label="Open profile navigation",
        aria_expanded="false",
        aria_controls="profile-sidebar",
        role="button",
        tabindex="0",
    )

    # Wrap content with sidebar + overlay (like /nous DocsLayout)
    wrapped_content = Div(
        overlay,
        sidebar,
        # P1: Screen reader live region for announcements
        Div(
            id="sidebar-sr-announcements",
            role="status",
            aria_live="polite",
            aria_atomic="true",
            cls="sr-only",
        ),
        Div(
            mobile_menu,
            Main(
                Div(content, cls="max-w-6xl mx-auto"),
                cls="p-6 lg:p-8",
            ),
            cls="profile-content",
            id="profile-content",
        ),
        cls="profile-container",
    )

    # Use BasePage with STANDARD type (we handle layout ourselves)
    return await BasePage(
        content=wrapped_content,
        title=title,
        page_type=PageType.STANDARD,
        request=request,
        active_page="profile/hub",
        extra_css=["/static/css/profile_sidebar.css"],
        user_display_name=user_display_name,
        is_authenticated=is_authenticated,
        is_admin=is_admin,
    )


__all__ = [
    "build_profile_sidebar",
    "create_profile_page",
    "CURRICULUM_ORDER",
    "DEFAULT_DOMAIN_ICONS",
    "DEFAULT_DOMAIN_NAMES",
    "DOMAIN_ORDER",
    "ProfileDomainItem",
]
