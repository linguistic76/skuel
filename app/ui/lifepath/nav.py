"""LifePath sidebar navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import Request

LIFEPATH_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Dashboard", "/lifepath", "dashboard", icon="\U0001f3e0"),
    SidebarItem("Vision", "/lifepath/vision", "vision", icon="\U0001f441"),
    SidebarItem("Alignment", "/lifepath/alignment", "alignment", icon="\U0001f4ca"),
]


async def lifepath_sidebar_page(
    active_page: str,
    content: Any,
    request: Request,
    extra_scripts: list[str] | None = None,
) -> Any:
    """Create sidebar page for LifePath routes.

    Args:
        extra_scripts: Page-specific JS (e.g. Chart.js for the alignment radar).
    """
    return await SidebarPage(
        content=content,
        items=LIFEPATH_SIDEBAR_ITEMS,
        active=active_page,
        title="Life Path",
        subtitle="Your Journey",
        storage_key="lifepath-sidebar",
        request=request,
        active_page="lifepath",
        extra_scripts=extra_scripts,
    )
