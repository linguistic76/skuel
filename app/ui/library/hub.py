"""Library hub — block definitions for the shared tabbed hub interface.

LIBRARY_BLOCKS is imported by ui/home_hub.py to populate the Library tab
on /home, /submissions, /gradebook, and /library.

See: /docs/design-principles/HUB_PAGES.md
"""

from ui.patterns.hub import HubBlockData

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
