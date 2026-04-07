"""Profile badge components.

Status and count badges for the profile sidebar.
"""

from typing import TYPE_CHECKING

from fasthtml.common import A, Div, Span

from core.services.user.domain_health import DomainStatus

if TYPE_CHECKING:
    from ui.profile.layout import ProfileDomainItem


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


def DomainSidebarItem(domain: "ProfileDomainItem", is_active: bool) -> A:
    """
    Full sidebar item with icon, name, count, and status.

    Args:
        domain: ProfileDomainItem with domain info
        is_active: Whether this domain is currently selected

    Returns:
        Anchor element for sidebar navigation
    """
    # Base classes
    base_classes = (
        "flex items-center justify-between px-3 py-2.5 rounded-lg transition-colors group"
    )

    # Active vs inactive styling
    if is_active:
        state_classes = (
            "bg-primary/10 text-primary font-semibold border-l-4 border-primary -ml-1 pl-4"
        )
    else:
        state_classes = "text-muted-foreground hover:text-foreground hover:bg-background"

    return A(
        # Left side: icon + name
        Div(
            Span(domain.icon, cls="text-lg mr-2"),
            Span(domain.name, cls="font-medium"),
            cls="flex items-center",
        ),
        # Right side: count + status
        Div(
            CountBadge(domain.count, domain.active_count),
            HealthIndicator(domain.status),
            cls="flex items-center gap-2",
        ),
        href=domain.href,
        cls=f"{base_classes} {state_classes}",
    )


__all__ = [
    "CountBadge",
    "DomainSidebarItem",
    "DomainStatus",
    "HealthIndicator",
]
