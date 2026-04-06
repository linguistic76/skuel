"""
SKUEL Card Components (MonsterUI)
==================================

Card wrappers using MonsterUI's card system.
Keeps SKUEL's API (Card, CardBody, CardTitle, CardActions, CardFigure, CardLink).
Re-exports MonsterUI's CardT directly for variant selection.
"""

from typing import Any

from fasthtml.common import A
from monsterui.franken import CardBody as MCardBody
from monsterui.franken import CardContainer as MCardContainer
from monsterui.franken import CardFooter as MCardFooter
from monsterui.franken import CardHeader as MCardHeader
from monsterui.franken import CardT
from monsterui.franken import CardTitle as MCardTitle

__all__ = [
    "CardT",
    "Card",
    "CardBody",
    "CardHeader",
    "CardTitle",
    "CardActions",
    "CardFigure",
    "CardLink",
]


def Card(
    *c: Any,
    cls: str = "",
    variant: CardT = CardT.default,
    **kwargs: Any,
) -> Any:
    """
    Card wrapper using MonsterUI internals.

    Args:
        *c: Card content (should include CardBody for proper styling)
        cls: Additional CSS classes
        variant: Card style variant (default, primary, secondary, destructive, hover)
        **kwargs: Additional HTML attributes
    """
    cls_parts: list[Any] = [variant]
    if cls:
        cls_parts.append(cls)

    return MCardContainer(*c, cls=tuple(cls_parts), **kwargs)


def CardBody(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Card body wrapper using MonsterUI."""
    return MCardBody(*c, cls=cls, **kwargs) if cls else MCardBody(*c, **kwargs)


def CardTitle(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Card title wrapper using MonsterUI."""
    return MCardTitle(*c, cls=cls, **kwargs) if cls else MCardTitle(*c, **kwargs)


def CardActions(*c: Any, cls: str = "", justify: str = "end", **kwargs: Any) -> Any:
    """Card actions wrapper (footer area for buttons).

    Args:
        *c: Action buttons/content
        cls: Additional CSS classes
        justify: Justify content ("start", "end", "center", "between")
        **kwargs: Additional HTML attributes
    """
    classes = [f"justify-{justify}"]
    if cls:
        classes.append(cls)
    return MCardFooter(*c, cls=" ".join(classes), **kwargs)


def CardFigure(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Card figure wrapper for images.

    Args:
        *c: Figure content (typically an Img)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Figure

    classes = ["overflow-hidden rounded-t-lg"]
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
    base_cls = "block rounded-lg border bg-card text-card-foreground shadow-sm hover:border-primary hover:shadow-md transition-all"
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return A(*c, href=href, cls=full_cls, **kwargs)


def CardHeader(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Card header wrapper using MonsterUI."""
    return MCardHeader(*c, cls=cls, **kwargs) if cls else MCardHeader(*c, **kwargs)
