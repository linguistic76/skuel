"""Admin dashboard page layout.

Uses SidebarPage for consistent navigation with all other SKUEL sidebar pages.
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT
    from starlette.requests import Request


ADMIN_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Overview", "/admin", "overview", icon="📊"),
    SidebarItem("Users", "/admin/users", "users", icon="👥"),
    SidebarItem("Analytics", "/admin/analytics", "analytics", icon="📈"),
    SidebarItem("Learning", "/admin/learning", "learning", icon="📚"),
    SidebarItem("System", "/admin/system", "system", icon="⚙️"),
    SidebarItem(
        "Finance",
        "/finance",
        "finance",
        icon="💰",
        badge_text="→",
        hx_attrs={"target": "_blank"},
    ),
    SidebarItem(
        "Ingestion",
        "/ingest",
        "ingestion",
        icon="📥",
        badge_text="→",
        hx_attrs={"target": "_blank"},
    ),
]


async def create_admin_page(
    content: Any,
    active_section: str = "",
    admin_username: str = "",
    title: str = "Admin Dashboard",
    request: "Request | None" = None,
    system_status: str = "healthy",
) -> "FT":
    """Create an admin dashboard page using the unified SidebarPage pattern.

    Args:
        content: Main page content
        active_section: Currently active section slug (empty = overview)
        admin_username: Admin's display name for sidebar heading
        title: Page title (browser tab)
        request: Starlette request for auto-detecting auth state
        system_status: Unused — kept for call-site compatibility
    """
    active = active_section if active_section else "overview"

    return await SidebarPage(
        content=content,
        items=ADMIN_SIDEBAR_ITEMS,
        active=active,
        title=admin_username or "Admin",
        subtitle="Admin Dashboard",
        storage_key="admin-sidebar",
        page_title=title,
        request=request,
        active_page="admin",
    )


__all__ = [
    "ADMIN_SIDEBAR_ITEMS",
    "create_admin_page",
]
