"""Stacked action card — header row (left|right) + actions row + optional extra."""

from fasthtml.common import Div, FT

from ui.cards import Card, CardBody


def StackedActionCard(
    header_left: FT,
    header_right: FT | str = "",
    actions: FT | str = "",
    extra: FT | str = "",
    header_align: str = "items-center",
    cls: str = "bg-background shadow-sm mb-2",
) -> FT:
    """Stacked card: header row (left|right) + actions row + optional extra.

    Args:
        header_left: Title/subtitle block (typically flex-1 Div).
        header_right: Badge cluster or status indicators.
        actions: Action buttons (wrapped in a right-aligned flex row).
        extra: Optional content below actions (e.g., feedback toggle).
        header_align: Vertical alignment of header row ("items-center" or "items-start").
        cls: Card-level CSS classes.
    """
    return Card(
        CardBody(
            Div(
                header_left,
                header_right,
                cls=f"flex {header_align} justify-between gap-4",
            ),
            Div(actions, cls="flex justify-end mt-3") if actions else "",
            extra or "",
            cls="p-4",
        ),
        cls=cls,
    )
