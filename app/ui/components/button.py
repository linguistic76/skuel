from enum import StrEnum
from typing import Any

import fasthtml.common as fh

from ui.components._util import _cls

__all__ = ["Button", "ButtonT"]

# Base classes applied to every button regardless of variant.
_BTN_BASE = (
    "inline-flex items-center justify-center font-medium transition-colors "
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring "
    "disabled:pointer-events-none disabled:opacity-50"
)


class ButtonT(StrEnum):
    """Button variant and size tokens. Values are the Tailwind class strings.

    Compose via cls tuple: cls=(ButtonT.primary, ButtonT.sm)
    """

    # Style variants
    default = "border border-input bg-background hover:bg-accent hover:text-accent-foreground"
    primary = "bg-primary text-primary-foreground hover:bg-primary/90"
    secondary = "bg-secondary text-secondary-foreground hover:bg-secondary/80"
    ghost = "hover:bg-accent hover:text-accent-foreground"
    destructive = "bg-destructive text-destructive-foreground hover:bg-destructive/90"
    link = "text-primary underline-offset-4 hover:underline"

    # Size variants
    xs = "h-7 px-2 text-xs rounded"
    sm = "h-8 px-3 text-sm rounded-md"
    lg = "h-11 px-8 rounded-md"
    xl = "h-12 px-10 text-base rounded-md"


def Button(
    *c: Any, cls: str | tuple = ButtonT.default, **kwargs: Any
) -> Any:  # boundary: fasthtml-elements
    """Styled button wrapping the FT Button element.

    Args:
        *c: Button content (text, icons, etc.)
        cls: Variant string or tuple of ButtonT values. Merged after base classes.
        **kwargs: Any HTML attribute (hx_*, x_*, data_*, aria_*, etc.) passes through.
    """
    return fh.Button(*c, cls=_cls(_BTN_BASE, cls), **kwargs)
