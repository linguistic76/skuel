from enum import StrEnum
from typing import Any

import fasthtml.common as fh

from ui.components._util import _cls

__all__ = ["Button", "ButtonT"]

# Universal base classes applied to every button regardless of variant or size.
_BTN_BASE = (
    "inline-flex items-center justify-center font-medium transition-colors "
    "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring "
    "disabled:pointer-events-none disabled:opacity-50"
)

# Named size tokens. Injected via the size= kwarg so they never conflict with
# style-variant classes in the cls tuple (Tailwind has no runtime class override).
_BTN_SIZES: dict[str, str] = {
    "xs": "h-7 px-2 text-xs rounded-sm",
    "sm": "h-8 px-3 text-sm rounded-md",
    "md": "h-9 px-4 py-2 rounded-md text-sm",
    "lg": "h-11 px-8 rounded-md",
    "xl": "h-12 px-10 text-base rounded-md",
}


class ButtonT(StrEnum):
    """Button style-variant tokens. Values ARE the Tailwind class strings.

    Use cls= for style (colour/border/hover), size= kwarg for geometry (height/padding).
    Composing style and size via cls tuple works but size= is preferred because
    Tailwind cannot reliably resolve conflicting height/padding classes from the
    class attribute alone (cascade order is CSS-file order, not HTML-class order).

    Example::

        Button("Save", cls=ButtonT.primary)  # primary, medium
        Button("Delete", cls=ButtonT.destructive, size="sm")  # small destructive
    """

    # Style variants
    default = "border border-input bg-background hover:bg-accent hover:text-accent-foreground"
    primary = "bg-primary text-primary-foreground hover:bg-primary/90"
    secondary = "bg-secondary text-secondary-foreground hover:bg-secondary/80"
    ghost = "hover:bg-accent hover:text-accent-foreground"
    destructive = "bg-destructive text-destructive-foreground hover:bg-destructive/90"
    link = "text-primary underline-offset-4 hover:underline"

    # Size convenience constants — prefer size= kwarg over composing these in cls.
    xs = "h-7 px-2 text-xs rounded-sm"
    sm = "h-8 px-3 text-sm rounded-md"
    lg = "h-11 px-8 rounded-md"
    xl = "h-12 px-10 text-base rounded-md"


def Button(
    *c: Any,
    cls: str | tuple = ButtonT.default,
    size: str = "md",
    **kwargs: Any,
) -> Any:  # boundary: fasthtml-elements
    """Styled button. Always has usable geometry via the size= kwarg default.

    Args:
        *c: Button content (text, icons, etc.)
        cls: Style variant — a ButtonT value or tuple. Controls colour, border, and
             hover appearance. Does NOT set height or padding.
        size: Geometry — "xs", "sm", "md" (default), "lg", or "xl". Applied before
              cls so there is no Tailwind class conflict with style variants.
        **kwargs: Any HTML attribute (hx_*, x_*, data_*, aria_*, etc.) passes through.
    """
    size_cls = _BTN_SIZES.get(size, _BTN_SIZES["md"])
    return fh.Button(*c, cls=_cls(_BTN_BASE, size_cls, cls), **kwargs)
