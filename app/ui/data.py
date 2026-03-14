"""
SKUEL Data Display Components
================================

Table, Stats (Stat, StatTitle, StatValue, StatDesc, StatFigure),
Tooltip, Divider, Avatar, AvatarGroup.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

if TYPE_CHECKING:
    from ui.buttons import ButtonT

__all__ = [
    "Table",
    "Stats",
    "Stat",
    "StatTitle",
    "StatValue",
    "StatDesc",
    "StatFigure",
    "Tooltip",
    "Divider",
    "Avatar",
    "AvatarGroup",
]


def Table(*c: Any, cls: str = "", zebra: bool = False, **kwargs: Any) -> Any:
    """
    Table wrapper.

    Args:
        *c: Table content (Thead, Tbody)
        cls: Additional CSS classes
        zebra: If True, uses zebra striping
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Table as FTTable

    classes = ["uk-table"]
    if zebra:
        classes.append("uk-table-striped")
    if cls:
        classes.append(cls)
    return FTTable(*c, cls=" ".join(classes), **kwargs)


def Tooltip(
    *c: Any,
    tip: str,
    cls: str = "",
    position: str = "top",
    variant: "ButtonT | None" = None,
    **kwargs: Any,
) -> Any:
    """
    Tooltip wrapper.

    Args:
        *c: Element to wrap with tooltip
        tip: Tooltip text
        cls: Additional CSS classes
        position: Tooltip position ("top", "bottom", "left", "right")
        variant: Optional color variant (from ui.buttons.ButtonT)
        **kwargs: Additional HTML attributes

    Example:
        Tooltip(Button("Hover me"), tip="This is a tooltip")
    """
    classes = ["tooltip", f"tooltip-{position}"]
    if variant is not None:
        classes.append(variant.value.replace("btn-", "tooltip-"))
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **{"data-tip": tip}, **kwargs)


def Divider(
    text: str = "",
    cls: str = "",
    horizontal: bool = True,
    **kwargs: Any,
) -> Any:
    """
    Divider.

    Args:
        text: Optional text to show in divider
        cls: Additional CSS classes
        horizontal: If True, horizontal divider; else vertical
        **kwargs: Additional HTML attributes
    """
    if horizontal:
        base_classes = ["border-t border-border my-4"]
    else:
        base_classes = ["border-l border-border mx-4 h-full"]
    if text:
        base_classes.append("flex items-center gap-2 text-muted-foreground text-sm")
    if cls:
        base_classes.append(cls)
    return Div(text if text else None, cls=" ".join(base_classes), **kwargs)


def Avatar(*c: Any, cls: str = "", online: bool | None = None, **kwargs: Any) -> Any:
    """
    Avatar wrapper.

    Args:
        *c: Avatar content (typically an Img in a Div)
        cls: Additional CSS classes
        online: If True shows online indicator, False shows offline, None shows nothing
        **kwargs: Additional HTML attributes
    """
    classes = ["avatar"]
    if online is True:
        classes.append("online")
    elif online is False:
        classes.append("offline")
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def AvatarGroup(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Avatar group wrapper.

    Args:
        *c: Avatar elements
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["avatar-group", "-space-x-6", "rtl:space-x-reverse"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def Stats(*c: Any, cls: str = "", vertical: bool = False, **kwargs: Any) -> Any:
    """
    Stats wrapper.

    Args:
        *c: Stat items
        cls: Additional CSS classes
        vertical: If True, displays stats vertically
        **kwargs: Additional HTML attributes
    """
    classes = ["stats", "shadow"]
    if vertical:
        classes.append("stats-vertical")
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def Stat(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Stat item wrapper.

    Args:
        *c: Stat content (StatTitle, StatValue, StatDesc, etc.)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["stat"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def StatTitle(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Stat title."""
    classes = ["stat-title"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def StatValue(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Stat value."""
    classes = ["stat-value"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def StatDesc(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Stat description."""
    classes = ["stat-desc"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def StatFigure(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Stat figure (for icons)."""
    classes = ["stat-figure"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)
