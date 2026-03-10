"""Statistics display pattern for dashboards.

Stats grids are used to display key metrics at the top of domain
dashboards. They show counts, totals, and trends in a compact format.
"""

from typing import Any

from fasthtml.common import Div, Span

from ui.cards import Card, CardBody, CardT
from ui.layout import Grid
from ui.text import Caption


def StatCard(
    label: str,
    value: str | int,
    change: str | None = None,
    trend: str | None = None,
    **kwargs: Any,
) -> Div:
    """Single statistic card.

    Args:
        label: Label describing the statistic (e.g., "Total Tasks")
        value: The main value to display
        change: Optional change text (e.g., "+5 this week")
        trend: Optional trend direction - "up", "down", or "neutral"
            Used to color the change text
        **kwargs: Additional attributes passed to Card

    Returns:
        A Card displaying the statistic

    Example:
        StatCard(
            label="Active Tasks",
            value=42,
            change="+5 this week",
            trend="up",
        )
    """
    trend_colors = {
        "up": "text-success",
        "down": "text-error",
        "neutral": "text-base-content/60",
    }

    content = [
        Caption(label),
        Div(
            Span(str(value), cls="text-3xl font-bold text-base-content"),
            cls="mt-1",
        ),
    ]

    if change:
        trend_cls = trend_colors.get(trend, "text-base-content/60")
        content.append(Span(change, cls=f"text-sm {trend_cls} mt-1 block"))

    return Card(CardBody(*content), variant=CardT.compact, **kwargs)


def StatsGrid(
    stats: list[dict[str, Any]],
    cols: int = 4,
    **kwargs: Any,
) -> Div:
    """Grid of statistic cards.

    Args:
        stats: List of stat dictionaries, each containing:
            - label: (required) Label for the stat
            - value: (required) Value to display
            - change: (optional) Change text
            - trend: (optional) Trend direction
        cols: Number of columns at large screen sizes (default: 4)
        **kwargs: Additional attributes passed to Grid

    Returns:
        A Grid containing StatCard components

    Example:
        StatsGrid([
            {"label": "Total", "value": 150},
            {"label": "Active", "value": 42, "change": "+5", "trend": "up"},
            {"label": "Completed", "value": 98},
            {"label": "Overdue", "value": 10, "change": "+2", "trend": "down"},
        ])
    """
    cards = [
        StatCard(
            label=s.get("label", ""),
            value=s.get("value", 0),
            change=s.get("change"),
            trend=s.get("trend"),
        )
        for s in stats
    ]
    return Grid(*cards, cols=cols, gap=4, **kwargs)
