"""Dual-track perception-gap card — shared UI (ADR-030).

Shared building blocks for the dual-track gap surface: the self-rate form, the
gap card (you-rated vs measured + insights), and a simple trend of recent
check-ins. Used by BOTH the user-level Self Check-In page
(``ui/self_checkin.py``) and the per-entity self-assessment sections on the
Goal / Habit / Principle detail pages.

Server-rendered FastHTML; the per-entity self-rate form submits via an HTMX POST
(it persists a check-in server-side via the dual-track store_callback, so it's a
mutation — POST + CSRF, not GET).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import H4, Div, Form, Li, Option, P, Span, Ul
from monsterui.franken import CardBody, CardHeader, CardTitle
from monsterui.franken import CardContainer as Card

from core.constants import DualTrackCheckin
from core.models.shared.dual_track import DualTrackResult
from ui.components import Button, ButtonT
from ui.forms import LabelSelect, LabelTextArea
from ui.primitives import section_label

if TYPE_CHECKING:
    from enum import StrEnum

# gap_direction -> (label, tailwind color classes). Public so other surfaces can
# reuse the same vocabulary for the perception gap.
DIRECTION_BADGE: dict[str, tuple[str, str]] = {
    "aligned": ("In sync", "bg-green-100 text-green-800"),
    "user_higher": ("You rate yourself higher than the data", "bg-amber-100 text-amber-800"),
    "system_higher": ("You're doing better than you think", "bg-blue-100 text-blue-800"),
}


def humanize(value: str) -> str:
    """`moderately_productive` -> `Moderately Productive`."""
    return value.replace("_", " ").title()


def level_options(enum_cls: type[StrEnum], *, exclude: tuple[str, ...] = ("unknown",)) -> list[Any]:
    """Build <option>s for a level enum, selecting the middle member as a neutral
    default. ``exclude`` drops non-ratable sentinels (e.g. AlignmentLevel.UNKNOWN)
    so the user can't self-rate with a placeholder."""
    members = [m for m in enum_cls if m.value not in exclude]
    mid = len(members) // 2
    return [
        Option(humanize(member.value), value=member.value, selected=(i == mid))
        for i, member in enumerate(members)
    ]


def bullet_list(heading: str, items: tuple[str, ...]) -> Any:
    """Render a small labelled bullet list, or nothing when empty."""
    if not items:
        return None
    return Div(
        P(heading, cls="text-xs font-semibold text-muted-foreground mt-2"),
        Ul(*[Li(item, cls="text-sm") for item in items], cls="list-disc list-inside"),
    )


def gap_card(label: str, result: DualTrackResult[Any]) -> Any:
    """One perception-gap card for a single dimension."""
    badge_label, badge_cls = DIRECTION_BADGE.get(
        result.gap_direction, ("—", "bg-base-200 text-base-content/70")
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
                    P(humanize(str(result.user_level.value)), cls="font-semibold"),
                    cls="flex-1",
                ),
                Div(
                    P("Measured", cls="text-xs text-muted-foreground"),
                    P(humanize(str(result.system_level.value)), cls="font-semibold"),
                    cls="flex-1",
                ),
                Div(
                    P("Gap", cls="text-xs text-muted-foreground"),
                    P(f"{result.perception_gap:.0%}", cls="font-semibold"),
                    cls="flex-1",
                ),
                cls="flex gap-4 mb-3",
            ),
            bullet_list("What the data shows", result.system_evidence),
            bullet_list("Insights", result.insights),
            bullet_list("Suggestions", result.recommendations),
            cls="space-y-2",
        ),
        cls="mb-4",
    )


def render_checkin_trend(checkins: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> Any:
    """Render a simple trend from the entity's stored dual-track check-ins.

    Shows the most recent ``DualTrackCheckin.TREND_WINDOW`` snapshots (newest
    first) with their date, direction badge, and gap magnitude — the "simple
    trend" surface of gap-trending (ADR-030). Returns nothing when there are no
    stored check-ins.
    """
    if not checkins:
        return None

    recent = list(checkins)[-DualTrackCheckin.TREND_WINDOW :][::-1]
    rows: list[Any] = []
    for snap in recent:
        direction = str(snap.get("gap_direction", ""))
        badge_label, badge_cls = DIRECTION_BADGE.get(
            direction, ("—", "bg-base-200 text-base-content/70")
        )
        gap = snap.get("perception_gap")
        gap_str = f"{gap:.0%}" if isinstance(gap, int | float) else "—"
        rows.append(
            Li(
                Span(str(snap.get("assessed_date", "")), cls="text-muted-foreground"),
                Span(badge_label, cls=f"ml-2 text-xs px-2 py-0.5 rounded-full {badge_cls}"),
                Span(f" · {gap_str} gap", cls="ml-2 text-xs text-muted-foreground"),
                cls="text-sm",
            )
        )

    return Div(
        P("Recent check-ins", cls="text-xs font-semibold text-muted-foreground mt-3"),
        Ul(*rows, cls="space-y-1"),
    )


def render_dual_track_result(
    label: str,
    result: DualTrackResult[Any],
    checkins: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> Any:
    """The HTMX fragment returned after a per-entity self-rating: the gap card
    plus the refreshed trend (which now includes the just-stored check-in)."""
    return Div(
        gap_card(label, result),
        render_checkin_trend(checkins),
    )


def DualTrackSection(
    domain: str,
    entity_uid: str,
    level_enum: type[StrEnum],
    label: str,
    prompt: str,
    checkins: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> Any:
    """Per-entity self-assessment section for a detail page (ADR-030).

    Renders the self-rate form (one level select + reflection), an empty results
    slot, and the current trend. On submit the form POSTs to
    ``/{domain}/dual-track/results?uid={entity_uid}`` which computes + persists a
    check-in and swaps the gap card + refreshed trend into the results slot.

    Pure presentation — no service calls. The trend reads ``checkins`` straight
    off the entity model (``entity.dual_track_checkins``); the route supplies the
    services.
    """
    results_slot = "dual-track-results"

    return Div(
        section_label("Self-Assessment"),
        P(
            "Rate yourself, then see how your self-perception compares with what "
            "your tracked actions show. The gap is the point.",
            cls="text-sm text-muted-foreground mb-3",
        ),
        Card(
            CardHeader(CardTitle(f"How would you rate your {label.lower()}?")),
            CardBody(
                Form(
                    LabelSelect(
                        *level_options(level_enum),
                        label=label,
                        name="level",
                        help_text=prompt,
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
                            cls=ButtonT.primary,
                        ),
                        cls="text-right",
                    ),
                    hx_post=f"/{domain}/dual-track/results?uid={entity_uid}",
                    hx_target=f"#{results_slot}",
                    hx_swap="innerHTML",
                    hx_include="[name='level'],[name='reflection']",
                )
            ),
            cls="mb-4",
        ),
        Div(render_checkin_trend(checkins), id=results_slot),
        H4(
            "Your ratings are saved so you can watch the gap change over time.",
            cls="text-xs text-muted-foreground mt-2",
        ),
        cls="my-4",
    )
