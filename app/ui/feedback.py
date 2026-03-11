"""
SKUEL DaisyUI Feedback Components
================================

AlertT, BadgeT, ProgressT, LoadingT enums and Alert, Badge, Loading,
Progress, RadialProgress wrappers.
"""

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Span

if TYPE_CHECKING:
    from ui.buttons import ButtonT

from ui.layout import Size

__all__ = [
    "AlertT",
    "BadgeT",
    "ProgressT",
    "LoadingT",
    "Alert",
    "Badge",
    "Loading",
    "PriorityBadge",
    "Progress",
    "RadialProgress",
    "StatusBadge",
    "get_submission_status_badge_class",
]


def get_submission_status_badge_class(status: str) -> str:
    """Get DaisyUI badge class for submission/report status.

    Centralised mapping used by submissions_ui, journals_ui, and user_profile_ui.
    Delegates to ui.badge_classes for the canonical mapping.
    """
    from ui.badge_classes import submission_status_badge_class

    return submission_status_badge_class(status)


class AlertT(StrEnum):
    """Alert variant types - maps to DaisyUI alert-* classes."""

    info = "alert-info"
    success = "alert-success"
    warning = "alert-warning"
    error = "alert-error"


class BadgeT(StrEnum):
    """Badge variant types - maps to DaisyUI badge-* classes."""

    primary = "badge-primary"
    secondary = "badge-secondary"
    accent = "badge-accent"
    neutral = "badge-neutral"
    ghost = "badge-ghost"
    info = "badge-info"
    success = "badge-success"
    warning = "badge-warning"
    error = "badge-error"
    outline = "badge-outline"


class ProgressT(StrEnum):
    """Progress variant types - maps to DaisyUI progress-* classes."""

    primary = "progress-primary"
    secondary = "progress-secondary"
    accent = "progress-accent"
    info = "progress-info"
    success = "progress-success"
    warning = "progress-warning"
    error = "progress-error"


class LoadingT(StrEnum):
    """Loading spinner variant types."""

    spinner = "loading-spinner"
    dots = "loading-dots"
    ring = "loading-ring"
    ball = "loading-ball"
    bars = "loading-bars"
    infinity = "loading-infinity"


def Alert(
    *c: Any,
    cls: str = "",
    variant: AlertT = AlertT.info,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Alert wrapper.

    Args:
        *c: Alert content
        cls: Additional CSS classes
        variant: Alert style variant (info, success, warning, error)
        **kwargs: Additional HTML attributes

    Example:
        Alert("Operation successful!", variant=AlertT.success)
        Alert(Span("Warning!"), P("Please review."), variant=AlertT.warning)
    """
    classes = ["alert", variant.value]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), role="alert", **kwargs)


def Badge(
    *c: Any,
    cls: str = "",
    variant: BadgeT = BadgeT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Badge wrapper.

    Args:
        *c: Badge content
        cls: Additional CSS classes
        variant: Badge style variant
        size: Badge size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes

    Example:
        Badge("New", variant=BadgeT.primary)
        Badge("5", variant=BadgeT.error, size=Size.sm)
    """
    classes = ["badge", variant.value]
    if size:
        classes.append(f"badge-{size.value}")
    if cls:
        classes.append(cls)
    return Span(*c, cls=" ".join(classes), **kwargs)


def Loading(
    cls: str = "",
    variant: LoadingT = LoadingT.spinner,
    size: Size = Size.md,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Loading spinner.

    Args:
        cls: Additional CSS classes
        variant: Loading animation type
        size: Loading size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes

    Example:
        Loading(size=Size.lg)
        Loading(variant=LoadingT.dots, size=Size.sm)
    """
    classes = ["loading", variant.value, f"loading-{size.value}"]
    if cls:
        classes.append(cls)
    return Span(cls=" ".join(classes), **kwargs)


def Progress(
    value: int | float | None = None,
    max_val: int = 100,
    cls: str = "",
    variant: ProgressT = ProgressT.primary,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Progress bar.

    Args:
        value: Current progress value (None for indeterminate)
        max_val: Maximum value (default 100)
        cls: Additional CSS classes
        variant: Progress color variant
        **kwargs: Additional HTML attributes

    Example:
        Progress(value=75, variant=ProgressT.success)
        Progress()  # Indeterminate
    """
    from fasthtml.common import Progress as FTProgress

    classes = ["progress", variant.value, "w-full"]
    if cls:
        classes.append(cls)

    attrs = {"cls": " ".join(classes), "max": str(max_val)}
    if value is not None:
        attrs["value"] = str(int(value))

    return FTProgress(**attrs, **kwargs)


def RadialProgress(
    value: int | float,
    cls: str = "",
    variant: "ButtonT" = None,  # type: ignore[assignment]
    size: str = "4rem",
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Radial progress (circular).

    Args:
        value: Progress percentage (0-100)
        cls: Additional CSS classes
        variant: Color variant (from ui.buttons.ButtonT)
        size: Size as CSS value (e.g., "4rem", "5rem")
        **kwargs: Additional HTML attributes

    Example:
        RadialProgress(75, variant=ButtonT.success)
    """
    from ui.buttons import ButtonT

    if variant is None:
        variant = ButtonT.primary
    classes = ["radial-progress", variant.value.replace("btn-", "text-")]
    if cls:
        classes.append(cls)

    style = f"--value:{int(value)}; --size:{size};"
    return Div(
        f"{int(value)}%",
        cls=" ".join(classes),
        style=style,
        role="progressbar",
        **kwargs,
    )


def StatusBadge(status: str | None, **kwargs: Any) -> Any:
    """Status-aware badge that maps status values to DaisyUI badge variants.

    Args:
        status: The status string (case-insensitive). Supported values:
            - "active" / "completed" / "done" -> success
            - "pending" / "in_progress" / "waiting" -> warning
            - "blocked" / "failed" / "overdue" -> error
            - "cancelled" / "archived" / "draft" -> neutral
        **kwargs: Additional attributes passed to Badge

    Returns:
        A DaisyUI Badge with appropriate variant, or None if status is None
    """
    if status is None:
        return None

    status_lower = status.lower().replace("-", "_")

    status_map: dict[str, tuple[str, BadgeT]] = {
        # Success states
        "active": ("Active", BadgeT.success),
        "completed": ("Completed", BadgeT.success),
        "done": ("Done", BadgeT.success),
        # Warning states
        "pending": ("Pending", BadgeT.warning),
        "in_progress": ("In Progress", BadgeT.warning),
        "waiting": ("Waiting", BadgeT.warning),
        # Error states
        "blocked": ("Blocked", BadgeT.error),
        "failed": ("Failed", BadgeT.error),
        "overdue": ("Overdue", BadgeT.error),
        # Neutral states
        "cancelled": ("Cancelled", BadgeT.neutral),
        "archived": ("Archived", BadgeT.neutral),
        "draft": ("Draft", BadgeT.neutral),
    }

    text, variant = status_map.get(status_lower, (status.title(), BadgeT.neutral))
    return Badge(text, variant=variant, **kwargs)


def PriorityBadge(priority: str | None, **kwargs: Any) -> Any:
    """Priority-aware badge that maps priority values to DaisyUI badge variants.

    Args:
        priority: The priority string (case-insensitive). Supported values:
            - "critical" / "urgent" / "high" -> error
            - "medium" / "normal" -> warning
            - "low" -> success
        **kwargs: Additional attributes passed to Badge

    Returns:
        A DaisyUI Badge with appropriate variant, or None if priority is None
    """
    if priority is None:
        return None

    priority_lower = priority.lower()

    priority_map: dict[str, tuple[str, BadgeT]] = {
        "critical": ("Critical", BadgeT.error),
        "urgent": ("Urgent", BadgeT.error),
        "high": ("High", BadgeT.error),
        "medium": ("Medium", BadgeT.warning),
        "normal": ("Normal", BadgeT.warning),
        "low": ("Low", BadgeT.success),
    }

    text, variant = priority_map.get(priority_lower, (priority.title(), BadgeT.neutral))
    return Badge(text, variant=variant, **kwargs)
