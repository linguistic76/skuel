"""Ku mastery self-assessment — dual-track Knowledge dimension (ADR-030).

The Knowledge-domain surface of the dual-track perception gap: on the Ku detail
page (``/explore/ku/{uid}``) a logged-in user rates how well they feel they've
*mastered* this Knowledge Unit (``MasteryLevel``) and sees it against the
system-measured **substance score** — how much they've actually applied the Ku
across their life. The gap is the point.

A Ku is SHARED/public curriculum, so (unlike Goals/Habits/Principles) the
check-in is per-(user, Ku) and persists on the ``:User`` node keyed by the Ku
uid — never on the shared ``:Ku`` node. The form POSTs (mutation: persists a
check-in), CSRF-guarded; ``skuel.js`` attaches the X-CSRF-Token header.

Reuses the shared ``ui/dual_track_card.py`` primitives (``level_options``,
``gap_card``, ``render_checkin_trend``) so the Knowledge surface matches the
activity dual-track surfaces.
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import H4, Div, Form, P

from core.models.enums import MasteryLevel
from core.models.shared.dual_track import DualTrackResult
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody, CardHeader, CardTitle
from ui.dual_track_card import gap_card, level_options, render_checkin_trend
from ui.forms import LabelSelect, LabelTextArea
from ui.text import SectionTitle

_RESULTS_SLOT = "ku-mastery-results"
_PROMPT = "How well have you mastered this knowledge?"


def render_ku_mastery_section(
    ku_uid: str,
    checkins: list[dict[str, Any]],
) -> Any:
    """Self-assessment section for the Ku detail page (authenticated users).

    Renders the self-rate form (mastery select + reflection), an empty results
    slot seeded with the current trend, and saves-over-time copy. On submit the
    form POSTs to ``/explore/ku/{ku_uid}/mastery-checkin`` which computes +
    persists the check-in and swaps the gap card + refreshed trend into the slot.

    Pure presentation — ``checkins`` is the user's stored knowledge check-in log
    for this Ku (``User.knowledge_checkins[ku_uid]``); the route supplies it.
    """
    return Div(
        SectionTitle("Mastery Self-Check"),
        P(
            "Rate how well you feel you've mastered this, then see it against how "
            "much your tracked actions show you actually applying it. The gap is the "
            "point.",
            cls="text-sm text-muted-foreground mb-3",
        ),
        Card(
            CardHeader(CardTitle(_PROMPT)),
            CardBody(
                Form(
                    LabelSelect(
                        *level_options(MasteryLevel),
                        label="Mastery",
                        name="level",
                        help_text=_PROMPT,
                        cls="space-y-2 mb-4",
                    ),
                    LabelTextArea(
                        "What's behind this rating? (optional)",
                        name="reflection",
                        placeholder="A sentence or two of context…",
                        cls="space-y-2 mb-4",
                    ),
                    Div(
                        Button(
                            "See My Perception Gap",
                            type="submit",
                            variant=ButtonT.primary,
                        ),
                        cls="text-right",
                    ),
                    hx_post=f"/explore/ku/{ku_uid}/mastery-checkin",
                    hx_target=f"#{_RESULTS_SLOT}",
                    hx_swap="innerHTML",
                    hx_include="[name='level'],[name='reflection']",
                )
            ),
            cls="mb-4",
        ),
        Div(render_checkin_trend(checkins), id=_RESULTS_SLOT),
        H4(
            "Your ratings are saved so you can watch the gap change over time.",
            cls="text-xs text-muted-foreground mt-2",
        ),
        cls="mt-8",
    )


def render_ku_mastery_result(
    result: DualTrackResult[MasteryLevel],
    checkins: list[dict[str, Any]],
) -> Any:
    """HTMX fragment after a mastery self-rating: the gap card + refreshed trend
    (which now includes the just-stored check-in)."""
    return Div(
        gap_card("Knowledge Mastery", result),
        render_checkin_trend(checkins),
    )
