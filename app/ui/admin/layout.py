"""Admin dashboard page layout.

Uses SidebarPage for consistent navigation with all other SKUEL sidebar pages.
"""

from typing import TYPE_CHECKING, Any

from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request


ADMIN_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem("Overview", "/admin", "overview", icon="layout-dashboard"),
    SidebarItem("Users", "/admin/users", "users", icon="users"),
    SidebarItem("Analytics", "/admin/analytics", "analytics", icon="trending-up"),
    SidebarItem(
        "Knowledge Health", "/admin/knowledge-health", "knowledge-health", icon="stethoscope"
    ),
    SidebarItem("Prereq Edges", "/admin/prereq-suggestions", "prereq", icon="link"),
    SidebarItem("Transcription", "/admin/batch-transcribe", "transcription", icon="mic"),
    SidebarItem("System", "/admin/system", "system", icon="settings"),
    SidebarItem(
        "Finance",
        "/finance/invoices",
        "finance",
        icon="wallet",
        badge_text="→",
        hx_attrs={"target": "_blank"},
    ),
    SidebarItem(
        "Ingestion",
        "/ingest",
        "ingestion",
        icon="folder-input",
        badge_text="→",
        hx_attrs={"target": "_blank"},
    ),
]


def create_admin_page(
    content: Any,
    active_section: str = "",
    admin_username: str = "",
    title: str = "Admin Dashboard",
    request: Request | None = None,
) -> FT:
    """Create an admin dashboard page using the unified SidebarPage pattern.

    Args:
        content: Main page content
        active_section: Currently active section slug (empty = overview)
        admin_username: Admin's display name for sidebar heading
        title: Page title (browser tab)
        request: Starlette request for auto-detecting auth state
    """
    active = active_section if active_section else "overview"

    return SidebarPage(
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
