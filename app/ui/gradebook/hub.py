"""GradeBook block definitions — Reports tab on /profile.

GRADEBOOK_BLOCKS feeds the Reports tab in ui/profile/hub.py. The previews
keep their per-kind endpoints; every block opens the one GradeBook page
(the 3→1 collapse, feedback-loop UX arc 2 C1) — preview cards link to the
kept detail routes directly.
"""

from ui.patterns.hub import HubBlockData

GRADEBOOK_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "Entry Reports",
        "entry-reports",
        "clipboard",
        "#F59E0B",
        "/gradebook",
        "/api/gradebook/entry-reports/preview",
    ),
    HubBlockData(
        "Activity Reports",
        "activity-reports",
        "bar-chart-2",
        "#8B5CF6",
        "/gradebook",
        "/api/gradebook/activity-reports/preview",
    ),
    HubBlockData(
        "Revisions",
        "revised-exercises",
        "refresh-cw",
        "#EF4444",
        "/gradebook",
        "/api/gradebook/revised-exercises/preview",
    ),
]
