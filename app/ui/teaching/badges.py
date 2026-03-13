"""
Teaching UI Badges
==================

Status and entity type badge components for teaching views.
"""

from typing import Any

from ui.feedback import Badge, BadgeT
from ui.layout import Size


def status_badge(status: str) -> Any:
    """Render a badge for entity status."""
    badge_variants: dict[str, BadgeT] = {
        "submitted": BadgeT.warning,
        "active": BadgeT.info,
        "completed": BadgeT.success,
        "revision_requested": BadgeT.error,
        "draft": BadgeT.ghost,
    }
    variant = badge_variants.get(status, BadgeT.ghost)
    label = status.replace("_", " ").title()
    return Badge(label, variant=variant)


def entity_type_badge(entity_type: str | None) -> Any:
    """Render a badge for entity type."""
    if not entity_type:
        return ""
    label = entity_type.replace("_", " ").title()
    return Badge(label, variant=BadgeT.outline, size=Size.sm)
