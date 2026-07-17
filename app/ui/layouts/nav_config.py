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
    NavItem(
        "Teaching", "/teaching/students", "teaching", requires_teacher=True, hide_for_admin=True
    ),
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
    icon: str = ""  # Icon name (ui/components/icon.py); when set, renders Icon vs letter
    hide_for_teacher: bool = False
    hide_for_admin: bool = False


@dataclass(frozen=True)
class DropdownItem:
    """Single item in a navbar dropdown menu."""

    label: str
    href: str
    icon: str = ""


# Activity domain dropdown items — used in mobile menu and avatar dropdown
ACTIVITY_DROPDOWN_ITEMS: tuple[DropdownItem, ...] = (
    DropdownItem("Tasks", "/tasks", icon="check-square"),
    DropdownItem("Events", "/events", icon="calendar"),
    DropdownItem("Goals", "/goals", icon="target"),
    DropdownItem("Habits", "/habits", icon="repeat"),
    DropdownItem("Principles", "/principles", icon="compass"),
    DropdownItem("Choices", "/choices", icon="git-branch"),
)


# Icon navigation items — rendered as circular icon buttons in the left navbar section
# requires_auth=False → visible to unauthenticated users (ContentScope.SHARED pages)
# requires_auth=True  → visible only when authenticated (ContentScope.USER_OWNED pages)
ICON_NAV_ITEMS: tuple[IconNavItem, ...] = (
    IconNavItem(
        "Today",
        "",
        "/today",
        "today",
        requires_auth=True,
        has_dropdown=False,
        icon="sun",
    ),
    IconNavItem(
        "Journals",
        "",
        "/journals",
        "journals",
        requires_auth=True,
        has_dropdown=False,
        icon="book-open",
    ),
    IconNavItem(
        "PathSteps",
        "",
        "/path-steps",
        "path-steps",
        requires_auth=False,
        has_dropdown=False,
        icon="map",
    ),
)


__all__ = [
    "ACTIVITY_DROPDOWN_ITEMS",
    "DropdownItem",
    "ICON_NAV_ITEMS",
    "IconNavItem",
    "MAIN_NAV_ITEMS",
    "NavItem",
]
