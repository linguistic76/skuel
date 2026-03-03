"""
SKUEL DaisyUI Button Components
================================

ButtonT enum and Button wrapper.
"""

from enum import Enum
from typing import Any

from fasthtml.common import Button as FTButton

from ui.layout import Size

__all__ = ["ButtonT", "Button"]


class ButtonT(str, Enum):
    """Button variant types - maps to DaisyUI btn-* classes."""

    primary = "btn-primary"
    secondary = "btn-secondary"
    accent = "btn-accent"
    neutral = "btn-neutral"
    ghost = "btn-ghost"
    link = "btn-link"
    info = "btn-info"
    success = "btn-success"
    warning = "btn-warning"
    error = "btn-error"
    outline = "btn-outline"


def Button(
    *c: Any,
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    outline: bool = False,
    disabled: bool = False,
    loading: bool = False,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Button wrapper.

    Args:
        *c: Button content (text, icons, etc.)
        cls: Additional CSS classes
        variant: Button style variant (primary, secondary, etc.)
        size: Button size (xs, sm, md, lg, xl)
        outline: If True, renders as outline button
        disabled: If True, button is disabled
        loading: If True, shows loading spinner
        **kwargs: Additional HTML attributes (hx_*, onclick, etc.)

    Example:
        Button("Submit", variant=ButtonT.primary, size=Size.lg)
        Button("Cancel", variant=ButtonT.ghost, hx_get="/cancel")
    """
    classes = ["btn", variant.value]

    if size:
        classes.append(f"btn-{size.value}")
    if outline and variant != ButtonT.outline:
        classes.append("btn-outline")
    if disabled:
        classes.append("btn-disabled")
    if loading:
        classes.append("loading")

    if cls:
        classes.append(cls)

    return FTButton(*c, cls=" ".join(classes), disabled=disabled, **kwargs)
