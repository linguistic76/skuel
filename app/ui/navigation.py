"""
SKUEL DaisyUI Navigation Components
================================

Navbar, Menu, MenuItem, Dropdown, DropdownTrigger, DropdownContent, Tabs, Tab.
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
    "Tab",
]


def Navbar(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Navbar wrapper.

    Args:
        *c: Navbar content (NavbarStart, NavbarCenter, NavbarEnd)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["navbar", "bg-base-100"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def NavbarStart(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """DaisyUI Navbar start section."""
    classes = ["navbar-start"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def NavbarCenter(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """DaisyUI Navbar center section."""
    classes = ["navbar-center"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def NavbarEnd(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """DaisyUI Navbar end section."""
    classes = ["navbar-end"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def Menu(*c: Any, cls: str = "", horizontal: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Menu wrapper.

    Args:
        *c: Menu items
        cls: Additional CSS classes
        horizontal: If True, renders horizontally
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Ul

    classes = ["menu"]
    if horizontal:
        classes.append("menu-horizontal")
    if cls:
        classes.append(cls)
    return Ul(*c, cls=" ".join(classes), **kwargs)


def MenuItem(*c: Any, cls: str = "", _active: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Menu item wrapper.

    Args:
        *c: Menu item content (typically an A tag)
        cls: Additional CSS classes
        _active: If True, marks as active item (currently unused - active class handled by caller)
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Li

    # The active class goes on the A element inside, not the Li
    return Li(*c, cls=cls if cls else None, **kwargs)


def Dropdown(*c: Any, cls: str = "", end: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Dropdown wrapper.

    Args:
        *c: Dropdown trigger and content
        cls: Additional CSS classes
        end: If True, aligns dropdown to end
        **kwargs: Additional HTML attributes

    Example:
        Dropdown(
            DropdownTrigger(Button("Options")),
            DropdownContent(
                MenuItem(A("Edit")),
                MenuItem(A("Delete")),
            )
        )
    """
    classes = ["dropdown"]
    if end:
        classes.append("dropdown-end")
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def DropdownTrigger(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    DaisyUI Dropdown trigger (use tabindex for accessibility).

    Args:
        *c: Trigger content (typically a Button)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = []
    if cls:
        classes.append(cls)
    return Div(
        *c, tabindex="0", role="button", cls=" ".join(classes) if classes else None, **kwargs
    )


def DropdownContent(
    *c: Any,
    cls: str = "",
    tabindex: str = "0",
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Dropdown content wrapper.

    Args:
        *c: Dropdown menu items
        cls: Additional CSS classes
        tabindex: Tabindex for accessibility
        **kwargs: Additional HTML attributes
    """
    from fasthtml.common import Ul

    classes = [
        "dropdown-content",
        "menu",
        "bg-base-100",
        "rounded-box",
        "shadow",
        "z-[1]",
        "w-52",
        "p-2",
    ]
    if cls:
        classes.append(cls)
    return Ul(*c, tabindex=tabindex, cls=" ".join(classes), **kwargs)


def Tabs(*c: Any, cls: str = "", boxed: bool = False, lifted: bool = False, **kwargs: Any) -> Any:
    """
    DaisyUI Tabs wrapper.

    Args:
        *c: Tab items
        cls: Additional CSS classes
        boxed: If True, uses boxed style
        lifted: If True, uses lifted style
        **kwargs: Additional HTML attributes
    """
    classes = ["tabs"]
    if boxed:
        classes.append("tabs-boxed")
    if lifted:
        classes.append("tabs-lifted")
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), role="tablist", **kwargs)


def Tab(
    *c: Any,
    cls: str = "",
    active: bool = False,
    disabled: bool = False,
    **kwargs: Any,
) -> Any:
    """
    DaisyUI Tab item with WCAG 2.1 Level AA compliance.

    Args:
        *c: Tab content
        cls: Additional CSS classes
        active: If True, marks as active tab
        disabled: If True, disables the tab
        **kwargs: Additional HTML attributes (aria-controls, etc.)

    Note:
        For full accessibility, use with Alpine.js accessibleTabs component:
        - Manages aria-selected toggling
        - Handles tabindex (0 for active, -1 for inactive)
        - Provides arrow key navigation
    """
    from fasthtml.common import A

    classes = ["tab"]
    if active:
        classes.append("tab-active")
    if disabled:
        classes.append("tab-disabled")
    if cls:
        classes.append(cls)

    # WCAG 2.1 Level AA: Add ARIA attributes for accessibility
    # role="tab" identifies this as a tab control
    # aria-selected indicates current selection state
    # tabindex controls keyboard focus (0 for active, -1 for inactive)
    attrs = {
        "cls": " ".join(classes),
        "role": "tab",
        "aria_selected": "true" if active else "false",
        "tabindex": 0 if active else -1,
    }

    # Merge with user-provided kwargs (allows overriding)
    attrs.update(kwargs)

    return A(*c, **attrs)
