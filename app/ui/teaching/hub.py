"""Teaching hub page — static container grid for teaching sections.

Hub page with no sidebar. Container cards link to child pages
that use SidebarPage for within-section navigation.
"""

from fasthtml.common import Div

from ui.patterns.hub import HubCardData, HubContainerGrid
from ui.patterns.page_header import PageHeader

_TEACHING_CARDS: list[HubCardData] = [
    HubCardData(
        icon="👥",
        name="Students",
        href="/teaching/students",
        description="View and manage your students",
    ),
    HubCardData(
        icon="👥",
        name="Groups",
        href="/teaching/groups",
        description="Manage class groups",
    ),
    HubCardData(
        icon="📥",
        name="Review Queue",
        href="/teaching/queue",
        description="Submissions awaiting your review",
    ),
]


def TeachingHub() -> Div:
    """Teaching hub — 3 container cards linking to teaching sections."""
    return Div(
        PageHeader("Teaching", subtitle="Manage students, groups, and submissions"),
        HubContainerGrid(_TEACHING_CARDS),
    )
