"""
Resource Media-Type Badge — shared
==================================

Colored pill badge for a Resource's media type (book / talk / film / podcast /
article / music). Shared across the library resources list and the
per-Resource detail page so the color language stays in one place.
"""

from typing import Any

from ui.feedback import Badge, BadgeT
from ui.layout import Size

_MEDIA_BADGE_MAP: dict[str, tuple[BadgeT | None, str]] = {
    "book": (BadgeT.success, ""),
    "talk": (BadgeT.info, ""),
    "film": (
        None,
        "bg-purple-100 dark:bg-purple-400/10 text-purple-800 dark:text-purple-300 border-purple-200 dark:border-purple-400/30",
    ),
    "podcast": (
        None,
        "bg-orange-100 dark:bg-orange-400/10 text-orange-800 dark:text-orange-300 border-orange-200 dark:border-orange-400/30",
    ),
    "article": (BadgeT.warning, ""),
    "music": (
        None,
        "bg-pink-100 dark:bg-pink-400/10 text-pink-800 dark:text-pink-300 border-pink-200 dark:border-pink-400/30",
    ),
}


def media_badge(media_type: str | None) -> Any:
    """Colored pill badge showing a resource's media type."""
    label = (media_type or "content").title()
    variant, custom_cls = _MEDIA_BADGE_MAP.get(media_type or "", (BadgeT.neutral, ""))
    return Badge(label, variant=variant, cls=custom_cls, size=Size.sm)


__all__ = ["media_badge"]
