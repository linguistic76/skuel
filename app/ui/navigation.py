"""
SKUEL Navigation Components
==============================

Navbar, Menu, MenuItem, Dropdown, Tabs wrappers.
"""

from typing import Any

from fasthtml.common import Div

__all__ = [
    "Navbar",
    "NavbarStart",
    "NavbarCenter",
    "NavbarEnd",
    "Menu",
    "MenuItem",
    "Dropdown",
    "DropdownTrigger",
    "DropdownContent",
    "Tabs",
]


def Navbar(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Navbar wrapper.

    Args:
        *c: Navbar content (NavbarStart, NavbarCenter, NavbarEnd)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["flex items-center justify-between px-4 py-2 bg-background border-b border-border"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def NavbarStart(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Navbar start section."""
    classes = ["flex items-center gap-2"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def NavbarCenter(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Navbar center section."""
    classes = ["flex items-center gap-2"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def NavbarEnd(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """Navbar end section."""
    classes = ["flex items-center gap-2 ml-auto"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def Menu(*c: Any, cls: str = "", horizontal: bool = False, **kwargs: Any) -> Any:
    """
    Menu wrapper.

    Args:
        *c: Menu items
        cls: Additional CSS classes
        horizontal: If True, renders horizontally
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Ul

    cls_parts = ["flex flex-row gap-1"] if horizontal else ["flex flex-col gap-1"]
    if cls:
        cls_parts.append(cls)
    return Ul(*c, cls=" ".join(cls_parts), **kwargs)


def MenuItem(*c: Any, cls: str = "", _active: bool = False, **kwargs: Any) -> Any:
    """
    Menu item wrapper.

    Args:
        *c: Menu item content (typically an A tag)
        cls: Additional CSS classes
        _active: If True, marks as active item
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Li

    return Li(*c, cls=cls if cls else None, **kwargs)


def Dropdown(*c: Any, cls: str = "", end: bool = False, **kwargs: Any) -> Any:
    """
    Dropdown wrapper.

    Args:
        *c: Dropdown trigger and content
        cls: Additional CSS classes
        end: If True, aligns dropdown to end
        **kwargs: Additional HTML attributes
    """
    classes = ["relative inline-block"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def DropdownTrigger(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Dropdown trigger.

    Args:
        *c: Trigger content (typically a Button)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    return Div(*c, tabindex="0", role="button", cls=cls if cls else None, **kwargs)


def DropdownContent(
    *c: Any,
    cls: str = "",
    tabindex: str = "0",
    **kwargs: Any,
) -> Any:
    """
    Dropdown content wrapper.

    Args:
        *c: Dropdown menu items
        cls: Additional CSS classes
        tabindex: Tabindex for accessibility
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Ul

    classes = [
        "absolute",
        "z-50",
        "mt-2",
        "w-52",
        "rounded-md",
        "border",
        "border-border",
        "bg-background",
        "p-2",
        "shadow-lg",
    ]
    if cls:
        classes.append(cls)
    return Ul(*c, tabindex=tabindex, cls=" ".join(classes), **kwargs)


def Tabs(*c: Any, cls: str = "", active_tab: int = 0, **kwargs: Any) -> Any:
    """Tab container. Each argument should be a (label, content) tuple."""
    from ui.components.nav import TabContainer as _TabContainer

    return _TabContainer(*c, cls=cls, active_tab=active_tab, **kwargs)
