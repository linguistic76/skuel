"""GradeBook hub — block definitions and page component for the GradeBook section.

GRADEBOOK_BLOCKS is imported by ui/home_hub.py to populate the GradeBook tab
on /home, /submissions, /gradebook, and /library.

GradeBookHub() is the standalone page component for /gradebook.

See: /docs/design-principles/HUB_PAGES.md
"""

from fasthtml.common import Div

from ui.patterns.hub import HubBlockData, HubDomainBlockList
from ui.patterns.page_header import PageHeader

GRADEBOOK_BLOCKS: list[HubBlockData] = [
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
    """GradeBook hub page content — PageHeader + block list for /gradebook."""
    return Div(
        PageHeader("GradeBook", subtitle="Your exercise reports, activity reports, and revisions"),
        HubDomainBlockList(GRADEBOOK_BLOCKS),
    )
