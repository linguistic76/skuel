"""Activity Domain sidebar navigation.

Renders a collapsible sidebar with all 6 Activity Domains.
Used on every individual domain page.

Usage:
    from ui.activities.nav import render_activity_sidebar_page

    return render_activity_sidebar_page(
        content=my_content,
        active="tasks",
        request=request,
    )
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

ACTIVITY_STORAGE_KEY = "activity-sidebar"

ACTIVITY_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Today", "/today", "today", icon="sun"),
    SidebarItem("Weekly", "/cal/week", "weekly", icon="calendar-range"),
    SidebarItem("Monthly", "/cal/month", "monthly", icon="calendar-days"),
    SidebarItem("Tasks", "/tasks", "tasks", icon="check-square"),
    SidebarItem("Events", "/cal", "events", icon="calendar"),
    SidebarItem("Goals", "/goals", "goals", icon="target"),
    SidebarItem("Habits", "/habits", "habits", icon="repeat"),
    SidebarItem("Principles", "/principles", "principles", icon="compass"),
    SidebarItem("Choices", "/choices", "choices", icon="git-branch"),
    SidebarItem("Journal", "/journals", "journals", icon="book-open"),
]


def render_activity_sidebar_page(
    content: Any,
    active: str,
    request: "Request | None" = None,
    extra_css: list[str] | None = None,
    title: str = "Tasks+",
    active_page: str = "activity",
    content_max_width: str = "max-w-6xl",
) -> "FT":
    """Wrap content in Activity Domain sidebar page.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "tasks", "activities").
        request: The request object for auth detection.
        extra_css: Additional CSS file paths to include in the page head.
        title: Browser/page title; defaults to "Tasks+" for activity domain pages.
        active_page: Top-nav active key passed to BasePage; defaults to "activity".
        content_max_width: Tailwind max-width class for the content column;
            "max-w-none" lets fluid pages (calendar) fill the available width.
    """
    return SidebarPage(
        content=content,
        items=ACTIVITY_SIDEBAR_ITEMS,
        active=active,
        title=title,
        storage_key=ACTIVITY_STORAGE_KEY,
        request=request,
        active_page=active_page,
        extra_css=extra_css,
        content_max_width=content_max_width,
    )
