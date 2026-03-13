"""Learning page layout with sidebar.

Used by /learn/submit, /learn/submissions, /learn/exercise-reports, /learn/activity-reports, /learn/generate-reports.
NOT used by the /learn landing page.
"""

from typing import TYPE_CHECKING, Any

from ui.learn.sidebar import LEARN_SIDEBAR_ITEMS
from ui.patterns.sidebar import SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


async def create_learn_page(
    content: Any,
    active_section: str,
    request: "Request | None" = None,
    title: str = "Learn",
) -> "FT":
    """Wrap content in the Learning sidebar layout.

    Args:
        content: Main content HTML
        active_section: Currently active section slug ("submit", "submissions", "exercise-reports", "activity-reports", "generate-reports")
        request: Starlette request for navbar auto-detection
        title: Page title for browser tab
    """
    return await SidebarPage(
        content=content,
        items=LEARN_SIDEBAR_ITEMS,
        active=active_section,
        title="Learn",
        subtitle="",
        storage_key="learn-sidebar",
        page_title=title,
        request=request,
        active_page="learn",
        title_href="/learn",
    )
