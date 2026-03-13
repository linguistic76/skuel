"""
SKUEL Layout Components
========================

Size enum and layout helper components. Re-exports MonsterUI layout primitives
where possible, keeps SKUEL adapters for gap/align parameters.

MonsterUI provides: DivFullySpaced, DivCentered, DivHStacked, DivVStacked, Grid, Center.
SKUEL keeps thin adapters for: DivHStacked/DivVStacked (gap=int), Grid (cols/responsive).
"""

from enum import StrEnum
from typing import Any

from fasthtml.common import Div
from monsterui.franken import (
    Center,
    DivCentered,
    DivFullySpaced,
)

__all__ = [
    "Size",
    "DivHStacked",
    "DivVStacked",
    "DivFullySpaced",
    "DivCentered",
    "Center",
    "FlexItem",
    "Grid",
    "Row",
    "Stack",
    "Container",
]


class Size(StrEnum):
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
    Horizontal flex stack with configurable gap.

    SKUEL adapter: MonsterUI's DivHStacked doesn't accept gap=int,
    so we keep this wrapper to translate gap/align to Tailwind classes.

    Args:
        *c: Child elements
        gap: Gap size (Tailwind spacing scale)
        cls: Additional CSS classes
        align: Align items ("start", "center", "end", "stretch", "baseline")
        **kwargs: Additional HTML attributes
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
    Vertical flex stack with configurable gap.

    SKUEL adapter: MonsterUI's DivVStacked doesn't accept gap=int,
    so we keep this wrapper to translate gap/align to Tailwind classes.

    Args:
        *c: Child elements
        gap: Gap size (Tailwind spacing scale)
        cls: Additional CSS classes
        align: Align items ("start", "center", "end", "stretch")
        **kwargs: Additional HTML attributes
    """
    classes = ["flex", "flex-col", f"gap-{gap}", f"items-{align}"]
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
    CSS Grid wrapper with responsive breakpoints.

    SKUEL adapter: translates cols/responsive to Tailwind grid classes.
    MonsterUI's Grid auto-detects columns from child count; SKUEL needs explicit control.

    Args:
        *c: Grid items
        cols: Number of columns
        gap: Gap size (Tailwind spacing scale)
        cls: Additional CSS classes
        responsive: If True, adds responsive breakpoints
        **kwargs: Additional HTML attributes
    """
    classes = ["grid", f"gap-{gap}"]

    if responsive:
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


def Stack(*c: Any, gap: int = 4, cls: str = "", **kwargs: Any) -> Any:
    """Vertical flex stack with gap.

    Args:
        *c: Child elements
        gap: Gap between items using Tailwind gap scale (default: 4 = 1rem)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    base_cls = f"flex flex-col gap-{gap}"
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return Div(*c, cls=full_cls, **kwargs)


def Row(*c: Any, gap: int = 4, align: str = "items-center", cls: str = "", **kwargs: Any) -> Any:
    """Horizontal flex row with overflow safety.

    Includes ``min-w-0`` so flex children can properly shrink and truncate text.

    Args:
        *c: Child elements
        gap: Gap between items using Tailwind gap scale (default: 4 = 1rem)
        align: Vertical alignment class (default: items-center)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    base_cls = f"flex {align} gap-{gap} min-w-0"
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return Div(*c, cls=full_cls, **kwargs)


def FlexItem(
    *c: Any,
    grow: bool = False,
    shrink: bool = True,
    cls: str = "",
    **kwargs: Any,
) -> Any:
    """Flex child with proper overflow handling.

    Includes ``min-w-0 overflow-hidden`` which allows the flex item to
    shrink below its content size, enabling text truncation.

    Args:
        *c: Child elements
        grow: If True, allows the item to grow to fill space (default: False)
        shrink: If True, allows the item to shrink (default: True)
        cls: Additional CSS classes
        **kwargs: Additional HTML attributes
    """
    grow_cls = "flex-grow" if grow else ""
    shrink_cls = "flex-shrink" if shrink else "flex-shrink-0"
    base_cls = f"{grow_cls} {shrink_cls} min-w-0 overflow-hidden".strip()
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return Div(*c, cls=full_cls, **kwargs)
