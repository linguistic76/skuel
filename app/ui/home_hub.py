"""Home hub page — post-login landing with Submissions, GradeBook, and navigational cards.

Inlines Submissions and GradeBook HTMX preview blocks at the top,
followed by a 2x2 card grid linking to Tasks+, Explore, Library, and Settings.
"""

from fasthtml.common import Div

from ui.gradebook.hub import GRADEBOOK_BLOCKS
from ui.patterns.hub import HubCardData, HubContainerGrid, HubDomainBlockList
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.workbench.hub import SUBMISSIONS_BLOCKS

_HOME_CARDS: list[HubCardData] = [
    HubCardData(
        icon="\u2713",
        name="Tasks +",
        href="/profile",
        description="Your tasks, goals, habits, and more at a glance",
    ),
    HubCardData(
        icon="\U0001f9ed",
        name="Explore",
        href="/explore",
        description="Discover knowledge units and path steps",
    ),
    HubCardData(
        icon="\U0001f4da",
        name="Library",
        href="/library",
        description="Browse exercises, resources, and curriculum",
    ),
    HubCardData(
        icon="\u2699\ufe0f",
        name="Settings",
        href="/settings",
        description="Preferences, display, notifications",
    ),
]


def HomeHub() -> Div:
    """Home hub — Submissions + GradeBook previews, then 4 navigational cards."""
    return Div(
        PageHeader("Home", subtitle="Welcome to SKUEL"),
        Div(
            SectionHeader("Submissions"),
            HubDomainBlockList(SUBMISSIONS_BLOCKS),
            cls="mb-8",
        ),
        Div(
            SectionHeader("GradeBook"),
            HubDomainBlockList(GRADEBOOK_BLOCKS),
            cls="mb-8",
        ),
        HubContainerGrid(_HOME_CARDS, cols=2),
    )
