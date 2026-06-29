"""LifePath alignment dashboard."""

from typing import Any

from fasthtml.common import H3, Div, P, Span
from monsterui.franken import CardContainer as Card

from core.models.type_hints import UserUID
from ui.components import ButtonT
from ui.feedback import Progress
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink
from ui.tokens import Container


def render_alignment_dashboard(status: dict, user_uid: UserUID) -> Any:
    """Build alignment dashboard with 5-dimension breakdown."""
    alignment = status.get("alignment", {})
    dimensions = alignment.get("dimensions", {})
    recommendations = status.get("recommendations", [])

    dimension_cards = []
    for dim_name, score in dimensions.items():
        color = "text-success" if score >= 0.7 else "text-warning" if score >= 0.4 else "text-error"
        dimension_cards.append(
            Div(
                Div(
                    Span(dim_name.title(), cls="text-sm font-medium"),
                    Span(f"{int(score * 100)}%", cls=f"text-lg font-bold {color}"),
                    cls="flex justify-between items-center mb-1",
                ),
                Progress(value=int(score * 100), max=100, cls="w-full h-2"),
                cls="mb-4",
            )
        )

    rec_items = [
        Div(
            Span(rec.get("title", ""), cls="font-medium"),
            P(rec.get("description", ""), cls="text-sm text-muted-foreground"),
            cls="p-3 bg-muted rounded mb-2",
        )
        for rec in recommendations[:5]
    ]

    return Div(
        PageHeader("Life Path Alignment"),
        # Overall score
        Card(
            Div(
                Div(
                    Span(
                        f"{int(alignment.get('alignment_score', 0) * 100)}%",
                        cls="text-5xl font-bold",
                    ),
                    Span(
                        alignment.get("alignment_level", "").title(),
                        cls="text-2xl text-muted-foreground ml-4",
                    ),
                    cls="flex items-baseline mb-4",
                ),
                P(
                    "Are you LIVING what you SAID?",
                    cls="text-muted-foreground",
                ),
                cls="p-6 text-center",
            ),
            cls="mb-8",
        ),
        # Dimension breakdown
        Card(
            Div(
                H3("5-Dimension Breakdown", cls="font-semibold text-lg mb-4"),
                *dimension_cards,
                cls="p-6",
            ),
            cls="mb-8",
        ),
        # Recommendations
        Card(
            Div(
                H3("Recommendations", cls="font-semibold text-lg mb-4"),
                *rec_items if rec_items else [P("Great work! Keep it up.")],
                cls="p-6",
            ),
            cls="mb-8",
        ),
        ButtonLink("Back to Dashboard", href="/lifepath", cls=ButtonT.secondary),
        cls=f"container mx-auto px-4 py-8 {Container.NARROW}",
    )
