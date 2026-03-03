"""
SKUEL DaisyUI Layout Components
================================

Size enum and layout helper components (DivHStacked, DivVStacked, etc.).

Size lives here because it is consumed by buttons, forms, badges, and loading
components — a single canonical location avoids circular imports.
"""

from enum import Enum
from typing import Any

from fasthtml.common import Div

__all__ = [
    "Size",
    "DivHStacked",
    "DivVStacked",
    "DivFullySpaced",
    "DivCentered",
    "Grid",
    "Container",
]


class Size(str, Enum):
    """Component size options."""

    xs = "xs"
    sm = "sm"
    md = "md"
    lg = "lg"
    xl = "xl"


def DivHStacked(
    *c: Any,
    gap: int = 2,
    cls: str = "",
    align: str = "center",
    **kwargs: Any,
) -> Any:
    """
    Horizontal flex stack.

    Args:
        *c: Child elements
        gap: Gap size (Tailwind spacing scale)
        cls: Additional CSS classes
        align: Align items ("start", "center", "end", "stretch", "baseline")
        **kwargs: Additional HTML attributes

    Example:
        DivHStacked(Icon("check"), Span("Success"), gap=2)
    """
    classes = ["flex", "flex-row", f"gap-{gap}", f"items-{align}"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def DivVStacked(
    *c: Any,
    gap: int = 2,
    cls: str = "",
    align: str = "stretch",
    **kwargs: Any,
) -> Any:
    """
    Vertical flex stack.

    Args:
        *c: Child elements
        gap: Gap size (Tailwind spacing scale)
        cls: Additional CSS classes
        align: Align items ("start", "center", "end", "stretch")
        **kwargs: Additional HTML attributes

    Example:
        DivVStacked(H1("Title"), P("Description"), gap=4)
    """
    classes = ["flex", "flex-col", f"gap-{gap}", f"items-{align}"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def DivFullySpaced(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Space-between flex layout.

    Args:
        *c: Child elements (typically 2)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes

    Example:
        DivFullySpaced(Span("Left"), Span("Right"))
    """
    classes = ["flex", "justify-between", "items-center"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def DivCentered(*c: Any, cls: str = "", **kwargs: Any) -> Any:
    """
    Centered flex layout (both axes).

    Args:
        *c: Child elements
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    classes = ["flex", "justify-center", "items-center"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)


def Grid(
    *c: Any,
    cols: int = 1,
    gap: int = 4,
    cls: str = "",
    responsive: bool = True,
    **kwargs: Any,
) -> Any:
    """
    CSS Grid wrapper.

    Args:
        *c: Grid items
        cols: Number of columns
        gap: Gap size (Tailwind spacing scale)
        cls: Additional CSS classes
        responsive: If True, adds responsive breakpoints
        **kwargs: Additional HTML attributes

    Example:
        Grid(Card(...), Card(...), Card(...), cols=3, gap=4)
    """
    classes = ["grid", f"gap-{gap}"]

    if responsive:
        # Responsive grid: 1 col on mobile, 2 on sm, cols on md+
        if cols == 2:
            classes.append("grid-cols-1 sm:grid-cols-2")
        elif cols == 3:
            classes.append("grid-cols-1 sm:grid-cols-2 md:grid-cols-3")
        elif cols == 4:
            classes.append("grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4")
        else:
            classes.append(f"grid-cols-{cols}")
    else:
        classes.append(f"grid-cols-{cols}")

    if cls:
        classes.append(cls)

    return Div(*c, cls=" ".join(classes), **kwargs)


def Container(*c: Any, cls: str = "", size: str = "7xl", **kwargs: Any) -> Any:
    """
    Centered container with max-width.

    Args:
        *c: Container content
        cls: Additional CSS classes
        size: Max width size (sm, md, lg, xl, 2xl, 3xl, 4xl, 5xl, 6xl, 7xl)
        **kwargs: Additional HTML attributes
    """
    classes = ["container", "mx-auto", "px-4", f"max-w-{size}"]
    if cls:
        classes.append(cls)
    return Div(*c, cls=" ".join(classes), **kwargs)
