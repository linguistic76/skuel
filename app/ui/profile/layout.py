"""Profile Hub page layout using unified sidebar (Tailwind + Alpine).

Sidebar sections: Overview, Activities (6 domains), Curriculum.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from fasthtml.common import A as Anchor
from fasthtml.common import (
    Div,
    Li,
    Span,
)

from ui.patterns.sidebar import SidebarItem, SidebarPage

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
    insight_count: int = 0  # Active insights for this domain


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
    "knowledge": "📖",
    "learning-steps": "📝",
    "learning-paths": "🗺️",
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
    "knowledge": "Knowledge",
    "learning-steps": "Learning Steps",
    "learning-paths": "Learning Paths",
}

# Order of domains in sidebar (Activity Domains)
DOMAIN_ORDER = ["tasks", "events", "goals", "habits", "principles", "choices"]

# Curriculum domains (separate section)
CURRICULUM_ORDER = ["knowledge", "learning-steps", "learning-paths"]


def _status_badge(status: str) -> "FT":
    """Status indicator dot."""
    from ui.badge_classes import health_dot_class

    color = health_dot_class(status)
    return Span(cls=f"w-2 h-2 rounded-full {color}", title=f"Status: {status}")


def _count_badge(count: int, active: int | None = None) -> "FT":
    """Count badge showing total (optionally with active subset)."""
    text = f"{active}/{count}" if active is not None and active > 0 else str(count)
    return Span(text, cls="badge badge-sm badge-ghost")


def _insight_badge(insight_count: int) -> Optional["FT"]:
    """Insight count badge (bell icon + count)."""
    if insight_count <= 0:
        return None

    from fasthtml.common import NotStr

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


# Store for ProfileDomainItem data keyed by slug, used by custom renderer
_profile_domain_data: dict[str, ProfileDomainItem] = {}


def _profile_item_renderer(item: SidebarItem, is_active: bool) -> "FT":
    """Custom renderer for profile sidebar items with badges and status dots."""
    active_cls = "bg-base-200 font-semibold" if is_active else ""

    # Check if this item has rich domain data
    domain = _profile_domain_data.get(item.slug)
    if domain:
        badges: list[Any] = [
            _count_badge(domain.count, domain.active_count),
            _status_badge(domain.status),
        ]
        insight = _insight_badge(domain.insight_count)
        if insight:
            badges.append(insight)

        return Li(
            Anchor(
                Span(item.icon, cls="text-lg", aria_hidden="true"),
                Span(item.label, cls="flex-1"),
                Div(*badges, cls="flex items-center gap-2"),
                href=item.href,
                cls=f"flex items-center gap-2 rounded-lg px-3 py-2.5 min-h-[44px]"
                f" transition-colors hover:bg-base-200 {active_cls}",
                **{"hx-boost": "false"},
            )
        )

    # Simple item (Overview, SubmissionReport)
    return Li(
        Anchor(
            Span(item.icon, cls="text-lg", aria_hidden="true") if item.icon else "",
            Span(item.label, cls="flex-1"),
            href=item.href,
            cls=f"flex items-center gap-2 rounded-lg px-3 py-2.5 min-h-[44px]"
            f" transition-colors hover:bg-base-200 {active_cls}",
            **{"hx-boost": "false"},
        )
    )


def _section_header(label: str) -> Li:
    """Render a sidebar section heading (e.g. ACTIVITIES, CURRICULUM)."""
    return Li(
        Span(
            label,
            cls="text-xs font-semibold uppercase tracking-wider opacity-60",
        ),
        cls="px-3 pt-2",
    )


def _build_profile_sidebar_items(
    active_domain: str,
    activity_domains: list[ProfileDomainItem] | None = None,
    curriculum_domains: list[ProfileDomainItem] | None = None,
) -> tuple[list[SidebarItem], list[Any] | None]:
    """Build sidebar items and extra sections (Activities + Curriculum).

    Returns:
        Tuple of (items, extra_sidebar_sections)
    """
    items = [
        SidebarItem("Overview", "/profile", "", icon="📊"),
    ]

    extra_sections: list[Any] = []

    # Activities section
    if activity_domains:
        for d in activity_domains:
            _profile_domain_data[d.slug] = d

        activity_items = [
            SidebarItem(label=d.name, href=d.href, slug=d.slug, icon=d.icon)
            for d in activity_domains
        ]

        journals_item = SidebarItem("Journals", "/journals", "journals", icon="📓")

        extra_sections.extend(
            [
                _section_header("Tracking"),
                *[
                    _profile_item_renderer(item, item.slug == active_domain)
                    for item in activity_items
                ],
                _profile_item_renderer(journals_item, active_domain == "journals"),
            ]
        )

    # Curriculum section (includes Submissions and Reports)
    submissions_item = SidebarItem("Submissions", "/submissions", "submissions", icon="📄")
    reports_item = SidebarItem("Reports", "/submissions/reports", "submission-reports", icon="💬")

    extra_sections.append(_section_header("Curriculum"))

    # Knowledge in Focus: placeholder linking to the existing knowledge domain view
    knowledge_focus_item = SidebarItem(
        "Knowledge in Focus",
        "/profile/knowledge",
        "knowledge-focus",
        icon="🔍",
    )
    extra_sections.append(
        _profile_item_renderer(knowledge_focus_item, active_domain == "knowledge-focus")
    )

    if curriculum_domains:
        for d in curriculum_domains:
            _profile_domain_data[d.slug] = d

        curriculum_items = [
            SidebarItem(label=d.name, href=d.href, slug=d.slug, icon=d.icon)
            for d in curriculum_domains
        ]

        extra_sections.extend(
            [_profile_item_renderer(item, item.slug == active_domain) for item in curriculum_items]
        )

    extra_sections.extend(
        [
            _profile_item_renderer(submissions_item, active_domain == "submissions"),
            _profile_item_renderer(reports_item, active_domain == "submission-reports"),
        ]
    )

    settings_item = SidebarItem("Settings", "/profile/settings", "settings", icon="⚙️")
    extra_sections.extend(
        [
            _section_header("Account"),
            _profile_item_renderer(settings_item, active_domain == "settings"),
        ]
    )

    return items, extra_sections or None


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
    """Create profile page using unified sidebar (Tailwind + Alpine).

    Args:
        content: Main content HTML
        domains: List of ProfileDomainItem for sidebar (Activity Domains)
        active_domain: Currently active domain slug (empty = overview)
        user_display_name: User's display name for header
        title: Page title
        is_authenticated: Whether user is authenticated (for navbar)
        is_admin: Whether user has admin role (shows Admin Dashboard in navbar)
        curriculum_domains: List of ProfileDomainItem for curriculum section
        unread_insights: Number of unread insights for navbar badge
        request: Starlette request (enables BasePage auto-detection of auth/admin)

    Returns:
        Complete HTML page using BasePage with sidebar layout
    """
    display_name = user_display_name or "Your Profile"

    items, extra_sections = _build_profile_sidebar_items(
        active_domain=active_domain,
        activity_domains=domains,
        curriculum_domains=curriculum_domains,
    )

    return await SidebarPage(
        content=content,
        items=items,
        active=active_domain or "",
        title=display_name,
        subtitle="",
        storage_key="profile-sidebar",
        extra_sidebar_sections=extra_sections,
        page_title=title,
        request=request,
        active_page="profile/hub",
        item_renderer=_profile_item_renderer,
        title_href="/profile",
    )


__all__ = [
    "create_profile_page",
    "CURRICULUM_ORDER",
    "DEFAULT_DOMAIN_ICONS",
    "DEFAULT_DOMAIN_NAMES",
    "DOMAIN_ORDER",
    "ProfileDomainItem",
]
