"""Study page layout with sidebar.

Used by /submit, /submissions, /exercise-reports, /activity-reports, /generate-reports.
NOT used by the /study landing page.
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarPage
from ui.study.sidebar import STUDY_SIDEBAR_ITEMS

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


async def create_study_page(
    content: Any,
    active_section: str,
    request: "Request | None" = None,
    title: str = "Study",
) -> "FT":
    """Wrap content in the Study sidebar layout.

    Args:
        content: Main content HTML
        active_section: Currently active section slug ("submit", "submissions", "exercise-reports", "activity-reports", "generate-reports")
        request: Starlette request for navbar auto-detection
        title: Page title for browser tab
    """
    return await SidebarPage(
        content=content,
        items=STUDY_SIDEBAR_ITEMS,
        active=active_section,
        title="Study",
        subtitle="",
        storage_key="study-sidebar",
        page_title=title,
        request=request,
        active_page="study",
        title_href="/study",
    )
