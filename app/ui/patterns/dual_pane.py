"""Dual-pane layout component — responsive side-by-side or stacked.

Desktop / tablet landscape: two columns side by side.
Phone / tablet portrait: stacked vertically.

Usage:
    from ui.patterns.dual_pane import DualPaneLayout

    DualPaneLayout(
        left=Div("Submissions pane"),
        right=Div("Reports pane"),
    )
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import Div


def DualPaneLayout(
    left: Any,
    right: Any,
    breakpoint: str = "md",
    gap: str = "6",
) -> Div:
    """Responsive dual-pane layout.

    Args:
        left: Left pane content (top when stacked).
        right: Right pane content (bottom when stacked).
        breakpoint: Tailwind breakpoint for side-by-side ("sm", "md", "lg").
        gap: Tailwind gap size between panes.

    Returns:
        Grid container that stacks below breakpoint, splits above.
    """
    return Div(
        left,
        right,
        cls=f"grid grid-cols-1 {breakpoint}:grid-cols-2 gap-{gap}",
    )
