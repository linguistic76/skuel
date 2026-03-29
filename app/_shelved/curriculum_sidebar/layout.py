"""Curriculum page layout with sidebar.

Used by /lessons, /learning-steps, /learning-paths, /exercises.
NOT used by the /curriculum landing page.
"""

from typing import TYPE_CHECKING, Any

from ui.curriculum.sidebar import CURRICULUM_SIDEBAR_ITEMS
from ui.patterns.sidebar import SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


async def create_curriculum_page(
    content: Any,
    active_section: str,
    request: "Request | None" = None,
    title: str = "Curriculum",
) -> "FT":
    """Wrap content in the Curriculum sidebar layout.

    Args:
        content: Main content HTML
        active_section: Currently active section slug ("lessons", "learning-steps", "learning-paths", "exercises")
        request: Starlette request for navbar auto-detection
        title: Page title for browser tab
    """
    return await SidebarPage(
        content=content,
        items=CURRICULUM_SIDEBAR_ITEMS,
        active=active_section,
        title="Curriculum",
        subtitle="",
        storage_key="curriculum-sidebar",
        page_title=title,
        request=request,
        active_page="curriculum",
        title_href="/curriculum",
    )
