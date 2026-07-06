"""Library block definitions — Curriculum tab on /profile.

LIBRARY_BLOCKS feeds the Curriculum tab in ui/profile/hub.py. Submission
History was moved to the Submissions tab so each block has a single home.
"""

from ui.patterns.hub import HubBlockData

LIBRARY_BLOCKS: list[HubBlockData] = [
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
    HubBlockData(
        "Exercises",
        "exercises",
        "book-open",
        "#3B82F6",
        "/library/exercises",
        "/api/library/exercises/preview",
    ),
]
