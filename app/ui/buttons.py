"""
SKUEL DaisyUI Button Components
================================

ButtonT enum and Button wrapper.
"""

from enum import Enum
from typing import Any

from fasthtml.common import A
from fasthtml.common import Button as FTButton

from ui.layout import Size

__all__ = ["ButtonT", "Button", "ButtonLink", "IconButton"]


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


def ButtonLink(
    *c: Any,
    href: str,
    cls: str = "",
    variant: ButtonT = ButtonT.primary,
    size: Size | None = None,
    **kwargs: Any,
) -> Any:
    """Button-styled link for navigation.

    Use when the action is navigation rather than form submission.

    Args:
        *c: Link content (text, icons, etc.)
        href: URL to navigate to
        cls: Additional CSS classes
        variant: Button style variant
        size: Button size (xs, sm, md, lg, xl)
        **kwargs: Additional HTML attributes
    """
    classes = ["btn", variant.value]
    if size:
        classes.append(f"btn-{size.value}")
    if cls:
        classes.append(cls)
    return A(*c, href=href, cls=" ".join(classes), **kwargs)


def IconButton(
    icon: str,
    cls: str = "",
    variant: ButtonT = ButtonT.ghost,
    size: Size | None = None,
    label: str | None = None,
    **kwargs: Any,
) -> Any:
    """Icon-only button with optional aria-label.

    Args:
        icon: The icon content (emoji or SVG)
        cls: Additional CSS classes
        variant: Button style variant (default: ghost)
        size: Button size
        label: Accessible label for screen readers
        **kwargs: Additional attributes passed to the Button element
    """
    classes = ["btn", variant.value, "btn-square"]
    if size:
        classes.append(f"btn-{size.value}")
    if cls:
        classes.append(cls)

    if label:
        kwargs["aria_label"] = label

    return FTButton(icon, cls=" ".join(classes), **kwargs)
