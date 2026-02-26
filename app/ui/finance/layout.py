"""Finance Hub page layout.

Uses SidebarPage for consistent navigation with all other SKUEL sidebar pages.
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


FINANCE_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Dashboard", "/finance", "dashboard", icon="📊"),
    SidebarItem("Expenses", "/finance/expenses", "expenses", icon="💵"),
    SidebarItem("Invoices", "/finance/invoices", "invoices", icon="📄"),
    SidebarItem("Budgets", "/finance/budgets", "budgets", icon="📈"),
    SidebarItem("Reports", "/finance/reports", "reports", icon="📋"),
    SidebarItem("Analytics", "/finance/analytics", "analytics", icon="🔍"),
]


async def create_finance_page(
    content: Any,
    active_section: str = "",
    admin_username: str = "",
    title: str = "Finance Hub",
    request: "Request | None" = None,
    budget_health: str = "healthy",
) -> "FT":
    """Create a finance hub page using the unified SidebarPage pattern.

    Args:
        content: Main page content
        active_section: Currently active section slug (empty = dashboard)
        admin_username: Admin's display name (unused — kept for compatibility)
        title: Page title (browser tab)
        request: Starlette request for auto-detecting auth state
        budget_health: Unused — kept for call-site compatibility
    """
    active = active_section if active_section else "dashboard"

    return await SidebarPage(
        content=content,
        items=FINANCE_SIDEBAR_ITEMS,
        active=active,
        title="💰 Finance Hub",
        subtitle="Expenses, budgets & reports",
        storage_key="finance-sidebar",
        page_title=title,
        request=request,
        active_page="finance",
    )


__all__ = [
    "FINANCE_SIDEBAR_ITEMS",
    "create_finance_page",
]
