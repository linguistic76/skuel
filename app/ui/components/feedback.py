from enum import StrEnum
from typing import Any

from fasthtml.common import Div, Span

from ui.components._util import _cls

__all__ = ["Alert", "AlertT", "Loading", "LoadingT"]


class AlertT(StrEnum):
    info = "info"
    success = "success"
    warning = "warning"
    error = "error"


class LoadingT(StrEnum):
    """Loading animation style tokens (CSS-only spinner uses spinner variant)."""

    spinner = "spinner"
    dots = "dots"
    ring = "ring"
    ball = "ball"
    bars = "bars"
    infinity = "infinity"


_ALERT_CLASSES: dict[str, str] = {
    "info": "bg-blue-50 border-blue-200 text-blue-800",
    "success": "bg-green-50 border-green-200 text-green-800",
    "warning": "bg-yellow-50 border-yellow-200 text-yellow-800",
    "error": "bg-red-50 border-red-200 text-red-800",
}

# CSS-only spinner — no DaisyUI dependency.
_LOADING_BASE = (
    "inline-block animate-spin rounded-full border-2 border-current border-t-transparent"
)

_LOADING_SIZES: dict[str, str] = {
    "xs": "w-3 h-3",
    "sm": "w-4 h-4",
    "md": "w-6 h-6",
    "lg": "w-8 h-8",
}


def Alert(
    *c: Any, variant: AlertT = AlertT.info, cls: str = "", **kwargs: Any
) -> Any:  # boundary: fasthtml-elements
    """Semantic alert box with icon-and-text layout.

    Args:
        *c: Alert content (text, icons, etc.)
        variant: Visual style — info, success, warning, or error.
        cls: Additional Tailwind classes.
        **kwargs: Any HTML attribute passes through.
    """
    color_cls = _ALERT_CLASSES.get(str(variant), _ALERT_CLASSES["info"])
    return Div(
        *c,
        cls=_cls("flex items-start gap-3 rounded-lg border p-4 text-sm", color_cls, cls),
        role="alert",
        **kwargs,
    )


def Loading(cls: str = "", size: str = "md", **kwargs: Any) -> Any:
    """CSS-only loading spinner.

    Args:
        cls: Additional Tailwind classes.
        size: "xs", "sm", "md", or "lg". Controls the spinner dimensions.
        **kwargs: Any HTML attribute passes through.
    """
    size_cls = _LOADING_SIZES.get(size, _LOADING_SIZES["md"])
    return Span(
        cls=_cls(_LOADING_BASE, size_cls, cls),
        role="status",
        **{"aria-label": "Loading"},
        **kwargs,
    )
