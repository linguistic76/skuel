"""Library hub — block definitions and page component for the Library section.

LIBRARY_BLOCKS is imported by ui/home_hub.py to populate the Library tab
on /home, /submissions, /gradebook, and /library.

LibraryHub() is the standalone page component for /library.

See: /docs/design-principles/HUB_PAGES.md
"""

from fasthtml.common import Div

from ui.patterns.hub import HubBlockData, HubDomainBlockList
from ui.patterns.page_header import PageHeader

LIBRARY_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "Exercises",
        "exercises",
        "book-open",
        "#3B82F6",
        "/library/exercises",
        "/api/library/exercises/preview",
    ),
    HubBlockData(
        "Submission History",
        "history",
        "file-text",
        "#8B5CF6",
        "/submissions/history",
        "/api/submissions/history/preview",
    ),
    HubBlockData(
        "Resources",
        "resources",
        "bookmark",
        "#F59E0B",
        "/library/resources",
        "/api/library/resources/preview",
    ),
    HubBlockData(
        "Ku",
        "ku",
        "brain",
        "#8B5CF6",
        "/library/ku",
        "/api/library/ku/preview",
    ),
    HubBlockData(
        "Path Steps",
        "path-steps",
        "map",
        "#10B981",
        "/library/path-steps",
        "/api/library/path-steps/preview",
    ),
]


def LibraryHub() -> Div:
    """Library hub page content — PageHeader + block list for /library."""
    return Div(
        PageHeader(
            "Library", subtitle="Your exercises, submission history, resources, and curriculum"
        ),
        HubDomainBlockList(LIBRARY_BLOCKS),
    )
