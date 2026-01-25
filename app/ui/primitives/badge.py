"""Badge components for status and priority indicators.

Badges are small visual indicators used to show status, priority,
or other categorical information. They use semantic colors from
the design system's status palette.
"""

from typing import Any

from fasthtml.common import Span


def Badge(text: str, variant: str = "default", **kwargs: Any) -> Any:
    """Inline badge with color variants.

    Args:
        text: The badge text content
        variant: Color variant - one of:
            - "default": Neutral gray
            - "primary": Accent color (blue)
            - "success": Green
            - "warning": Orange/amber
            - "error": Red
        **kwargs: Additional attributes passed to the Span element

    Returns:
        A Span element styled as a badge
    """
    variants = {
        "default": "bg-base-200 text-base-content/70",
        "primary": "bg-primary/10 text-primary",
        "success": "bg-success/10 text-success",
        "warning": "bg-warning/10 text-warning",
        "error": "bg-error/10 text-error",
    }
    variant_cls = variants.get(variant, variants["default"])
    base_cls = f"inline-flex px-2 py-0.5 text-xs font-medium rounded-full {variant_cls}"

    extra_cls = kwargs.pop("cls", "")
    full_cls = f"{base_cls} {extra_cls}".strip()

    return Span(text, cls=full_cls, **kwargs)


def StatusBadge(status: str | None, **kwargs: Any) -> Any:
    """Status-aware badge that maps status values to appropriate colors.

    Args:
        status: The status string (case-insensitive). Supported values:
            - "active" / "completed" -> success (green)
            - "pending" / "in_progress" -> warning (orange)
            - "blocked" / "failed" -> error (red)
            - "cancelled" / "archived" -> default (gray)
            - Other values are displayed as-is with default styling
        **kwargs: Additional attributes passed to Badge

    Returns:
        A Badge component with appropriate styling, or None if status is None
    """
    if status is None:
        return None

    status_lower = status.lower().replace("-", "_")

    status_map = {
        # Success states
        "active": ("Active", "success"),
        "completed": ("Completed", "success"),
        "done": ("Done", "success"),
        # Warning states
        "pending": ("Pending", "warning"),
        "in_progress": ("In Progress", "warning"),
        "waiting": ("Waiting", "warning"),
        # Error states
        "blocked": ("Blocked", "error"),
        "failed": ("Failed", "error"),
        "overdue": ("Overdue", "error"),
        # Default states
        "cancelled": ("Cancelled", "default"),
        "archived": ("Archived", "default"),
        "draft": ("Draft", "default"),
    }

    text, variant = status_map.get(status_lower, (status.title(), "default"))
    return Badge(text, variant, **kwargs)


def PriorityBadge(priority: str | None, **kwargs: Any) -> Any:
    """Priority-aware badge that maps priority values to appropriate colors.

    Args:
        priority: The priority string (case-insensitive). Supported values:
            - "critical" / "urgent" -> error (red)
            - "high" -> error (red)
            - "medium" / "normal" -> warning (orange)
            - "low" -> success (green)
            - Other values are displayed as-is with default styling
        **kwargs: Additional attributes passed to Badge

    Returns:
        A Badge component with appropriate styling, or None if priority is None
    """
    if priority is None:
        return None

    priority_lower = priority.lower()

    priority_map = {
        # Critical/Urgent - red
        "critical": ("Critical", "error"),
        "urgent": ("Urgent", "error"),
        # High - red
        "high": ("High", "error"),
        # Medium - orange
        "medium": ("Medium", "warning"),
        "normal": ("Normal", "warning"),
        # Low - green
        "low": ("Low", "success"),
    }

    text, variant = priority_map.get(priority_lower, (priority.title(), "default"))
    return Badge(text, variant, **kwargs)
