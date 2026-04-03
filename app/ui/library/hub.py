"""Library hub page — entry point with container navigation.

Hub page with no sidebar. Each container links to a child page
that uses SidebarPage for within-section navigation.

See: /docs/design-principles/HUB_PAGES.md
"""

from fasthtml.common import Div

from ui.patterns.hub import HubCardData, HubContainerGrid
from ui.patterns.page_header import PageHeader


def LibraryHub() -> Div:
    """Library hub — 4 containers for learning resources."""
    containers = [
        HubCardData(
            icon="📖",
            name="Exercises",
            href="/library/exercises",
            description="Assigned and personal exercises with submission status.",
        ),
        HubCardData(
            icon="🔖",
            name="Resources",
            href="/library/resources",
            description="Curated books, talks, films, and other learning materials.",
        ),
        HubCardData(
            icon="🧠",
            name="Ku",
            href="/library/ku",
            description="Your bookmarked knowledge units for quick reference.",
        ),
        HubCardData(
            icon="🗺️",
            name="Path Steps",
            href="/library/path-steps",
            description="Path steps you are currently enrolled in.",
        ),
    ]
    return Div(
        PageHeader("Library", subtitle="Browse exercises, resources, and knowledge"),
        HubContainerGrid(containers, cols=2),
    )
