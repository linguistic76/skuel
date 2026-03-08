"""
Teaching UI Badges
==================

Status and entity type badge components for teaching views.
"""

from fasthtml.common import Span


def status_badge(status: str) -> Span:
    """Render a DaisyUI badge for entity status."""
    badge_classes = {
        "submitted": "badge-warning",
        "active": "badge-info",
        "completed": "badge-success",
        "revision_requested": "badge-error",
        "draft": "badge-ghost",
    }
    cls = badge_classes.get(status, "badge-ghost")
    label = status.replace("_", " ").title()
    return Span(label, cls=f"badge {cls}")


def entity_type_badge(entity_type: str | None) -> Span:
    """Render a DaisyUI badge for entity type."""
    if not entity_type:
        return Span()
    label = entity_type.replace("_", " ").title()
    return Span(label, cls="badge badge-outline badge-sm")
