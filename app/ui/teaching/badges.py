"""
Teaching UI Badges
==================

Status and entity type badge components for teaching views.
"""

from typing import Any

from core.models.enums import EntityType
from ui.feedback import Badge, BadgeT
from ui.layout import Size


def entity_type_badge(entity_type: EntityType | str | None) -> Any:
    """Render a badge for entity type."""
    if not entity_type:
        return ""
    type_str = entity_type.value if isinstance(entity_type, EntityType) else entity_type
    label = type_str.replace("_", " ").title()
    return Badge(label, variant=BadgeT.outline, size=Size.sm)
