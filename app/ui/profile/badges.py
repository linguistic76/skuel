"""Profile badge components.

Status and count badges for the profile sidebar.
"""

from typing import Any

from fasthtml.common import Span

from core.services.user.domain_health import DomainStatus
from ui.feedback import Badge, BadgeT


def HealthIndicator(status: str) -> Span:
    """
    Health status indicator dot.

    Args:
        status: One of "healthy", "warning", "critical"

    Returns:
        Span element with colored dot
    """
    color_classes = {
        "healthy": "bg-success",
        "warning": "bg-warning",
        "critical": "bg-error",
    }

    color_class = color_classes.get(status, "bg-muted-foreground")

    return Span(
        cls=f"w-2 h-2 rounded-full {color_class}",
        title=f"Status: {status}",
    )


def CountBadge(count: int, active: int | None = None) -> Any:  # boundary: fasthtml-elements
    """
    Count badge showing total (optionally with active subset).

    Args:
        count: Total count
        active: Optional active/pending count to highlight

    Returns:
        A neutral Badge with the count display
    """
    text = f"{active}/{count}" if active is not None and active > 0 else str(count)
    return Badge(text, variant=BadgeT.neutral)


__all__ = [
    "CountBadge",
    "DomainStatus",
    "HealthIndicator",
]
