"""Self Check-In UI — dual-track perception-gap (ADR-030).

Renders a single page where the user self-rates three user-level dimensions
(Productivity / Engagement / Decision Quality) and sees the gap between their
self-perception and the system-measured reality.

Server-rendered FastHTML; the form loads results via an HTMX GET fragment
(non-mutating compute-and-display, so no CSRF / persistence in v1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import H3, H4, Div, Form, Li, Option, P, Span, Ul

from core.models.enums import DecisionQualityLevel, EngagementLevel, ProductivityLevel
from core.models.shared.dual_track import DualTrackResult
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody, CardHeader, CardTitle
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


def _humanize(value: str) -> str:
    """`moderately_productive` -> `Moderately Productive`."""
    return value.replace("_", " ").title()


def _level_options(enum_cls: type[StrEnum]) -> list[Any]:
    """Build <option>s for an enum, selecting the middle level as a neutral default."""
    members = list(enum_cls)
    mid = len(members) // 2
    return [
        Option(_humanize(member.value), value=member.value, selected=(i == mid))
        for i, member in enumerate(members)
    ]


def render_checkin_form() -> Any:
    """The self-rating form card."""
    selects = [
        LabelSelect(
            *_level_options(enum_cls),
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


_DIRECTION_BADGE: dict[str, tuple[str, str]] = {
    # gap_direction -> (label, tailwind color classes)
    "aligned": ("In sync", "bg-green-100 text-green-800"),
    "user_higher": ("You rate yourself higher than the data", "bg-amber-100 text-amber-800"),
    "system_higher": ("You're doing better than you think", "bg-blue-100 text-blue-800"),
}


def _gap_card(label: str, result: DualTrackResult[Any]) -> Any:
    """One perception-gap card for a single dimension."""
    badge_label, badge_cls = _DIRECTION_BADGE.get(
        result.gap_direction, ("—", "bg-gray-100 text-gray-800")
    )

    return Card(
        CardHeader(
            CardTitle(label),
            Span(badge_label, cls=f"text-xs px-2 py-1 rounded-full {badge_cls}"),
            cls="flex items-center justify-between",
        ),
        CardBody(
            Div(
                Div(
                    P("You rated", cls="text-xs text-muted-foreground"),
                    P(_humanize(str(result.user_level.value)), cls="font-semibold"),
                    cls="flex-1",
                ),
                Div(
                    P("Measured", cls="text-xs text-muted-foreground"),
                    P(_humanize(str(result.system_level.value)), cls="font-semibold"),
                    cls="flex-1",
                ),
                Div(
                    P("Gap", cls="text-xs text-muted-foreground"),
                    P(f"{result.perception_gap:.0%}", cls="font-semibold"),
                    cls="flex-1",
                ),
                cls="flex gap-4 mb-3",
            ),
            _bullet_list("What the data shows", result.system_evidence),
            _bullet_list("Insights", result.insights),
            _bullet_list("Suggestions", result.recommendations),
            cls="space-y-2",
        ),
        cls="mb-4",
    )


def _bullet_list(heading: str, items: tuple[str, ...]) -> Any:
    """Render a small labelled bullet list, or nothing when empty."""
    if not items:
        return None
    return Div(
        P(heading, cls="text-xs font-semibold text-muted-foreground mt-2"),
        Ul(*[Li(item, cls="text-sm") for item in items], cls="list-disc list-inside"),
    )


def render_checkin_results(
    results: list[tuple[str, DualTrackResult[Any]]], errors: list[str]
) -> Any:
    """Render the result fragment: a gap card per assessed dimension."""
    if not results and not errors:
        return Div(
            P("No dimensions could be assessed.", cls="text-muted-foreground"),
        )

    cards = [_gap_card(label, result) for label, result in results]
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
