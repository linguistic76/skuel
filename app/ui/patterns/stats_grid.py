"""Statistics display pattern for dashboards.

Stats grids are used to display key metrics at the top of domain
dashboards. They show counts, totals, and trends in a compact format.
"""

from dataclasses import dataclass
from typing import Any, Literal

from fasthtml.common import FT, Div, Span

from ui.components import Card, CardBody
from ui.layout import Grid

#: The colours a statistic's value may take: a semantic token that has a text
#: colour in both themes.
StatColor = Literal["primary", "success", "info", "warning", "error", "muted-foreground"]

# Each class is written out whole: the stylesheet is compiled from the class
# names found in the source, and a name assembled at render time is not one.
_VALUE_COLOR_CLASSES: dict[str, str] = {
    "primary": "text-primary",
    "success": "text-success",
    "info": "text-info",
    "warning": "text-warning",
    "error": "text-error",
    "muted-foreground": "text-muted-foreground",
}


def value_color_class(color: StatColor | None) -> str:
    """The text class for a statistic's value; the default text colour for none.

    Raises:
        ValueError: ``color`` is not a ``StatColor`` token. A palette name such
            as ``purple-600`` has no compiled class and would render as plain text.
    """
    if color is None:
        return "text-foreground"
    try:
        return _VALUE_COLOR_CLASSES[color]
    except KeyError:
        raise ValueError(
            f"{color!r} is not a stat colour; use one of {', '.join(_VALUE_COLOR_CLASSES)}"
        ) from None


@dataclass(frozen=True)
class StatItem:
    """Typed data carrier for a single statistic in a StatsGrid."""

    label: str
    value: str | int
    change: str | None = None
    trend: str | None = None
    color: StatColor | None = None
    href: str | None = None


def StatCard(
    label: str,
    value: str | int,
    change: str | None = None,
    trend: str | None = None,
    color: StatColor | None = None,
    href: str | None = None,
    **kwargs: Any,
) -> FT:
    """Single statistic card.

    Args:
        label: Label describing the statistic (e.g., "Total Tasks")
        value: The main value to display
        change: Optional change text (e.g., "+5 this week")
        trend: Optional trend direction - "up", "down", or "neutral"
            Used to color the change text
        color: Optional ``StatColor`` token ("primary", "success", "info",
            "warning", "error", "muted-foreground"), the colour of the value.
            Anything else raises ``ValueError``.
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

    value_cls = f"text-3xl font-bold {value_color_class(color)}"

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


def IconStat(label: str, value: str | int, icon: str, color_class: str = "") -> FT:
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
) -> FT:
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
