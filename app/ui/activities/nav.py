"""Activity Domain sidebar navigation.

Renders a collapsible sidebar with all 6 Activity Domains on every domain page,
and a slimmer variant — the temporal lenses plus the Journal and Reports doors,
no domain rows, no badge request — on the calendar and Today pages (ruling 6 of
the calendar-priority-lens arc: the Activity Domains are understood there
through Activity Reports, not sidebar counts).

Usage:
    from ui.activities.nav import render_activity_sidebar_page

    return render_activity_sidebar_page(
        content=my_content,
        active="tasks",
        request=request,
    )
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from ui.patterns.error_banner import render_error_banner
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
    SidebarItem("Goals", "/goals", "goals", icon="target"),
    SidebarItem("Habits", "/habits", "habits", icon="repeat"),
    SidebarItem("Principles", "/principles", "principles", icon="compass"),
    SidebarItem("Choices", "/choices", "choices", icon="git-branch"),
    SidebarItem("Journal", "/journals", "journals", icon="book-open"),
]

#: The calendar/Today variant: the three temporal lenses, the Journal, and the
#: Reports door (the newest owned report, or the request form when none). No
#: domain rows — and no ``/api/sidebar/badges`` request, which builds the RICH
#: UserContext for counts these rows never show.
CALENDAR_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Today", "/today", "today", icon="sun"),
    SidebarItem("Weekly", "/cal/week", "weekly", icon="calendar-range"),
    SidebarItem("Monthly", "/cal/month", "monthly", icon="calendar-days"),
    SidebarItem("Journal", "/journals", "journals", icon="book-open"),
    SidebarItem("Reports", "/activity-reports/latest", "reports", icon="file-text"),
]


def render_activity_sidebar_page(
    content: Any,
    active: str,
    request: "Request | None" = None,
    extra_css: list[str] | None = None,
    title: str = "Tasks+",
    active_page: str = "activity",
    content_max_width: str = "max-w-6xl",
    items: list[SidebarItem] | None = None,
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
        items: The sidebar rows; the full domain list by default. The calendar
            and Today pages pass ``CALENDAR_SIDEBAR_ITEMS``, which also switches
            the badge request off — the rows it would decorate are not there.
    """
    rows = ACTIVITY_SIDEBAR_ITEMS if items is None else items
    return SidebarPage(
        content=content,
        items=rows,
        active=active,
        title=title,
        storage_key=ACTIVITY_STORAGE_KEY,
        request=request,
        active_page=active_page,
        extra_css=extra_css,
        content_max_width=content_max_width,
        badges=rows is ACTIVITY_SIDEBAR_ITEMS,
    )


def render_activity_sidebar_error(
    message: str,
    active: str,
    request: "Request | None" = None,
) -> "FT":
    """A whole Activity sidebar page whose only content is an error banner.

    The terminal state of every activity guard that has nothing left to render —
    a missing UID, or an entity the user does not own (deliberately reported as
    "not found", per OWNERSHIP_VERIFICATION). Distinct from
    ``require_owned_entity``, which answers a bare 404 body: these routes are
    full page loads, so the learner gets the page chrome back.

    Args:
        message: The user-facing error text.
        active: The active sidebar item slug (e.g. "tasks").
        request: The request object for auth detection.
    """
    return render_activity_sidebar_page(
        Div(render_error_banner(message)),
        active=active,
        request=request,
    )
