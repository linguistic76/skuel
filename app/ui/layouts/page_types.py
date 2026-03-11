"""Page type definitions for SKUEL unified UX design system.

Defines the two page paradigms:
- HUB: Sidebar navigation for multi-domain access (Profile Hub)
- STANDARD: Centered content without sidebar (most pages)

Usage:
    from ui.layouts.page_types import PageType, PAGE_CONFIG

    config = PAGE_CONFIG[PageType.STANDARD]
    container_cls = config["container"]  # "max-w-6xl mx-auto"
"""

from enum import StrEnum
from typing import TypedDict


class PageType(StrEnum):
    """Page layout types for consistent UX."""

    HUB = "hub"  # Sidebar + multi-domain navigation (Profile Hub)
    STANDARD = "standard"  # Centered content, no sidebar (most pages)
    CUSTOM = "custom"  # Full-width, page manages its own layout


class PageConfig(TypedDict):
    """Configuration for a page type."""

    sidebar: bool
    sidebar_width: str
    container: str
    content_padding: str


PAGE_CONFIG: dict[PageType, PageConfig] = {
    PageType.HUB: {
        "sidebar": True,
        "sidebar_width": "w-64",
        "container": "flex-1 min-w-0",
        "content_padding": "p-6 lg:p-8",
    },
    PageType.STANDARD: {
        "sidebar": False,
        "sidebar_width": "",
        "container": "max-w-6xl mx-auto",
        "content_padding": "p-6 lg:p-8",
    },
    PageType.CUSTOM: {
        "sidebar": False,
        "sidebar_width": "",
        "container": "",
        "content_padding": "",
    },
}


# Container width constant (1152px) - the standard for SKUEL
CONTAINER_WIDTH = "max-w-6xl"


__all__ = ["PageType", "PageConfig", "PAGE_CONFIG", "CONTAINER_WIDTH"]
