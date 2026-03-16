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
    hide_for_admin: bool = False


# Main navigation items - order determines display order
MAIN_NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("Teaching", "/teaching", "teaching", requires_teacher=True),
)


@dataclass(frozen=True)
class IconNavItem:
    """Immutable icon-only navigation item for the navbar left section.

    Renders as a circular button with a single letter (e.g., "A" for Activities).
    """

    label: str
    letter: str
    href: str
    page_key: str
    requires_auth: bool = True
    has_dropdown: bool = False


@dataclass(frozen=True)
class DropdownItem:
    """Single item in a navbar dropdown menu."""

    label: str
    href: str
    icon: str = ""


# Activity domain dropdown items — shown on hover over the "A" icon
ACTIVITY_DROPDOWN_ITEMS: tuple[DropdownItem, ...] = (
    DropdownItem("Tasks", "/tasks", icon="✅"),
    DropdownItem("Goals", "/goals", icon="🎯"),
    DropdownItem("Habits", "/habits", icon="🔄"),
    DropdownItem("Events", "/events", icon="📅"),
    DropdownItem("Choices", "/choices", icon="🔀"),
    DropdownItem("Principles", "/principles", icon="⚖️"),
)


# Curriculum domain dropdown items — shown on hover over the "C" icon
CURRICULUM_DROPDOWN_ITEMS: tuple[DropdownItem, ...] = (
    DropdownItem("Lessons", "/lessons", icon="📖"),
    DropdownItem("Learning Steps", "/learning-steps", icon="🧩"),
    DropdownItem("Learning Paths", "/learning-paths", icon="🗺️"),
    DropdownItem("Exercises", "/exercises", icon="🏋️"),
)

# Study workspace dropdown items — shown on hover over the "S" icon
STUDY_DROPDOWN_ITEMS: tuple[DropdownItem, ...] = (
    DropdownItem("Submit", "/submit", icon="📤"),
    DropdownItem("My Submissions", "/submissions", icon="📝"),
    DropdownItem("Exercise Reports", "/exercise-reports", icon="📋"),
    DropdownItem("Activity Reports", "/activity-reports", icon="📊"),
    DropdownItem("Generate Reports", "/generate-reports", icon="⚡"),
)


# Icon navigation items — rendered as circular letter buttons in the left navbar section
ICON_NAV_ITEMS: tuple[IconNavItem, ...] = (
    IconNavItem("Activities", "A", "/profile", "activities", has_dropdown=True),
    IconNavItem("Curriculum", "C", "/curriculum", "curriculum", has_dropdown=True),
    IconNavItem("Study", "S", "/study", "study", has_dropdown=True),
)

# Admin-only navigation item - prepended to nav when user is admin
ADMIN_NAV_ITEM = NavItem(
    label="Admin Dashboard",
    href="/admin",
    page_key="admin",
    requires_admin=True,
)

__all__ = [
    "ACTIVITY_DROPDOWN_ITEMS",
    "ADMIN_NAV_ITEM",
    "CURRICULUM_DROPDOWN_ITEMS",
    "DropdownItem",
    "ICON_NAV_ITEMS",
    "IconNavItem",
    "MAIN_NAV_ITEMS",
    "NavItem",
    "STUDY_DROPDOWN_ITEMS",
]
