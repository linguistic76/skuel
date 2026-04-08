"""GradeBook hub — block definitions for the shared tabbed hub interface.

GRADEBOOK_BLOCKS is imported by ui/home_hub.py to populate the GradeBook tab
on /home, /submissions, /gradebook, and /library.

See: /docs/design-principles/HUB_PAGES.md
"""

from ui.patterns.hub import HubBlockData

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
