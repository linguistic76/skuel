"""Ku mastery self-assessment — dual-track Knowledge dimension (ADR-030).

Segmented mastery control (New / Familiar / Working / Fluent) whose state
is owned by the parent ``kuReading()`` Alpine component. The form POSTs to
``/explore/ku/{ku_uid}/mastery-checkin`` via HTMX and swaps the gap-card
result into ``#mastery-results``.

A Ku is SHARED/public curriculum, so check-ins persist on the ``:User`` node
keyed by Ku UID — never on the shared ``:Ku`` node. CSRF-guarded via
``skuel.js``.

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Button, Div, Form, Input, Label, P, Section, Span, Textarea

from core.models.enums import MasteryLevel
from core.models.shared.dual_track import DualTrackResult
from ui.components import Icon
from ui.dual_track_card import gap_card, render_checkin_trend

if TYPE_CHECKING:
    from fasthtml.common import FT

_RESULTS_SLOT = "mastery-results"
_MASTERY_LEVELS: list[tuple[str, str]] = [
    ("novice", "New"),
    ("familiar", "Familiar"),
    ("proficient", "Working"),
    ("mastered", "Fluent"),
]


def render_ku_mastery_section(
    ku_uid: str,
    checkins: list[dict[str, Any]],
) -> "FT":
    """Mastery self-check section for the Ku detail page (authenticated users only).

    Renders a segmented mastery control (state owned by the parent
    ``kuReading()`` Alpine component), an optional reflection textarea,
    and an HTMX-swapped results slot. On submit, POSTs to
    ``/explore/ku/{ku_uid}/mastery-checkin`` and swaps the gap card + trend.
    """
    level_buttons: list[FT] = [
        Button(
            label,
            type="button",
            role="radio",
            cls="flex-1 sm:flex-none px-3.5 py-1.5 rounded-md text-13 font-medium transition-colors",
            **{
                ":aria-checked": f"(mastery === '{level_id}').toString()",
                "@click": f"mastery = '{level_id}'",
                ":class": (
                    f"mastery === '{level_id}' "
                    "? 'bg-card text-foreground shadow-xs' "
                    ": 'text-muted-foreground hover:text-foreground'"
                ),
            },
        )
        for level_id, label in _MASTERY_LEVELS
    ]

    results_content: FT = render_checkin_trend(checkins) if checkins else Div()

    return Section(
        Div(
            "Mastery self-check",
            id="mastery-heading",
            cls="font-mono text-11 font-medium tracking-[0.09em] uppercase text-muted-foreground mb-1",
        ),
        P(
            "Rate how well you feel you know this. SKUEL compares it with how much your "
            "tracked actions show you actually applying it — the gap is the point.",
            cls="text-13 text-muted-foreground leading-relaxed mb-4 max-w-[56ch]",
        ),
        Form(
            Div(
                Div("How well do you know this?", cls="text-15 font-semibold mb-3"),
                Div(
                    *level_buttons,
                    cls="inline-flex w-full sm:w-auto rounded-lg border border-border p-1 bg-muted/40",
                    role="radiogroup",
                    **{"aria-label": "Mastery level"},
                ),
                # Hidden input keeps the form value in sync with Alpine state
                Input(type="hidden", name="level", **{":value": "mastery"}),
                Label(
                    Span(
                        "What's behind this rating?",
                        Span(" (optional)", cls="font-normal text-muted-foreground/70"),
                        cls="block text-xs font-medium text-muted-foreground mb-1.5",
                    ),
                    Textarea(
                        rows=2,
                        name="reflection",
                        placeholder="A sentence or two of context…",
                        cls=(
                            "w-full rounded-lg border border-border bg-card px-3.5 py-2.5 "
                            "text-sm leading-relaxed placeholder:text-muted-foreground/70 "
                            "focus:outline-hidden resize-none"
                        ),
                        **{"x-model": "note"},
                    ),
                    cls="block mt-4",
                ),
                Button(
                    Icon("git-branch", cls="w-4 h-4"),
                    " See my perception gap",
                    type="submit",
                    cls=(
                        "mt-4 inline-flex items-center gap-2 bg-foreground text-background "
                        "rounded-lg px-4 py-2.5 text-sm font-semibold "
                        "hover:opacity-90 focus:outline-hidden"
                    ),
                ),
                cls="border border-border rounded-xl p-5 sm:p-6 bg-card",
            ),
            hx_post=f"/explore/ku/{ku_uid}/mastery-checkin",
            hx_target=f"#{_RESULTS_SLOT}",
            hx_swap="innerHTML",
        ),
        Div(results_content, id=_RESULTS_SLOT, cls="mt-5" if checkins else ""),
        P(
            "Your ratings are saved so you can watch the gap change over time.",
            cls="text-11 text-muted-foreground/80 mt-2.5",
        ),
        cls="mb-9",
        role="region",
        **{"aria-labelledby": "mastery-heading"},
    )


def render_ku_mastery_result(
    result: DualTrackResult[MasteryLevel],
    checkins: list[dict[str, Any]],
) -> "FT":
    """HTMX fragment after a mastery self-rating: gap card + refreshed trend."""
    return Div(
        gap_card("Knowledge Mastery", result),
        render_checkin_trend(checkins),
    )
