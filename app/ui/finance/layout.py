"""Finance Hub page layout.

Uses SidebarPage for consistent navigation with all other SKUEL sidebar pages.
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request


FINANCE_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Invoices", "/finance/invoices", "invoices", icon="📄"),
]


def create_finance_page(
    content: Any,
    active_section: str = "",
    title: str = "Finance Hub",
    request: "Request | None" = None,
) -> "FT":
    """Create a finance hub page using the unified SidebarPage pattern.

    Args:
        content: Main page content
        active_section: Currently active section slug (empty = dashboard)
        title: Page title (browser tab)
        request: Starlette request for auto-detecting auth state
    """
    active = active_section if active_section else "dashboard"

    return SidebarPage(
        content=content,
        items=FINANCE_SIDEBAR_ITEMS,
        active=active,
        title="💰 Finance Hub",
        subtitle="Invoices",
        storage_key="finance-sidebar",
        page_title=title,
        request=request,
        active_page="finance",
    )


__all__ = [
    "FINANCE_SIDEBAR_ITEMS",
    "create_finance_page",
]
