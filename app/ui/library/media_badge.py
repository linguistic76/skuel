"""
Resource Media-Type Badge — shared
==================================

Colored pill badge for a Resource's media type (book / talk / film / podcast /
article / music). Shared across the library hub list, the hub previews, and the
per-Resource detail page so the color language stays in one place.
"""

from typing import Any

from ui.feedback import Badge, BadgeT
from ui.layout import Size

_MEDIA_BADGE_MAP: dict[str, tuple[BadgeT | None, str]] = {
    "book": (BadgeT.success, ""),
    "talk": (BadgeT.info, ""),
    "film": (None, "bg-purple-100 text-purple-800 border-purple-200"),
    "podcast": (None, "bg-orange-100 text-orange-800 border-orange-200"),
    "article": (BadgeT.warning, ""),
    "music": (None, "bg-pink-100 text-pink-800 border-pink-200"),
}


def media_badge(media_type: str | None) -> Any:
    """Colored pill badge showing a resource's media type."""
    label = (media_type or "content").title()
    variant, custom_cls = _MEDIA_BADGE_MAP.get(media_type or "", (BadgeT.neutral, ""))
    return Badge(label, variant=variant, cls=custom_cls, size=Size.sm)


__all__ = ["media_badge"]
