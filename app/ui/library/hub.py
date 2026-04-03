"""Library hub page — HTMX-loaded preview blocks for learning resources.

Hub page with no sidebar. Each block loads a preview via HTMX
and links to a child page that uses SidebarPage for within-section navigation.

See: /docs/design-principles/HUB_PAGES.md
"""

from fasthtml.common import Div

from ui.patterns.hub import HubBlockData, HubDomainBlockList
from ui.patterns.page_header import PageHeader

_LIBRARY_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "Exercises",
        "exercises",
        "book-open",
        "#3B82F6",
        "/library/exercises",
        "/api/library/exercises/preview",
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
    """Library hub — 4 domain blocks with HTMX previews."""
    return Div(
        PageHeader("Library", subtitle="Browse exercises, resources, and knowledge"),
        HubDomainBlockList(_LIBRARY_BLOCKS),
    )
