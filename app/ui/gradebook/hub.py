"""GradeBook block definitions — Reports tab on /profile.

GRADEBOOK_BLOCKS feeds the Reports tab in ui/profile/hub.py.
"""

from ui.patterns.hub import HubBlockData

GRADEBOOK_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "Entry Reports",
        "entry-reports",
        "clipboard",
        "#F59E0B",
        "/entry-reports",
        "/api/gradebook/entry-reports/preview",
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
