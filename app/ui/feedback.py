"""
SKUEL Feedback Components
==========================

Alert, Badge, Loading, Progress, RadialProgress — pure Tailwind, no MonsterUI.
"""

from enum import StrEnum
from typing import Any

from fasthtml.common import Div, Span

from ui.components import Alert as _SKUELAlert
from ui.components import Loading as _SKUELLoading
from ui.components import Progress as _SKUELProgress
from ui.components.feedback import AlertT
from ui.layout import Size

__all__ = [
    "AlertT",
    "BadgeT",
    "ProgressT",
    "Alert",
    "Badge",
    "Loading",
    "PriorityBadge",
    "Progress",
    "RadialProgress",
    "StatusBadge",
]


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


def Alert(
    *c: Any,
    cls: str = "",
    variant: AlertT = AlertT.info,
    **kwargs: Any,
) -> Any:
    """Semantic alert box.

    Args:
        *c: Alert content
        cls: Additional CSS classes
        variant: Alert style variant (info, success, warning, error)
        **kwargs: Additional HTML attributes
    """
    return _SKUELAlert(*c, variant=variant, cls=cls, **kwargs)


def Badge(
    *c: Any,
    cls: str = "",
    variant: BadgeT | None = BadgeT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """Badge/pill component using Tailwind utility classes.

    Args:
        *c: Badge content
        cls: Additional CSS classes
        variant: Badge style variant (None to skip color — caller provides via cls)
        size: Badge size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes
    """
    color_cls = _BADGE_COLORS.get(variant.value, _BADGE_COLORS["neutral"]) if variant else ""

    size_cls = {
        "xs": "text-10 px-1.5 py-0",
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
    size: Size = Size.md,
    **kwargs: Any,
) -> Any:
    """Loading spinner.

    Args:
        cls: Additional CSS classes
        size: Spinner size (xs, sm, md, lg)
        **kwargs: Additional HTML attributes
    """
    return _SKUELLoading(cls=cls, size=size.value, **kwargs)


def Progress(
    value: int | float | None = None,
    max_val: int = 100,
    cls: str = "",
    variant: ProgressT = ProgressT.primary,
    **kwargs: Any,
) -> Any:
    """Horizontal progress bar.

    Args:
        value: Current progress value (None for empty bar)
        max_val: Maximum value (default 100)
        cls: Additional CSS classes
        variant: Progress color variant
        **kwargs: Additional HTML attributes
    """
    return _SKUELProgress(value=value, max_val=max_val, cls=cls, variant=variant.value, **kwargs)


def RadialProgress(
    value: int | float,
    cls: str = "",
    variant: str | None = None,
    size: str = "4rem",
    **kwargs: Any,
) -> Any:
    """Radial progress (circular) — custom SKUEL SVG component.

    Args:
        value: Progress percentage (0-100)
        cls: Additional CSS classes
        variant: Color variant (reserved for future use)
        size: Size as CSS value (e.g., "4rem", "5rem")
        **kwargs: Additional HTML attributes
    """
    classes = ["relative inline-flex items-center justify-center"]
    if cls:
        classes.append(cls)

    pct = int(value)
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


def StatusBadge(status: str | None, cls: str = "", **kwargs: Any) -> Any:
    """Status-aware badge that delegates to EntityStatus for canonical styling.

    Covers all 14 EntityStatus values (active, completed, submitted, processing,
    queued, revision_requested, etc.) via EntityStatus.get_badge_class().

    Args:
        status: The status string (case-insensitive).
        cls: Additional CSS classes, merged after the status badge class.
        **kwargs: Additional attributes passed to Badge

    Returns:
        A Badge with appropriate variant, or None if status is None
    """
    if status is None:
        return None

    from core.models.enums import EntityStatus

    status_lower = status.lower().replace("-", "_")
    display_text = status_lower.replace("_", " ").title()

    try:
        entity_status = EntityStatus(status_lower)
        badge_cls = entity_status.get_badge_class()
    except ValueError:
        badge_cls = "bg-base-200 text-base-content/70 border-base-200"

    return Badge(display_text, variant=None, cls=f"{badge_cls} {cls}".strip(), **kwargs)


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
