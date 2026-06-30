"""Profile badge components.

Status and count badges for the profile sidebar.
"""

from fasthtml.common import Span

from core.services.user.domain_health import DomainStatus


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


def CountBadge(count: int, active: int | None = None) -> Span:
    """
    Count badge showing total (optionally with active subset).

    Args:
        count: Total count
        active: Optional active/pending count to highlight

    Returns:
        Span element with count display
    """
    if active is not None and active > 0:
        return Span(
            f"{active}/{count}",
            cls="text-xs font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-full",
        )

    return Span(
        str(count),
        cls="text-xs font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-full",
    )


__all__ = [
    "CountBadge",
    "DomainStatus",
    "HealthIndicator",
]
