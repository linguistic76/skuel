"""GradeBook block definitions — GradeBook tab on /profile.

GRADEBOOK_BLOCKS feeds the GradeBook tab in ui/profile/hub.py.
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
