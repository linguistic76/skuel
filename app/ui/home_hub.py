"""Home hub page — post-login landing with cards linking to the 6 main sections.

Uses HubContainerGrid (navigational cards, no HTMX previews) for a 3x2 grid
linking to Profile, Explore, Library, GradeBook, Workbench, and Search.
"""

from fasthtml.common import Div

from ui.patterns.hub import HubCardData, HubContainerGrid
from ui.patterns.page_header import PageHeader

_HOME_CARDS: list[HubCardData] = [
    HubCardData(
        icon="\U0001f464",
        name="Profile",
        href="/profile",
        description="Your activity overview and domain connections",
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
        icon="\U0001f4ca",
        name="GradeBook",
        href="/gradebook",
        description="Track submissions and feedback",
    ),
    HubCardData(
        icon="\U0001f527",
        name="Workbench",
        href="/workbench",
        description="Upload data, submit exercises, settings",
    ),
    HubCardData(
        icon="\U0001f50d",
        name="Search",
        href="/search",
        description="Search across all domains",
    ),
]


def HomeHub() -> Div:
    """Home hub — 6 navigational cards in a 3x2 grid."""
    return Div(
        PageHeader("Home", subtitle="Welcome to SKUEL"),
        HubContainerGrid(_HOME_CARDS, cols=3),
    )
