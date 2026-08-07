"""
SKUEL Layout Components
========================

Size enum and layout helper components. Pure Tailwind — no MonsterUI dependency.
"""

from enum import StrEnum
from typing import Any

from fasthtml.common import Div

from ui.components._util import _cls
from ui.components.layout import Center, DivCentered, DivFullySpaced

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

    Wraps Tailwind flex-row with configurable gap/align as named kwargs.

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

    Wraps Tailwind flex-col with configurable gap/align as named kwargs.

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


# Responsive column breakpoints: mobile-first, 1 col → N cols at wider viewports.
_RESPONSIVE_COLS: dict[int, str] = {
    1: "grid-cols-1",
    2: "grid-cols-1 sm:grid-cols-2",
    3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
    4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
    5: "grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5",
    6: "grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-6",
}


def Grid(
    *c: Any,
    cols: int = 1,
    gap: int = 4,
    cls: str = "",
    responsive: bool = True,
    **kwargs: Any,
) -> Any:
    """CSS Grid container.

    Args:
        *c: Grid items
        cols: Number of columns (max columns when responsive=True)
        gap: Gap size (Tailwind spacing scale)
        cls: Additional CSS classes
        responsive: If True, uses mobile-first breakpoints (1 col → cols at wider viewports)
        **kwargs: Additional HTML attributes
    """
    if responsive:
        col_cls = _RESPONSIVE_COLS.get(cols, f"grid-cols-1 sm:grid-cols-2 lg:grid-cols-{cols}")
    else:
        col_cls = f"grid-cols-{cols}"
    return Div(*c, cls=_cls(f"grid {col_cls} gap-{gap}", cls), **kwargs)


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
    grow_cls = "grow" if grow else ""
    shrink_cls = "shrink" if shrink else "shrink-0"
    base_cls = f"{grow_cls} {shrink_cls} min-w-0 overflow-hidden".strip()
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return Div(*c, cls=full_cls, **kwargs)
