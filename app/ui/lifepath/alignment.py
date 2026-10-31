"""LifePath alignment dashboard.

Two measures share the page, and neither is shown as the other. The five-dimension
alignment (score, radar, bars) is the page's one alignment figure. Below it, the
path's steps banded by how lived they are, and which kinds of activity carry the
path's knowledge — both from the learner's PERSONAL substance over the whole path,
shown as counts and shares, never as a second alignment percentage.
"""

from fasthtml.common import FT, H3, H4, A, Canvas, Div, Li, P, Span, Ul

from core.models.enums import AlignmentLevel, SubstanceBand
from core.ports.query_types import (
    LifePathStatus,
    LifePathStepSubstanceRow,
    LifePathSubstanceAlignment,
)
from ui.components import ButtonT, Card
from ui.feedback import Badge, BadgeT, Progress
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink
from ui.tokens import Container

#: How many of the least-lived steps the page lists (the service reports up to ten).
_LEAST_LIVED_SHOWN = 5


def render_alignment_dashboard(status: LifePathStatus, lived: FT) -> FT:
    """Build the alignment dashboard: the 5-dimension breakdown, then ``lived``.

    Args:
        status: The learner's Life Path status (designated, with its alignment).
        lived: The steps and practice cards (``render_lived_cards``), or the
            banner of their failed read — the five-dimension half stands either way.
    """
    alignment = status.get("alignment") or {}
    dimensions = alignment.get("dimensions")
    recommendations = status.get("recommendations", [])
    level = AlignmentLevel(alignment.get("alignment_level", AlignmentLevel.UNKNOWN))
    scores = (
        [
            ("Knowledge", dimensions["knowledge"]),
            ("Activity", dimensions["activity"]),
            ("Goal", dimensions["goal"]),
            ("Principle", dimensions["principle"]),
            ("Momentum", dimensions["momentum"]),
        ]
        if dimensions
        else []
    )

    dimension_cards = []
    for dim_name, score in scores:
        color = "text-success" if score >= 0.7 else "text-warning" if score >= 0.4 else "text-error"
        dimension_cards.append(
            Div(
                Div(
                    Span(dim_name, cls="text-sm font-medium"),
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
            cls="p-3 bg-muted rounded-sm mb-2",
        )
        for rec in recommendations[:5]
    ]

    return Div(
        PageHeader("Life Path Alignment", subtitle=alignment.get("life_path_title")),
        # The header spaces itself (mb-8); the cards below it are gap-spaced.
        Div(
            # Overall score
            Card(
                Div(
                    Div(
                        Span(
                            f"{int(alignment.get('alignment_score', 0) * 100)}%",
                            cls="text-5xl font-bold",
                        ),
                        Span(level.get_label(), cls="text-2xl text-muted-foreground ml-4"),
                        cls="flex items-baseline mb-4",
                    ),
                    P(
                        "Are you LIVING what you SAID?",
                        cls="text-muted-foreground",
                    ),
                    cls="p-6 text-center",
                ),
            ),
            # Dimension breakdown — radar chart + per-dimension bars
            Card(
                Div(
                    H3("5-Dimension Breakdown", cls="font-semibold text-lg mb-4"),
                    _alignment_radar(),
                    *dimension_cards,
                    cls="p-6",
                ),
            ),
            lived,
            # Recommendations
            Card(
                Div(
                    H3("Recommendations", cls="font-semibold text-lg mb-4"),
                    *rec_items if rec_items else [P("Great work! Keep it up.")],
                    cls="p-6",
                ),
            ),
            Div(ButtonLink("Back to Dashboard", href="/lifepath", cls=ButtonT.secondary)),
            cls="flex flex-col gap-8",
        ),
        cls=f"container mx-auto {Container.NARROW}",
    )


def render_lived_cards(lived: LifePathSubstanceAlignment) -> FT:
    """The path's steps by how lived they are, and where that practice comes from.

    ``lived`` is ``AnalyticsService.calculate_life_path_alignment``'s payload: the
    learner's personal substance over every step of the designated path. Its
    ``alignment_score`` (the steps' mean) is deliberately not shown — the band
    counts say the same thing without reading as a second alignment figure.
    """
    return Div(_steps_card(lived), _practice_card(lived), cls="flex flex-col gap-8")


def _steps_card(lived: LifePathSubstanceAlignment) -> FT:
    """The band counts over the path's steps, then the least-lived steps."""
    count = lived["knowledge_count"]  # PathSteps, despite the key's name
    if not count:
        body: tuple[FT, ...] = (P(lived.get("message", "Your Life Path has no steps yet.")),)
    else:
        band_counts = {
            SubstanceBand.EMBODIED: lived["embodied_knowledge"],
            SubstanceBand.PRACTICED: lived["practiced_knowledge"],
            SubstanceBand.APPLIED: lived["applied_knowledge"],
            SubstanceBand.THEORETICAL: lived["theoretical_knowledge"],
        }
        bands = Div(
            *[_band_cell(band, band_counts[band]) for band in SubstanceBand],
            cls="grid grid-cols-2 sm:grid-cols-4 gap-3",
        )
        gaps = lived["gaps"][:_LEAST_LIVED_SHOWN]
        least_lived = (
            Div(
                H4("Least lived", cls="font-medium mb-1"),
                Ul(*[_least_lived_row(gap) for gap in gaps], cls="divide-y divide-border"),
            )
            if gaps
            else P("Every step of your path is in your life.", cls="text-success")
        )
        body = (bands, least_lived)
    subtitle = (
        f"{count} {'step' if count == 1 else 'steps'}, by how much of each shows up in what you do."
        if count
        else None
    )
    return Card(
        Div(
            _card_heading("Your path's steps", subtitle),
            *body,
            cls="p-6 flex flex-col gap-4",
        ),
    )


def _card_heading(title: str, subtitle: str | None) -> FT:
    """A card's title, with its subtitle tucked under it rather than gap-spaced."""
    return Div(
        H3(title, cls="font-semibold text-lg"),
        P(subtitle, cls="text-sm text-muted-foreground mt-1") if subtitle else None,
    )


def _band_cell(band: SubstanceBand, count: int) -> FT:
    return Div(
        Span(str(count), cls="text-2xl font-bold tabular-nums"),
        Span(band.get_label(), cls="text-sm font-medium"),
        Span(band.get_description(), cls="text-xs text-muted-foreground"),
        cls="flex flex-col gap-0.5 p-3 bg-muted rounded-sm",
    )


def _least_lived_row(gap: LifePathStepSubstanceRow) -> FT:
    """One step under the review threshold, linking to the step itself.

    The row's ``ku_uid`` is a PathStep uid (the service's historical key spelling).
    """
    band = gap["band"]
    return Li(
        A(
            gap["title"],
            href=f"/explore/ps/{gap['ku_uid']}",
            cls="font-medium text-primary hover:underline",
        ),
        Badge(band.get_label(), variant=BadgeT.neutral),
        cls="flex items-center justify-between gap-3 py-2",
    )


def _practice_card(lived: LifePathSubstanceAlignment) -> FT:
    """Each channel's share of the learner's substance on the path."""
    shares = lived["domain_contributions"]
    if any(share > 0 for share in shares.values()):
        body = Div(
            *[_share_row(channel, share) for channel, share in shares.items()],
            cls="flex flex-col gap-4",
        )
    else:
        body = P("None of your activity touches your path's knowledge yet.")
    return Card(
        Div(
            _card_heading(
                "Where your practice comes from",
                "Which kinds of activity carry your path's knowledge.",
            ),
            body,
            cls="p-6 flex flex-col gap-4",
        ),
    )


def _share_row(channel: str, share: float) -> FT:
    percent = int(share * 100)
    return Div(
        Div(
            Span(channel.title(), cls="text-sm font-medium"),
            Span(
                f"{percent}%" if share > 0 else "not yet",
                cls="text-sm text-muted-foreground tabular-nums",
            ),
            cls="flex justify-between items-center mb-1",
        ),
        Progress(value=percent, max=100, cls="w-full h-2"),
    )


def _alignment_radar() -> FT:
    """Radar chart of the 5 alignment dimensions (chartVis Alpine component).

    The canvas fills its parent, which caps and centres it. Chart.js sizes the
    canvas to the parent's width minus the canvas's own margins, so a margin on
    the canvas (``mx-auto``) would hold it at its starting width.
    """
    return Div(
        Canvas(
            **{
                "x-ref": "canvas",
                "width": "360",
                "height": "360",
                "class": "max-w-full",
            }
        ),
        Div(
            "Loading chart...",
            cls="text-center text-muted-foreground py-8",
            **{"x-show": "loading"},
        ),
        Div(
            Span("Error: ", cls="font-bold"),
            Span(**{"x-text": "error"}),
            cls="text-error text-center py-8",
            **{"x-show": "error"},
        ),
        cls="mb-6 max-w-lg mx-auto",
        **{"x-data": "chartVis('/api/lifepath/alignment/chart')"},
    )
