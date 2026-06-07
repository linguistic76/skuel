"""Self Check-In UI — dual-track perception-gap (ADR-030).

Renders a single page where the user self-rates three user-level dimensions
(Productivity / Engagement / Decision Quality) and sees the gap between their
self-perception and the system-measured reality.

Server-rendered FastHTML; the form submits via an HTMX POST. The submission
persists a check-in per rated dimension to the :User node (user-level dims have
no :Entity row), so it's a mutation — POST + CSRF, not GET. ``skuel.js`` attaches
the X-CSRF-Token header to every HTMX request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import H3, H4, Div, Form, P

from core.models.enums import (
    DecisionQualityLevel,
    DualTrackDimension,
    EngagementLevel,
    ProductivityLevel,
)
from core.models.shared.dual_track import DualTrackResult
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody, CardHeader, CardTitle
from ui.dual_track_card import gap_card, level_options, render_checkin_trend
from ui.forms import LabelSelect, LabelTextArea
from ui.text import SectionTitle

if TYPE_CHECKING:
    from enum import StrEnum

# Dimension registry: (dimension, human label, enum class, prompt). The dimension's
# value doubles as the form field name and the storage key on the :User node — the
# route, the persistence callback, and the aggregator all key off the same token.
DIMENSIONS: list[tuple[DualTrackDimension, str, type[StrEnum], str]] = [
    (
        DualTrackDimension.PRODUCTIVITY,
        "Productivity",
        ProductivityLevel,
        "How productive do you feel lately?",
    ),
    (
        DualTrackDimension.ENGAGEMENT,
        "Engagement",
        EngagementLevel,
        "How engaged do you feel in your events?",
    ),
    (
        DualTrackDimension.DECISION_QUALITY,
        "Decision Quality",
        DecisionQualityLevel,
        "How good have your recent decisions felt?",
    ),
]

# Field names the form submits (one select per dimension + the shared reflection).
_INCLUDE = ",".join(f"[name='{dim.value}']" for dim, *_ in DIMENSIONS) + ",[name='reflection']"


def render_checkin_form() -> Any:
    """The self-rating form card. POSTs to /self-checkin/results (persists)."""
    selects = [
        LabelSelect(
            *level_options(enum_cls),
            label=label,
            name=dim.value,
            help_text=prompt,
            cls="space-y-2 mb-4",
        )
        for dim, label, enum_cls, prompt in DIMENSIONS
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
                hx_post="/self-checkin/results",
                hx_target="#checkin-results",
                hx_swap="innerHTML",
                hx_include=_INCLUDE,
            )
        ),
        cls="mb-6",
    )


def render_checkin_history(checkins_by_dimension: dict[str, list[dict[str, Any]]]) -> Any:
    """Per-dimension trend of stored check-ins, shown on initial page load.

    Reuses ``render_checkin_trend`` (ADR-030 gap-trending) for each dimension that
    has at least one persisted check-in. Returns nothing when the user has never
    checked in (the form alone is enough on a first visit).
    """
    blocks: list[Any] = []
    for dim, label, _enum_cls, _prompt in DIMENSIONS:
        checkins = checkins_by_dimension.get(dim.value, [])
        if not checkins:
            continue
        blocks.append(
            Div(
                H4(label, cls="font-semibold text-sm"),
                render_checkin_trend(checkins),
                cls="mb-4",
            )
        )

    if not blocks:
        return None

    return Div(
        SectionTitle("Your Check-In History"),
        *blocks,
        cls="mt-8",
    )


def render_checkin_results(
    results: list[tuple[str, str, DualTrackResult[Any]]],
    errors: list[str],
    checkins_by_dimension: dict[str, list[dict[str, Any]]],
) -> Any:
    """Render the result fragment after a submit: per dimension, a gap card plus
    its refreshed trend (which now includes the just-stored check-in)."""
    if not results and not errors:
        return Div(
            P("No dimensions could be assessed.", cls="text-muted-foreground"),
        )

    cards = [
        Div(
            gap_card(label, result),
            render_checkin_trend(checkins_by_dimension.get(dim_value, [])),
            cls="mb-4",
        )
        for dim_value, label, result in results
    ]
    error_block = (
        Div(*[P(e, cls="text-error text-sm") for e in errors], cls="mb-3") if errors else None
    )

    return Div(
        H3("Your Perception Gap", cls="font-semibold text-lg mb-3"),
        error_block,
        *cards,
        H4(
            "The gap is the point — it shows where self-perception and tracked action diverge. "
            "Your ratings are saved so you can watch the gap change over time.",
            cls="text-xs text-muted-foreground mt-4",
        ),
    )
