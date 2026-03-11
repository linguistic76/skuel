"""
SKUEL DaisyUI Card Components
================================

CardT enum and Card, CardBody, CardTitle, CardActions, CardFigure wrappers.
"""

from enum import StrEnum
from typing import Any

from fasthtml.common import A, Div

__all__ = ["CardT", "Card", "CardBody", "CardTitle", "CardActions", "CardFigure", "CardLink"]


class CardT(StrEnum):
    """Card variant types - maps to DaisyUI styling."""

    default = ""
    bordered = "card-bordered"
    compact = "card-compact"
    side = "card-side"


def Card(
    *c: Any,
    cls: str = "",
    variant: CardT = CardT.default,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Card wrapper.

    Args:
        *c: Card content (should include CardBody for proper styling)
        cls: Additional CSS classes
        variant: Card style variant
        **kwargs: Additional HTML attributes

    Example:
        Card(CardBody(H1("Title"), P("Content")))
        Card(CardBody(...), variant=CardT.bordered)
    """
    classes = ["card", "bg-base-100", "shadow-sm"]

    if variant.value:
        classes.append(variant.value)

    if cls:
        classes.append(cls)

    return Div(*c, cls=" ".join(classes), **kwargs)


def CardBody(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Card body wrapper.

    Args:
        *c: Card body content
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["card-body"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def CardTitle(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Card title wrapper.

    Args:
        *c: Title content
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["card-title"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def CardActions(*c: Any, cls: str = "", justify: str = "end", **kwargs: Any) -> Any:
    """
    DaisyUI Card actions wrapper.

    Args:
        *c: Action buttons/content
        cls: Additional CSS classes
        justify: Justify content ("start", "end", "center", "between")
        **kwargs: Additional HTML attributes
    """
    classes = ["card-actions", f"justify-{justify}"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def CardFigure(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Card figure wrapper for images.

    Args:
        *c: Figure content (typically an Img)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Figure

    classes = ["figure"]
    if cls:
        classes.append(cls)
    return Figure(*c, cls=" ".join(classes), **kwargs)


def CardLink(*c: Any, href: str, cls: str = "", **kwargs: Any) -> Any:
    """Clickable card that acts as a navigation link.

    Args:
        *c: Child elements
        href: URL to navigate to when clicked
        cls: Additional CSS classes
        **kwargs: Additional attributes passed to the A element
    """
    base_cls = (
        "block card bg-base-100 shadow-sm hover:border-primary hover:shadow-md transition-all"
    )
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return A(*c, href=href, cls=full_cls, **kwargs)
