"""GradeBook hub page — HTMX-loaded preview blocks for feedback and reports.

Hub page with no sidebar. Each block loads a preview via HTMX
and links to a child page that uses SidebarPage for within-section navigation.

See: /docs/design-principles/HUB_PAGES.md
"""

from fasthtml.common import Div

from ui.patterns.hub import HubBlockData, HubDomainBlockList
from ui.patterns.page_header import PageHeader

_GRADEBOOK_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "Exercise Reports",
        "exercise-reports",
        "clipboard",
        "#F59E0B",
        "/exercise-reports",
        "/api/gradebook/exercise-reports/preview",
    ),
    HubBlockData(
        "Activity Reports",
        "activity-reports",
        "bar-chart-2",
        "#8B5CF6",
        "/activity-reports",
        "/api/gradebook/activity-reports/preview",
    ),
    HubBlockData(
        "Revisions",
        "revised-exercises",
        "refresh-cw",
        "#EF4444",
        "/revised-exercises",
        "/api/gradebook/revised-exercises/preview",
    ),
]


def GradeBookHub() -> Div:
    """GradeBook hub — 3 domain blocks with HTMX previews."""
    return Div(
        PageHeader("GradeBook", subtitle="Track your submissions and feedback"),
        HubDomainBlockList(_GRADEBOOK_BLOCKS),
    )
