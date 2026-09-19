"""Activity Domain sidebar navigation.

Renders a collapsible sidebar — the three temporal lenses (Today / Weekly /
Monthly), the six Activity Domain rows with their count and health badges, the
Journal (today's daily periodic note) and the GradeBook (feedback received) —
as ONE list on every domain page, the calendar views, Today, the periodic
notes and the GradeBook surfaces (the page, its detail pages and the
activity-report request form — the GradeBook has no sidebar of its own).

This is the one sidebar that opts into the badge loader: its domain rows are
the badges' targets (``ACTIVITY_SIDEBAR_ITEMS ∩ DOMAIN_STATS_CONFIG``), and the
loader fires only once the desktop sidebar is on screen.

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

# The sidebar's heading — one name on every page that carries it, whatever the
# page's own browser title is.
ACTIVITY_SIDEBAR_TITLE = "Tasks+"

ACTIVITY_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Today", "/today", "today", icon="sun"),
    SidebarItem("Weekly", "/cal/week", "weekly", icon="calendar-range"),
    SidebarItem("Monthly", "/cal/month", "monthly", icon="calendar-days"),
    SidebarItem("Tasks", "/tasks", "tasks", icon="check-square"),
    SidebarItem("Goals", "/goals", "goals", icon="target"),
    SidebarItem("Habits", "/habits", "habits", icon="repeat"),
    SidebarItem("Events", "/events", "events", icon="calendar"),
    SidebarItem("Principles", "/principles", "principles", icon="compass"),
    SidebarItem("Choices", "/choices", "choices", icon="git-branch"),
    # The periodic notes' door: today's daily note (find-or-create, then a
    # redirect to the note page). The dateless route resolves "today" at click
    # time, so this list can stay a constant.
    SidebarItem("Journal", "/journals/daily", "journals", icon="book-open"),
    # Feedback received on submitted work. The GradeBook page and its detail
    # pages render under THIS sidebar with the row lit — there is no other.
    SidebarItem("GradeBook", "/gradebook", "gradebook", icon="clipboard-check"),
]


def render_activity_sidebar_page(
    content: Any,
    active: str,
    request: Request | None = None,
    extra_css: list[str] | None = None,
    title: str = ACTIVITY_SIDEBAR_TITLE,
    content_max_width: str = "max-w-6xl",
) -> FT:
    """Wrap content in Activity Domain sidebar page.

    Every page under this sidebar is a Tasks+ page, so every one lights the
    Tasks+ door in the global chrome (``active_page="activity"``, the key
    ``ICON_NAV_ITEMS`` declares) — the sidebar row is the only per-page light.

    Args:
        content: The page content to render in the main area.
        active: The active sidebar item slug (e.g. "tasks", "activities").
        request: The request object for auth detection.
        extra_css: Additional CSS file paths to include in the page head.
        title: Browser/page title only — the sidebar heading is always
            ``ACTIVITY_SIDEBAR_TITLE``; defaults to that same name.
        content_max_width: Tailwind max-width class for the content column;
            "max-w-none" lets fluid pages (calendar) fill the available width.
    """
    return SidebarPage(
        content=content,
        items=ACTIVITY_SIDEBAR_ITEMS,
        active=active,
        title=ACTIVITY_SIDEBAR_TITLE,
        page_title=title,
        storage_key=ACTIVITY_STORAGE_KEY,
        request=request,
        active_page="activity",
        extra_css=extra_css,
        content_max_width=content_max_width,
        badges=True,
    )


def render_activity_sidebar_error(
    message: str,
    active: str,
    request: Request | None = None,
    title: str = ACTIVITY_SIDEBAR_TITLE,
) -> FT:
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
        title: Browser/page title only — see ``render_activity_sidebar_page``.
    """
    return render_activity_sidebar_page(
        Div(render_error_banner(message)),
        active=active,
        request=request,
        title=title,
    )
