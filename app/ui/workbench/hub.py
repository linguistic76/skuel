"""Submissions block definitions — Submissions tab on /profile.

SUBMISSIONS_BLOCKS feeds the Submissions tab in ui/profile/hub.py.
"""

from ui.patterns.hub import HubBlockData

SUBMISSIONS_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "New Journal",
        "journal",
        "book-open",
        "#8B5CF6",
        "/journals",
        "/api/submissions/journal/preview",
        view_all_href="/journals/browse",
    ),
    HubBlockData(
        "Submit Exercise",
        "submit",
        "send",
        "#3B82F6",
        "/submit",
        "/api/submissions/submit/preview",
    ),
]
