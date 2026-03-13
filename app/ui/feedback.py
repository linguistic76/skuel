"""
SKUEL Feedback Components (MonsterUI)
======================================

Alert, Badge, Loading, Progress, RadialProgress wrappers.
Uses MonsterUI where available, Tailwind utilities for semantic badges.
"""

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, Span
from monsterui.daisy import Alert as MAlert
from monsterui.daisy import AlertT as MAlertT
from monsterui.daisy import Loading as MLoading
from monsterui.daisy import LoadingT as MLoadingT

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
    """Get badge class for submission/report status.

    Centralised mapping used by submissions_ui, journals_ui, and user_profile_ui.
    Delegates to ui.badge_classes for the canonical mapping.
    """
    from ui.badge_classes import submission_status_badge_class

    return submission_status_badge_class(status)


class AlertT(StrEnum):
    """Alert variant types."""

    info = "info"
    success = "success"
    warning = "warning"
    error = "error"


# Mapping SKUEL AlertT to MonsterUI AlertT
_ALERT_MAP: dict[str, MAlertT] = {
    "info": MAlertT.info,
    "success": MAlertT.success,
    "warning": MAlertT.warning,
    "error": MAlertT.error,
}


class BadgeT(StrEnum):
    """Badge variant types — mapped to Tailwind utility classes."""

    primary = "primary"
    secondary = "secondary"
    accent = "accent"
    neutral = "neutral"
    ghost = "ghost"
    info = "info"
    success = "success"
    warning = "warning"
    error = "error"
    outline = "outline"


# Badge color classes (Tailwind utilities)
_BADGE_COLORS: dict[str, str] = {
    "primary": "bg-primary/10 text-primary border-primary/20",
    "secondary": "bg-secondary text-secondary-foreground border-secondary",
    "accent": "bg-violet-100 text-violet-800 border-violet-200",
    "neutral": "bg-muted text-muted-foreground border-border",
    "ghost": "bg-muted/50 text-muted-foreground border-transparent",
    "info": "bg-blue-100 text-blue-800 border-blue-200",
    "success": "bg-green-100 text-green-800 border-green-200",
    "warning": "bg-yellow-100 text-yellow-800 border-yellow-200",
    "error": "bg-red-100 text-red-800 border-red-200",
    "outline": "bg-transparent text-foreground border-border",
}


class ProgressT(StrEnum):
    """Progress variant types — mapped to Tailwind colors."""

    primary = "primary"
    secondary = "secondary"
    accent = "accent"
    info = "info"
    success = "success"
    warning = "warning"
    error = "error"


class LoadingT(StrEnum):
    """Loading spinner variant types."""

    spinner = "spinner"
    dots = "dots"
    ring = "ring"
    ball = "ball"
    bars = "bars"
    infinity = "infinity"


def Alert(
    *c: Any,
    cls: str = "",
    variant: AlertT = AlertT.info,
    **kwargs: Any,
) -> Any:
    """
    Alert wrapper using MonsterUI.

    Args:
        *c: Alert content
        cls: Additional CSS classes
        variant: Alert style variant (info, success, warning, error)
        **kwargs: Additional HTML attributes
    """
    mu_variant = _ALERT_MAP.get(variant.value, MAlertT.info)
    cls_parts = [mu_variant]
    if cls:
        cls_parts.append(cls)
    return MAlert(*c, cls=tuple(cls_parts), **kwargs)


def Badge(
    *c: Any,
    cls: str = "",
    variant: BadgeT | None = BadgeT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """
    Badge/pill component using Tailwind utility classes.

    Args:
        *c: Badge content
        cls: Additional CSS classes
        variant: Badge style variant (None to skip color — caller provides via cls)
        size: Badge size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes
    """
    color_cls = _BADGE_COLORS.get(variant.value, _BADGE_COLORS["neutral"]) if variant else ""

    size_cls = {
        "xs": "text-[10px] px-1.5 py-0",
        "sm": "text-xs px-2 py-0.5",
        "md": "text-xs px-2.5 py-0.5",
        "lg": "text-sm px-3 py-1",
    }

    classes = ["inline-flex items-center rounded-full border font-medium", color_cls]
    if size:
        classes.append(size_cls.get(size.value, size_cls["sm"]))
    else:
        classes.append(size_cls["sm"])

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
    Loading spinner using MonsterUI.

    Args:
        cls: Additional CSS classes
        variant: Loading animation type
        size: Loading size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes
    """
    # Map SKUEL LoadingT to MonsterUI LoadingT
    mu_loading_map: dict[str, MLoadingT] = {
        "spinner": MLoadingT.spinner,
        "dots": MLoadingT.dots,
        "ring": MLoadingT.ring,
        "ball": MLoadingT.ball,
        "bars": MLoadingT.bars,
        "infinity": MLoadingT.infinity,
    }
    mu_size_map: dict[str, MLoadingT] = {
        "xs": MLoadingT.xs,
        "sm": MLoadingT.sm,
        "md": MLoadingT.md,
        "lg": MLoadingT.lg,
    }

    mu_variant = mu_loading_map.get(variant.value, MLoadingT.spinner)
    mu_size = mu_size_map.get(size.value, MLoadingT.md)

    return MLoading(cls=(mu_variant, mu_size, cls) if cls else (mu_variant, mu_size), **kwargs)


def Progress(
    value: int | float | None = None,
    max_val: int = 100,
    cls: str = "",
    variant: ProgressT = ProgressT.primary,
    **kwargs: Any,
) -> Any:
    """
    Progress bar using MonsterUI.

    Args:
        value: Current progress value (None for indeterminate)
        max_val: Maximum value (default 100)
        cls: Additional CSS classes
        variant: Progress color variant
        **kwargs: Additional HTML attributes
    """
    from monsterui.franken import Progress as MProgress

    cls_parts = []
    if cls:
        cls_parts.append(cls)

    attrs: dict[str, Any] = {"max": str(max_val)}
    if value is not None:
        attrs["value"] = str(int(value))
    if cls_parts:
        attrs["cls"] = " ".join(cls_parts)

    return MProgress(**attrs, **kwargs)


def RadialProgress(
    value: int | float,
    cls: str = "",
    variant: "ButtonT" = None,  # type: ignore[assignment]
    size: str = "4rem",
    **kwargs: Any,
) -> Any:
    """
    Radial progress (circular) — custom SKUEL component (no MonsterUI equivalent).

    Args:
        value: Progress percentage (0-100)
        cls: Additional CSS classes
        variant: Color variant (ignored in MonsterUI — uses primary)
        size: Size as CSS value (e.g., "4rem", "5rem")
        **kwargs: Additional HTML attributes
    """
    classes = ["relative inline-flex items-center justify-center"]
    if cls:
        classes.append(cls)

    pct = int(value)
    # SVG-based radial progress
    return Div(
        Div(
            f"{pct}%",
            cls="absolute text-xs font-semibold text-foreground",
        ),
        Div(
            cls="radial-progress-ring",
            style=f"--value:{pct}; --size:{size}; width:{size}; height:{size};",
        ),
        cls=" ".join(classes),
        role="progressbar",
        **{"aria-valuenow": str(pct), "aria-valuemin": "0", "aria-valuemax": "100"},
        **kwargs,
    )


def StatusBadge(status: str | None, **kwargs: Any) -> Any:
    """Status-aware badge that maps status values to badge variants.

    Args:
        status: The status string (case-insensitive). Supported values:
            - "active" / "completed" / "done" -> success
            - "pending" / "in_progress" / "waiting" -> warning
            - "blocked" / "failed" / "overdue" -> error
            - "cancelled" / "archived" / "draft" -> neutral
        **kwargs: Additional attributes passed to Badge

    Returns:
        A Badge with appropriate variant, or None if status is None
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
    """Priority-aware badge that maps priority values to badge variants.

    Args:
        priority: The priority string (case-insensitive). Supported values:
            - "critical" / "urgent" / "high" -> error
            - "medium" / "normal" -> warning
            - "low" -> success
        **kwargs: Additional attributes passed to Badge

    Returns:
        A Badge with appropriate variant, or None if priority is None
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
