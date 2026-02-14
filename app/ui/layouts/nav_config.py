"""
Navigation Configuration
========================

Type-safe navigation items for the navbar.
Centralized configuration following SKUEL patterns.

Usage:
    from ui.layouts.nav_config import MAIN_NAV_ITEMS, NavItem
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    """
    Immutable navigation item configuration.

    Attributes:
        label: Display text for the link
        href: URL path to navigate to
        page_key: Key for active state matching (matches active_page param)
        requires_auth: Whether link requires authentication (default True)
        requires_admin: Whether link requires admin role (default False)
        requires_teacher: Whether link requires teacher role (default False)
    """

    label: str
    href: str
    page_key: str
    requires_auth: bool = True
    requires_admin: bool = False
    requires_teacher: bool = False


# Main navigation items - order determines display order
# Note: Profile is accessed via the avatar link in the navbar right section, not here.
MAIN_NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("Search", "/search", "search"),
    NavItem("Askesis", "/askesis", "askesis"),
    NavItem("Events", "/events", "events"),
    NavItem("Journals", "/journals", "journals"),
    NavItem("Reports", "/reports", "reports"),
    NavItem("Teaching", "/teaching", "teaching", requires_teacher=True),
    NavItem("Knowledge", "/ku", "knowledge"),
)

# Admin-only navigation item - prepended to nav when user is admin
ADMIN_NAV_ITEM = NavItem(
    label="Admin Dashboard",
    href="/admin",
    page_key="admin",
    requires_admin=True,
)

# Profile dropdown items - activity domains accessible from navbar avatar
# Events is already a top-level nav item in MAIN_NAV_ITEMS
PROFILE_DROPDOWN_ITEMS: tuple[NavItem, ...] = (
    NavItem("Tasks", "/tasks", "tasks"),
    NavItem("Goals", "/goals", "goals"),
    NavItem("Habits", "/habits", "habits"),
    NavItem("Choices", "/choices", "choices"),
    NavItem("Principles", "/principles", "principles"),
)

# Account items shown below a divider in the profile dropdown
PROFILE_ACCOUNT_ITEMS: tuple[NavItem, ...] = (
    NavItem("Settings", "/settings", "settings"),
    NavItem("Sign out", "/logout", "logout"),
)

__all__ = [
    "NavItem",
    "MAIN_NAV_ITEMS",
    "ADMIN_NAV_ITEM",
    "PROFILE_DROPDOWN_ITEMS",
    "PROFILE_ACCOUNT_ITEMS",
]
