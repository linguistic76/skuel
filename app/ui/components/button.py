from enum import StrEnum
from typing import Any

import fasthtml.common as fh

from ui.components._util import _cls

__all__ = ["Button", "ButtonT"]

# Universal base classes applied to every button regardless of variant or size.
_BTN_BASE = (
    "inline-flex items-center justify-center text-center font-medium transition-colors "
    "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring "
    "disabled:pointer-events-none disabled:opacity-50"
)

# Named size tokens. Injected via the size= kwarg so they never conflict with
# style-variant classes in the cls tuple (Tailwind has no runtime class override).
# A size sets a MINIMUM height, never a height: a label that wraps grows its button
# instead of spilling out of it. Each size's vertical padding is the largest half-step
# at which one line of its own text, inside a 1px border, still fits that minimum — so
# a one-line button keeps its height, bordered or not, and a wrapped one is padded.
_BTN_SIZES: dict[str, str] = {
    "xs": "min-h-7 px-2 py-1 text-xs rounded-sm",
    "sm": "min-h-8 px-3 py-1 text-sm rounded-md",
    "md": "min-h-9 px-4 py-1.5 rounded-md text-sm",
    "lg": "min-h-11 px-8 py-2 rounded-md",
    "xl": "min-h-12 px-10 py-2.5 text-base rounded-md",
    # A button standing in a row of fields takes the field heights as its minimum:
    # 44px on phones, 40px from ``md`` (``ui.components.form``'s field size).
    "field": "min-h-11 md:min-h-10 px-4 py-2.5 md:py-2 rounded-md text-sm",
}


class ButtonT(StrEnum):
    """Button style-variant tokens. Values ARE the Tailwind class strings.

    Use cls= for style (colour/border/hover), size= kwarg for geometry (height/padding).
    Geometry never goes in cls: Tailwind cannot resolve two height or padding classes
    on one element by their order in the class attribute (cascade order is CSS-file
    order, not HTML-class order).

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
        size: Geometry — "xs", "sm", "md" (default), "lg", "xl", or "field" (the
              field heights, for a button beside an input or select). Applied
              before cls so there is no Tailwind class conflict with style variants.
        **kwargs: Any HTML attribute (hx_*, x_*, data_*, aria_*, etc.) passes through.
    """
    size_cls = _BTN_SIZES.get(size, _BTN_SIZES["md"])
    return fh.Button(*c, cls=_cls(_BTN_BASE, size_cls, cls), **kwargs)
