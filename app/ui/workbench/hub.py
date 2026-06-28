"""Exercises block definitions — Exercises tab on /profile.

SUBMISSIONS_BLOCKS feeds the Exercises tab in ui/profile/hub.py.
"""

from ui.patterns.hub import HubBlockData

SUBMISSIONS_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "Submit Exercise",
        "submit",
        "send",
        "#3B82F6",
        "/submit",
        "/api/submissions/submit/preview",
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
