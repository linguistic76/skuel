"""Metadata badge — label + value inline badge for detail pages."""

from typing import Any

from fasthtml.common import Span

from ui.feedback import Badge, BadgeT


def metadata_badge(label: str, value: str, variant: BadgeT = BadgeT.ghost) -> Any:
    """Render a metadata badge with a bold label and value."""
    return Badge(
        Span(label, cls="font-medium mr-1"),
        value,
        variant=variant,
        cls="gap-1",
    )
