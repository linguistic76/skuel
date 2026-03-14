"""Page type definitions for SKUEL unified UX design system.

Defines the two page paradigms:
- STANDARD: Centered content without sidebar (most pages)
- CUSTOM: Full-width, page manages its own layout (sidebar pages use SidebarPage)

Usage:
    from ui.layouts.page_types import PageType, PAGE_CONFIG

    config = PAGE_CONFIG[PageType.STANDARD]
    container_cls = config["container"]  # "max-w-6xl mx-auto"
"""

from enum import StrEnum
from typing import TypedDict


class PageType(StrEnum):
    """Page layout types for consistent UX."""

    STANDARD = "standard"  # Centered content, no sidebar (most pages)
    CUSTOM = "custom"  # Full-width, page manages its own layout


class PageConfig(TypedDict):
    """Configuration for a page type."""

    container: str
    content_padding: str


PAGE_CONFIG: dict[PageType, PageConfig] = {
    PageType.STANDARD: {
        "container": "max-w-6xl mx-auto",
        "content_padding": "p-6 lg:p-8",
    },
    PageType.CUSTOM: {
        "container": "",
        "content_padding": "",
    },
}


# Container width constant (1152px) - the standard for SKUEL
CONTAINER_WIDTH = "max-w-6xl"


__all__ = ["PageType", "PageConfig", "PAGE_CONFIG", "CONTAINER_WIDTH"]
