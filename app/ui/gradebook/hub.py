"""GradeBook hub page — entry point with container navigation.

Hub page with no sidebar. Each container links to a child page
that uses SidebarPage for within-section navigation.

See: /docs/design-principles/HUB_PAGES.md
"""

from fasthtml.common import Div

from ui.patterns.hub import HubCardData, HubContainerGrid
from ui.patterns.page_header import PageHeader


def GradeBookHub() -> Div:
    """GradeBook hub — 4 containers for submissions and feedback."""
    containers = [
        HubCardData(
            icon="📝",
            name="My Submissions",
            href="/gradebook/mysubmissions",
            description="Your submitted exercises and their feedback status.",
        ),
        HubCardData(
            icon="📤",
            name="Submit",
            href="/submit",
            description="Upload your completed exercise worksheet.",
        ),
        HubCardData(
            icon="📋",
            name="Exercise Reports",
            href="/exercise-reports",
            description="Teacher and AI feedback on your exercise submissions.",
        ),
        HubCardData(
            icon="📊",
            name="Activity Reports",
            href="/activity-reports",
            description="AI and scheduled feedback on your activity patterns.",
        ),
    ]
    return Div(
        PageHeader("GradeBook", subtitle="Track your submissions and feedback"),
        HubContainerGrid(containers, cols=2),
    )
