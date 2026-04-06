"""Submissions hub page — where users upload data, submit exercises, and track history.

Hub page with no sidebar. Each block loads a preview via HTMX
and links to a child page that uses SidebarPage for within-section navigation.

See: /docs/design-principles/HUB_PAGES.md
"""

from fasthtml.common import Div

from ui.patterns.hub import HubBlockData, HubDomainBlockList
from ui.patterns.page_header import PageHeader

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


def SubmissionsHub() -> Div:
    """Submissions hub — 3 domain blocks with HTMX previews."""
    return Div(
        PageHeader(
            "Submissions",
            subtitle="Upload activity data, submit exercises, and track your submissions",
        ),
        HubDomainBlockList(SUBMISSIONS_BLOCKS),
    )
