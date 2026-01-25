"""Admin UI module.

Provides admin dashboard layout and navigation components.
All admin routes require ADMIN role.
"""

from ui.admin.layout import (
    ADMIN_NAV_ITEMS,
    AdminLayout,
    AdminNavItem,
    create_admin_page,
)

__all__ = [
    "ADMIN_NAV_ITEMS",
    "AdminLayout",
    "AdminNavItem",
    "create_admin_page",
]
