"""Profile badge components.

Status and count badges for the profile sidebar.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fasthtml.common import A, Div, Span

if TYPE_CHECKING:
    from ui.profile.layout import ProfileDomainItem


def StatusBadge(status: str) -> Span:
    """
    Status indicator dot.

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
            StatusBadge(domain.status),
            cls="flex items-center gap-2",
        ),
        href=domain.href,
        cls=f"{base_classes} {state_classes}",
    )


@dataclass
class DomainStatus:
    """Helper for calculating domain status from UserContext."""

    @staticmethod
    def calculate_tasks_status(
        overdue_count: int,
        blocked_count: int,
    ) -> str:
        """Calculate tasks domain health status."""
        if overdue_count > 3 or blocked_count > 5:
            return "critical"
        elif overdue_count > 0 or blocked_count > 0:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_habits_status(at_risk_count: int) -> str:
        """Calculate habits domain health status."""
        if at_risk_count > 2:
            return "critical"
        elif at_risk_count > 0:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_goals_status(
        at_risk_count: int,
        stalled_count: int,
    ) -> str:
        """Calculate goals domain health status."""
        if at_risk_count > 0:
            return "critical"
        elif stalled_count > 0:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_events_status(
        missed_today: int,
        missed_week: int,
    ) -> str:
        """Calculate events domain health status."""
        if missed_today > 0:
            return "critical"
        elif missed_week > 0:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_principles_status(
        aligned_count: int,
        against_count: int,
    ) -> str:
        """Calculate principles domain health status."""
        if against_count > aligned_count:
            return "critical"
        elif aligned_count == 0 and against_count == 0:
            return "healthy"  # No decisions yet
        elif aligned_count < against_count * 2:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_choices_status(pending_count: int) -> str:
        """Calculate choices domain health status."""
        if pending_count > 5:
            return "critical"
        elif pending_count > 0:
            return "warning"
        return "healthy"


__all__ = [
    "CountBadge",
    "DomainSidebarItem",
    "DomainStatus",
    "StatusBadge",
]
