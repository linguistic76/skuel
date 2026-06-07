"""Self Check-In UI — dual-track perception-gap (ADR-030).

Renders a single page where the user self-rates three user-level dimensions
(Productivity / Engagement / Decision Quality) and sees the gap between their
self-perception and the system-measured reality.

Server-rendered FastHTML; the form loads results via an HTMX GET fragment
(non-mutating compute-and-display, so no CSRF / persistence in v1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import H3, H4, Div, Form, P

from core.models.enums import DecisionQualityLevel, EngagementLevel, ProductivityLevel
from core.models.shared.dual_track import DualTrackResult
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody, CardHeader, CardTitle
from ui.dual_track_card import gap_card, level_options
from ui.forms import LabelSelect, LabelTextArea

if TYPE_CHECKING:
    from enum import StrEnum

# Dimension registry: (form field, human label, enum class, prompt).
DIMENSIONS: list[tuple[str, str, type[StrEnum], str]] = [
    ("productivity", "Productivity", ProductivityLevel, "How productive do you feel lately?"),
    ("engagement", "Engagement", EngagementLevel, "How engaged do you feel in your events?"),
    (
        "decision_quality",
        "Decision Quality",
        DecisionQualityLevel,
        "How good have your recent decisions felt?",
    ),
]


def render_checkin_form() -> Any:
    """The self-rating form card."""
    selects = [
        LabelSelect(
            *level_options(enum_cls),
            label=label,
            name=field,
            help_text=prompt,
            cls="space-y-2 mb-4",
        )
        for field, label, enum_cls, prompt in DIMENSIONS
    ]

    return Card(
        CardHeader(CardTitle("Rate Yourself")),
        CardBody(
            Form(
                *selects,
                LabelTextArea(
                    "What's behind these ratings? (optional)",
                    name="reflection",
                    placeholder="A sentence or two of context…",
                    cls="space-y-2 mb-4",
                ),
                Div(
                    Button("See My Perception Gap", type="submit", variant=ButtonT.primary),
                    cls="text-right",
                ),
                hx_get="/self-checkin/results",
                hx_target="#checkin-results",
                hx_swap="innerHTML",
                hx_include=(
                    "[name='productivity'],[name='engagement'],"
                    "[name='decision_quality'],[name='reflection']"
                ),
            )
        ),
        cls="mb-6",
    )


def render_checkin_results(
    results: list[tuple[str, DualTrackResult[Any]]], errors: list[str]
) -> Any:
    """Render the result fragment: a gap card per assessed dimension."""
    if not results and not errors:
        return Div(
            P("No dimensions could be assessed.", cls="text-muted-foreground"),
        )

    cards = [gap_card(label, result) for label, result in results]
    error_block = (
        Div(*[P(e, cls="text-error text-sm") for e in errors], cls="mb-3") if errors else None
    )

    return Div(
        H3("Your Perception Gap", cls="font-semibold text-lg mb-3"),
        error_block,
        *cards,
        H4(
            "The gap is the point — it shows where self-perception and tracked action diverge.",
            cls="text-xs text-muted-foreground mt-4",
        ),
    )
