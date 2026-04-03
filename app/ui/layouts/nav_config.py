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
    icon: str = ""  # Lucide icon name — when set, renders UkIcon instead of letter


@dataclass(frozen=True)
class DropdownItem:
    """Single item in a navbar dropdown menu."""

    label: str
    href: str
    icon: str = ""


# Activity domain dropdown items — REPLACED (2026-04-03)
# Individual domain links removed; single /activities link via ICON_NAV_ITEMS
ACTIVITY_DROPDOWN_ITEMS: tuple[DropdownItem, ...] = ()


# Curriculum domain dropdown items — SHELVED (2026-03-29)
# Curriculum sidebar removed; pages accessible via /profile hub cards
CURRICULUM_DROPDOWN_ITEMS: tuple[DropdownItem, ...] = ()

# Study workspace dropdown items — SHELVED (2026-03-29)
# Study sidebar removed; pages accessible via /profile hub cards
STUDY_DROPDOWN_ITEMS: tuple[DropdownItem, ...] = ()


# Icon navigation items — rendered as circular icon buttons in the left navbar section
# requires_auth=False → visible to unauthenticated users (ContentScope.SHARED pages)
# requires_auth=True  → visible only when authenticated (ContentScope.USER_OWNED pages)
ICON_NAV_ITEMS: tuple[IconNavItem, ...] = (
    IconNavItem(
        "Activity",
        "",
        "/activities",
        "activity",
        has_dropdown=False,
        icon="activity",
    ),
    IconNavItem(
        "Explore",
        "",
        "/explore",
        "explore",
        requires_auth=False,
        has_dropdown=False,
        icon="compass",
    ),
    IconNavItem(
        "Library",
        "",
        "/library",
        "library",
        requires_auth=False,
        has_dropdown=False,
        icon="book-open",
    ),
    IconNavItem(
        "GradeBook",
        "",
        "/gradebook",
        "gradebook",
        has_dropdown=False,
        icon="arrow-left-right",
    ),
)


__all__ = [
    "ACTIVITY_DROPDOWN_ITEMS",
    "CURRICULUM_DROPDOWN_ITEMS",
    "DropdownItem",
    "ICON_NAV_ITEMS",
    "IconNavItem",
    "MAIN_NAV_ITEMS",
    "NavItem",
    "STUDY_DROPDOWN_ITEMS",
]
