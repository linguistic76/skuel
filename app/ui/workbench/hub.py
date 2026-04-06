"""Workbench hub page — where users get their work into SKUEL.

Hub page with no sidebar. Each block loads a preview via HTMX
and links to a child page that uses SidebarPage for within-section navigation.

See: /docs/design-principles/HUB_PAGES.md
"""

from fasthtml.common import Div

from ui.patterns.hub import HubBlockData, HubDomainBlockList
from ui.patterns.page_header import PageHeader

_WORKBENCH_BLOCKS: list[HubBlockData] = [
    HubBlockData(
        "Upload Activity Data",
        "upload",
        "upload-cloud",
        "#10B981",
        "/upload",
        "/api/workbench/upload/preview",
    ),
    HubBlockData(
        "Submit Exercise",
        "submit",
        "send",
        "#3B82F6",
        "/submit",
        "/api/workbench/submit/preview",
    ),
    HubBlockData(
        "Upload History",
        "history",
        "clock",
        "#8B5CF6",
        "/workbench/history",
        "/api/workbench/history/preview",
    ),
]


def WorkbenchHub() -> Div:
    """Workbench hub — 3 domain blocks with HTMX previews."""
    return Div(
        PageHeader(
            "Workbench",
            subtitle="Upload activity data, submit exercises, and track your contributions",
        ),
        HubDomainBlockList(_WORKBENCH_BLOCKS),
    )
