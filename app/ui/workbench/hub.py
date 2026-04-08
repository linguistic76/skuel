"""Submissions hub — block definitions for the shared tabbed hub interface.

SUBMISSIONS_BLOCKS is imported by ui/home_hub.py to populate the Submissions tab
on /home, /submissions, /gradebook, and /library.

See: /docs/design-principles/HUB_PAGES.md
"""

from ui.patterns.hub import HubBlockData

SUBMISSIONS_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "Upload Activity Data",
        "upload",
        "upload-cloud",
        "#10B981",
        "/upload",
        "/api/submissions/upload/preview",
    ),
    HubBlockData(
        "Submit Exercise",
        "submit",
        "send",
        "#3B82F6",
        "/submit",
        "/api/submissions/submit/preview",
    ),
    HubBlockData(
        "Submission History",
        "history",
        "file-text",
        "#8B5CF6",
        "/submissions/history",
        "/api/submissions/history/preview",
    ),
]
