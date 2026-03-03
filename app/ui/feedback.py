"""
SKUEL DaisyUI Feedback Components
================================

AlertT, BadgeT, ProgressT, LoadingT enums and Alert, Badge, Loading,
Progress, RadialProgress wrappers.
"""

from enum import Enum
from typing import Any

from fasthtml.common import Div, Span

from ui.layout import Size

__all__ = [
    "AlertT",
    "BadgeT",
    "ProgressT",
    "LoadingT",
    "Alert",
    "Badge",
    "Loading",
    "Progress",
    "RadialProgress",
]


class AlertT(str, Enum):
    """Alert variant types - maps to DaisyUI alert-* classes."""

    info = "alert-info"
    success = "alert-success"
    warning = "alert-warning"
    error = "alert-error"


class BadgeT(str, Enum):
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


class ProgressT(str, Enum):
    """Progress variant types - maps to DaisyUI progress-* classes."""

    primary = "progress-primary"
    secondary = "progress-secondary"
    accent = "progress-accent"
    info = "progress-info"
    success = "progress-success"
    warning = "progress-warning"
    error = "progress-error"


class LoadingT(str, Enum):
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
