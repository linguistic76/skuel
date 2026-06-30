"""Statistics display pattern for dashboards.

Stats grids are used to display key metrics at the top of domain
dashboards. They show counts, totals, and trends in a compact format.
"""

from dataclasses import dataclass
from typing import Any

from fasthtml.common import Div, Span

from ui.components import Card, CardBody
from ui.layout import Grid


@dataclass(frozen=True)
class StatItem:
    """Typed data carrier for a single statistic in a StatsGrid."""

    label: str
    value: str | int
    change: str | None = None
    trend: str | None = None
    color: str | None = None
    href: str | None = None


def StatCard(
    label: str,
    value: str | int,
    change: str | None = None,
    trend: str | None = None,
    color: str | None = None,
    href: str | None = None,
    **kwargs: Any,
) -> Div:
    """Single statistic card.

    Args:
        label: Label describing the statistic (e.g., "Total Tasks")
        value: The main value to display
        change: Optional change text (e.g., "+5 this week")
        trend: Optional trend direction - "up", "down", or "neutral"
            Used to color the change text
        color: Optional semantic color token (e.g., "primary", "success",
            "accent", "secondary", "error"). Applied as text-{color} to the value.
        href: Optional URL — makes the entire card a clickable link.
        **kwargs: Additional attributes passed to Card

    Returns:
        A Card displaying the statistic

    Example:
        StatCard(
            label="Active Tasks",
            value=42,
            change="+5 this week",
            trend="up",
            href="/tasks?status=active",
        )
    """
    from fasthtml.common import A as Anchor

    trend_colors = {
        "up": "text-success",
        "down": "text-error",
        "neutral": "text-muted-foreground",
    }

    value_cls = (
        f"text-3xl font-bold text-{color}" if color else "text-3xl font-bold text-foreground"
    )

    content: list[Any] = [
        Span(label, cls="text-xs text-muted-foreground uppercase tracking-wide"),
        Div(
            Span(str(value), cls=value_cls),
            cls="mt-1",
        ),
    ]

    if change:
        trend_cls = (
            trend_colors.get(trend, "text-muted-foreground") if trend else "text-muted-foreground"
        )
        content.append(Span(change, cls=f"text-sm {trend_cls} mt-1 block"))

    card = Card(CardBody(*content), **kwargs)

    if href:
        return Anchor(
            card,
            href=href,
            cls="no-underline text-inherit",
            style="display: block; transition: transform 0.15s; cursor: pointer;",
        )

    return card


def IconStat(label: str, value: Any, icon: str, color_class: str = "") -> Div:
    """Compact centered stat tile with an emoji/icon, label, and value.

    Distinct from StatCard: no Card wrapper, icon-led, centered — meant to sit
    inside a caller-provided grid (e.g. ingestion dashboards, dry-run previews).

    Args:
        label: Stat label (e.g. "Total Files").
        value: The value to display (coerced to str).
        icon: Emoji or icon glyph shown above the label.
        color_class: Optional Tailwind color class applied to the value
            (e.g. "text-success").

    Returns:
        A centered Div tile.

    Example:
        IconStat("Successful", 42, "✅", "text-success")
    """
    return Div(
        Div(icon, cls="text-2xl"),
        Div(label, cls="text-sm text-muted-foreground"),
        Div(str(value), cls=f"text-2xl font-bold {color_class}".strip()),
        cls="p-4 text-center",
    )


def StatsGrid(
    stats: list[StatItem],
    cols: int = 4,
    **kwargs: Any,
) -> Div:
    """Grid of statistic cards.

    Args:
        stats: List of StatItem instances
        cols: Number of columns at large screen sizes (default: 4)
        **kwargs: Additional attributes passed to Grid

    Returns:
        A Grid containing StatCard components

    Example:
        StatsGrid([
            StatItem(label="Total", value=150),
            StatItem(label="Active", value=42, change="+5", trend="up"),
            StatItem(label="Completed", value=98),
        ])
    """
    cards = [
        StatCard(
            label=s.label,
            value=s.value,
            change=s.change,
            trend=s.trend,
            color=s.color,
            href=s.href,
        )
        for s in stats
    ]
    return Grid(*cards, cols=cols, gap=4, **kwargs)
