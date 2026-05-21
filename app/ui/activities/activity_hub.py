"""Activity Domains hub view — all 6 domains as HTMX-loaded preview blocks.

Each block has a colored domain header (icon + title + "View all" link)
and 3 priority-sorted cards loaded via HTMX from /api/profile/{slug}/preview.
"""

from fasthtml.common import Div

from ui.patterns.hub import HubBlockData, HubDomainBlockList
from ui.patterns.page_header import PageHeader

ACTIVITY_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "Tasks", "tasks", "check-square", "#3B82F6", "/tasks", "/api/profile/tasks/preview"
    ),
    HubBlockData("Goals", "goals", "target", "#F59E0B", "/goals", "/api/profile/goals/preview"),
    HubBlockData("Habits", "habits", "repeat", "#10B981", "/habits", "/api/profile/habits/preview"),
    HubBlockData(
        "Events", "events", "calendar", "#8B5CF6", "/events", "/api/profile/events/preview"
    ),
    HubBlockData(
        "Choices", "choices", "git-branch", "#F97316", "/choices", "/api/profile/choices/preview"
    ),
    HubBlockData(
        "Principles",
        "principles",
        "compass",
        "#EC4899",
        "/principles",
        "/api/profile/principles/preview",
    ),
]


def ActivityHubView() -> Div:
    """All 6 Activity Domains as scrollable blocks with 3 preview cards each."""
    return Div(
        PageHeader(
            "Activity Domains",
            subtitle="Your tasks, goals, habits, events, choices, and principles",
        ),
        HubDomainBlockList(ACTIVITY_BLOCKS),
    )
