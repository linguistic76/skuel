"""Layout primitives that handle overflow correctly.

This module provides layout components that properly handle flex/grid overflow
issues that commonly cause text truncation bugs. The key insight is that
flex children need `min-w-0` to properly truncate text.

Key Components:
- Container: Centered content container with responsive padding
- Stack: Vertical flex container with gap
- Row: Horizontal flex container with overflow safety
- FlexItem: Flex child with proper overflow handling
- Grid: Responsive CSS grid layout
"""

from typing import Any

from fasthtml.common import Div


def Container(*children: Any, width: str = "max-w-6xl", cls: str = "", **kwargs: Any) -> Div:
    """Centered content container with responsive padding.

    Args:
        *children: Child elements
        width: Max width class (default: max-w-6xl)
        cls: Additional CSS classes to append
        **kwargs: Additional attributes passed to the Div element

    Returns:
        A Div element with centered container styling
    """
    base_cls = f"{width} mx-auto px-4 sm:px-6 lg:px-8"
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return Div(*children, cls=full_cls, **kwargs)


def Stack(*children: Any, gap: int = 4, cls: str = "", **kwargs: Any) -> Div:
    """Vertical stack (flex-col) with gap.

    Args:
        *children: Child elements
        gap: Gap between items using Tailwind gap scale (default: 4 = 1rem)
        cls: Additional CSS classes to append
        **kwargs: Additional attributes passed to the Div element

    Returns:
        A Div element with vertical flex styling
    """
    base_cls = f"flex flex-col gap-{gap}"
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return Div(*children, cls=full_cls, **kwargs)


def Row(
    *children: Any, gap: int = 4, align: str = "items-center", cls: str = "", **kwargs: Any
) -> Div:
    """Horizontal row (flex) with overflow safety.

    This component includes `min-w-0` to ensure flex children can properly
    shrink and truncate text when needed.

    Args:
        *children: Child elements
        gap: Gap between items using Tailwind gap scale (default: 4 = 1rem)
        align: Vertical alignment class (default: items-center)
        cls: Additional CSS classes to append
        **kwargs: Additional attributes passed to the Div element

    Returns:
        A Div element with horizontal flex styling
    """
    base_cls = f"flex {align} gap-{gap} min-w-0"
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return Div(*children, cls=full_cls, **kwargs)


def FlexItem(
    *children: Any,
    grow: bool = False,
    shrink: bool = True,
    cls: str = "",
    **kwargs: Any,
) -> Div:
    """Flex child with proper overflow handling.

    This is the KEY component for fixing text truncation in flex layouts.
    It includes `min-w-0 overflow-hidden` which allows the flex item to
    shrink below its content size, enabling text truncation.

    Args:
        *children: Child elements
        grow: If True, allows the item to grow to fill space (default: False)
        shrink: If True, allows the item to shrink (default: True)
        cls: Additional CSS classes to append
        **kwargs: Additional attributes passed to the Div element

    Returns:
        A Div element with flex item styling
    """
    grow_cls = "flex-grow" if grow else ""
    shrink_cls = "flex-shrink" if shrink else "flex-shrink-0"
    base_cls = f"{grow_cls} {shrink_cls} min-w-0 overflow-hidden".strip()
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return Div(*children, cls=full_cls, **kwargs)


def Grid(*children: Any, cols: int = 3, gap: int = 6, cls: str = "", **kwargs: Any) -> Div:
    """Responsive CSS grid layout.

    Mobile-first responsive grid that starts with 1 column and expands:
    - Mobile: 1 column
    - Tablet (md): 2 columns
    - Desktop (lg): specified number of columns

    Args:
        *children: Child elements (grid items)
        cols: Number of columns at lg breakpoint (default: 3)
        gap: Gap between items using Tailwind gap scale (default: 6 = 1.5rem)
        cls: Additional CSS classes to append
        **kwargs: Additional attributes passed to the Div element

    Returns:
        A Div element with responsive grid styling
    """
    base_cls = f"grid grid-cols-1 md:grid-cols-2 lg:grid-cols-{cols} gap-{gap}"
    full_cls = f"{base_cls} {cls}".strip() if cls else base_cls
    return Div(*children, cls=full_cls, **kwargs)
