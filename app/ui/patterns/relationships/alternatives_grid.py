"""AlternativesComparisonGrid Component - Side-by-Side Comparison.

Displays alternative entities in a responsive comparison table with criteria rows.
Uses HTMX lazy loading for performance.

Features:
- Responsive grid (1 col mobile, 2-4 desktop)
- Comparison criteria rows
- Highlight differences
- Action buttons per alternative
- HTMX lazy loading

Layout (2 alternatives):
┌────────────┬────────────┐
│ Alternative│ Alternative│
│ A          │ B          │
├────────────┼────────────┤
│ Timeframe  │ Timeframe  │
│ 5 years    │ 2 years    │
├────────────┼────────────┤
│ Difficulty │ Difficulty │
│ High       │ Medium     │
└────────────┴────────────┘
"""

from typing import Any

from fasthtml.common import Div, H3, Table, Tbody, Td, Th, Thead, Tr

from ui.primitives.card import Card


def AlternativesComparisonGrid(entity_uid: str, entity_type: str) -> Div:
    """Side-by-side comparison table for alternative entities.

    Args:
        entity_uid: Entity UID to get alternatives for
        entity_type: Entity type (tasks, goals, etc.)

    Returns:
        Div containing HTMX-loadable comparison grid
    """
    return Card(
        H3("Alternative Approaches", cls="text-lg font-bold mb-4"),
        # Comparison grid (HTMX loads)
        Div(
            Div("Loading alternatives...", cls="skeleton h-48"),
            id=f"alternatives-{entity_uid}",
            **{
                "hx-get": f"/api/{entity_type}/{entity_uid}/lateral/alternatives/compare",
                "hx-trigger": "load delay:300ms",  # Staggered loading
                "hx-swap": "innerHTML",
            },
        ),
        cls="bg-base-100 shadow-sm p-4",
    )


def render_alternatives_fragment(alternatives: list[dict[str, Any]]) -> Div:
    """Render alternatives as comparison table (called by HTMX endpoint).

    Args:
        alternatives: List of alternative entities with comparison data

    Returns:
        Div containing rendered comparison table
    """
    if not alternatives:
        return Div(
            "No alternatives defined.",
            cls="text-base-content/70 text-sm",
        )

    # Header row
    headers = [Th("Criteria", cls="bg-base-200")]
    for alt in alternatives:
        headers.append(
            Th(
                Div(
                    Div(alt["title"], cls="font-semibold"),
                    Div(
                        alt["entity_type"].capitalize(),
                        cls="text-xs text-base-content/60 font-normal",
                    ),
                    cls="space-y-1",
                ),
                cls="bg-base-200",
            )
        )

    # Comparison rows
    criteria = ["timeframe", "difficulty", "resources"]
    rows = []

    for criterion in criteria:
        cells = [Td(criterion.replace("_", " ").title(), cls="font-semibold")]
        for alt in alternatives:
            value = alt["comparison_data"].get(criterion, "N/A")
            cells.append(Td(value))
        rows.append(Tr(*cells))

    # Status row
    status_cells = [Td("Status", cls="font-semibold")]
    for alt in alternatives:
        status = alt.get("status", "unknown")
        status_badge_cls = "badge badge-sm"
        if status == "completed":
            status_badge_cls += " badge-success"
        elif status in {"active", "in_progress"}:
            status_badge_cls += " badge-info"
        else:
            status_badge_cls += " badge-ghost"

        status_cells.append(
            Td(Div(status.replace("_", " ").title(), cls=status_badge_cls))
        )
    rows.append(Tr(*status_cells))

    # Priority row
    priority_cells = [Td("Priority", cls="font-semibold")]
    for alt in alternatives:
        priority = alt.get("priority", "N/A")
        priority_cells.append(Td(priority.replace("_", " ").title() if priority else "N/A"))
    rows.append(Tr(*priority_cells))

    # Tradeoffs row
    tradeoff_cells = [Td("Tradeoffs", cls="font-semibold")]
    for alt in alternatives:
        tradeoffs = alt["metadata"].get("tradeoffs", "")
        tradeoff_cells.append(Td(tradeoffs or "—", cls="text-sm"))
    rows.append(Tr(*tradeoff_cells))

    # Comparison criteria row
    criteria_cells = [Td("Decision Criteria", cls="font-semibold")]
    for alt in alternatives:
        criteria_text = alt["metadata"].get("comparison_criteria", "")
        criteria_cells.append(Td(criteria_text or "—", cls="text-sm italic"))
    rows.append(Tr(*criteria_cells))

    return Div(
        Table(
            Thead(Tr(*headers)),
            Tbody(*rows),
            cls="table table-zebra w-full",
        ),
        cls="overflow-x-auto",
    )


__all__ = ["AlternativesComparisonGrid", "render_alternatives_fragment"]
