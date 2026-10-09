"""The Insights cards — the hub methods' first door.

One card per ``HubQuestion``: the section mounts a lazy HTMX placeholder per
question, and each fragment answers with the card for one hub method's record
type — ``PathStep`` (what to learn next), the ``(ku_uid, blocked_count)`` rows
(what unlocks the most), ``CrossDomainSynergy``, ``LifePathAlignment``,
``ScheduleAwareRecommendation`` and the ``PerceptionAnalysis`` rollup.

Every record names entities by uid. The route hands each card the titles it
resolved (``titles``) and a card renders ``titles.get(uid, fallback)`` — a uid is
never shown when a title is known. Entity kind comes from the record's own domain
field, never from the uid's spelling (ADR-013).

See: /docs/roadmap/askesis-intelligence-doors.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import H3, A, Div, Li, P, Span, Ul

from core.models.enums import EntityType, HubQuestion
from ui.components import Card, CardBody, CardHeader
from ui.feedback import Badge, BadgeT
from ui.layout import Grid
from ui.patterns.entity_links import entity_detail_href
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.section_header import SectionHeader
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from fasthtml.common import FT

    from core.models.context_types import (
        CrossDomainSynergy,
        LifePathAlignment,
        PathStep,
        ScheduleAwareRecommendation,
    )
    from core.ports.query_types import PerceptionAnalysis

# The staged seventh card: method 2 waits on the learning-path walk
# (``_HUB_CRITICAL_PATH`` in scripts/detect_bloat.py). A note, not a dead card.
STAGED_CRITICAL_PATH_NOTE = (
    "A seventh question — the fastest route to your life path — arrives when the "
    "learning-path walk lands."
)

_SCORE_BADGE_THRESHOLDS: tuple[tuple[float, BadgeT], ...] = (
    (0.7, BadgeT.success),
    (0.4, BadgeT.warning),
)

_ALIGNMENT_DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("knowledge_score", "Knowledge"),
    ("activity_score", "Activity"),
    ("goal_score", "Goals"),
    ("principle_score", "Principles"),
    ("momentum_score", "Momentum"),
)

_DIRECTION_BADGES: dict[str, tuple[str, BadgeT]] = {
    "user_higher": ("over-rated", BadgeT.warning),
    "system_higher": ("under-rated", BadgeT.info),
    "aligned": ("accurate", BadgeT.success),
}


# ---------------------------------------------------------------------------
# The section and the card shell
# ---------------------------------------------------------------------------


def render_hub_section() -> FT:
    """The "Your intelligence" section: one lazy mount per question, plus the staged note."""
    return Div(
        SectionHeader("Your intelligence", cls="mb-2"),
        P(
            "Six questions SKUEL answers from everything you track.",
            cls="text-sm text-muted-foreground mb-4",
        ),
        Grid(
            *[
                content_loading_placeholder(
                    question.fragment_url(),
                    question.mount_id(),
                    loading_text=f"Answering: {question.label()}",
                )
                for question in HubQuestion
            ],
            cols=2,
            gap=4,
        ),
        P(STAGED_CRITICAL_PATH_NOTE, cls="text-xs text-muted-foreground mt-3"),
        id="insights-hub",
        cls="mb-2",
        **{"aria-label": "Your intelligence"},
    )


def _card(question: HubQuestion, *body: Any, footer: Any = None) -> FT:
    """The card shell every answer shares; its id is the mount the fragment swaps into."""
    return Card(
        CardHeader(
            Span(
                f"Question {question.number()}",
                cls="text-11 uppercase tracking-wider text-muted-foreground",
            ),
            H3(question.label(), cls="text-base font-semibold leading-tight text-foreground"),
            cls="p-5 pb-3",
        ),
        CardBody(*body, footer if footer is not None else None, cls="p-5 pt-0 space-y-3"),
        id=question.mount_id(),
        cls="h-full",
    )


def _empty(message: str, *, href: str | None = None, action: str | None = None) -> FT:
    """A truthful empty state: what the method found nothing of, and the door that feeds it."""
    children: list[Any] = [P(message, cls="text-sm text-muted-foreground")]
    if href and action:
        children.append(Div(ButtonLink(action, href=href, size="sm"), cls="mt-2"))
    return Div(*children)


def _entity_link(
    domain: str, uid: str, titles: Mapping[str, str], fallback: str | None = None
) -> FT:
    """The entity's title, linked to its detail page when it has one."""
    text = titles.get(uid) or fallback or uid
    href = entity_detail_href(_entity_type_of(domain), uid)
    if href is None:
        return Span(text, cls="font-medium text-foreground")
    return A(text, href=href, cls="font-medium text-foreground hover:underline")


def _entity_type_of(domain: str) -> str:
    """The canonical entity kind a record's domain word names — the records say
    "knowledge" where the Ku page is the destination; aliases resolve at this boundary.
    A word naming no kind ("meta", "multi") has no detail page and stays as it is."""
    resolved = EntityType.from_string(domain)
    return resolved.value if resolved is not None else domain


def _score_badge(score: float, label: str | None = None) -> FT:
    variant = BadgeT.neutral
    for threshold, candidate in _SCORE_BADGE_THRESHOLDS:
        if score >= threshold:
            variant = candidate
            break
    return Badge(label or f"{score:.0%}", variant=variant, cls="shrink-0 whitespace-nowrap")


def _rows(items: Sequence[Any]) -> FT:
    return Ul(*items, cls="space-y-3 list-none p-0 m-0")


def render_hub_card_error(question: HubQuestion, message: str) -> FT:
    """The card when its hub method could not answer — the question stays, the reason is said."""
    return _card(
        question,
        P("This question couldn't be answered right now.", cls="text-sm text-foreground"),
        P(message, cls="text-xs text-muted-foreground break-words"),
    )


# ---------------------------------------------------------------------------
# 1 — What should I learn next?
# ---------------------------------------------------------------------------


def render_learn_next_card(steps: Sequence[PathStep], titles: Mapping[str, str]) -> FT:
    if not steps:
        return _card(
            HubQuestion.LEARN_NEXT,
            _empty(
                "Nothing is ready to learn yet. Start reading a knowledge unit and SKUEL "
                "has a place to rank from.",
                href="/explore",
                action="Explore knowledge",
            ),
        )
    rows = []
    for step in steps:
        badges: list[Any] = [Badge(f"~{step.estimated_time_minutes} min", variant=BadgeT.ghost)]
        if step.unlocks_count:
            badges.append(Badge(f"unlocks {step.unlocks_count}", variant=BadgeT.info))
        if not step.prerequisites_met:
            badges.append(Badge("prerequisites pending", variant=BadgeT.warning))
        if step.aligns_with_goals:
            badges.append(
                Badge(f"serves {len(step.aligns_with_goals)} goals", variant=BadgeT.accent)
            )
        rows.append(
            Li(
                Div(
                    _entity_link("ku", step.ku_uid, titles, step.title),
                    _score_badge(step.priority_score),
                    cls="flex items-start justify-between gap-2",
                ),
                P(step.rationale, cls="text-xs text-muted-foreground mt-0.5")
                if step.rationale
                else None,
                Div(*badges, cls="flex flex-wrap gap-1.5 mt-1.5"),
            )
        )
    return _card(HubQuestion.LEARN_NEXT, _rows(rows))


# ---------------------------------------------------------------------------
# 4 — What unlocks the most?
# ---------------------------------------------------------------------------


def render_unblock_first_card(blockers: Sequence[tuple[str, int]], titles: Mapping[str, str]) -> FT:
    if not blockers:
        return _card(
            HubQuestion.UNBLOCK_FIRST,
            _empty("No prerequisite is holding anything you're learning back right now."),
        )
    rows = [
        Li(
            Div(
                _entity_link("ku", ku_uid, titles),
                Badge(
                    f"unlocks {count} unit{'s' if count != 1 else ''}",
                    variant=BadgeT.info,
                    cls="shrink-0 whitespace-nowrap",
                ),
                cls="flex items-start justify-between gap-2",
            ),
        )
        for ku_uid, count in blockers
    ]
    return _card(
        HubQuestion.UNBLOCK_FIRST,
        P(
            "Prerequisites you haven't mastered, ranked by how much each one holds back.",
            cls="text-xs text-muted-foreground",
        ),
        _rows(rows),
    )


# ---------------------------------------------------------------------------
# 6 — What helps many things at once?
# ---------------------------------------------------------------------------


def _plural(domain: str, count: int) -> str:
    return f"{count} {domain}{'s' if count != 1 else ''}"


def render_synergies_card(synergies: Sequence[CrossDomainSynergy], titles: Mapping[str, str]) -> FT:
    if not synergies:
        return _card(
            HubQuestion.SYNERGIES,
            _empty(
                "No cross-domain leverage yet. Link a habit to the goals it supports, or a goal "
                "to the knowledge it needs, and what helps many things shows here.",
                href="/goals",
                action="Open your goals",
            ),
        )
    rows = []
    for synergy in synergies:
        rows.append(
            Li(
                Div(
                    _entity_link(synergy.source_domain, synergy.source_uid, titles),
                    _score_badge(synergy.synergy_score),
                    cls="flex items-start justify-between gap-2",
                ),
                P(
                    f"{synergy.synergy_type or 'helps'} "
                    f"{_plural(synergy.target_domain or 'item', len(synergy.target_uids))}",
                    cls="text-xs text-muted-foreground",
                ),
                P(synergy.rationale, cls="text-xs text-foreground/80 mt-0.5")
                if synergy.rationale
                else None,
                Ul(
                    *[
                        Li(tip, cls="text-xs text-muted-foreground")
                        for tip in synergy.recommendations[:2]
                    ],
                    cls="list-disc pl-4 mt-1",
                )
                if synergy.recommendations
                else None,
            )
        )
    return _card(HubQuestion.SYNERGIES, _rows(rows))


# ---------------------------------------------------------------------------
# 7 — Am I living toward my life path?
# ---------------------------------------------------------------------------


def _dimension_bar(label: str, score: float) -> FT:
    pct = max(0, min(100, round(score * 100)))
    return Div(
        Div(
            Span(label, cls="text-xs text-muted-foreground"),
            Span(f"{pct}%", cls="text-xs tabular-nums text-foreground"),
            cls="flex justify-between",
        ),
        Div(
            Div(cls="h-1.5 rounded-full bg-primary", style=f"width: {pct}%"),
            cls="h-1.5 w-full rounded-full bg-muted mt-1",
            role="progressbar",
            **{"aria-valuenow": str(pct), "aria-valuemin": "0", "aria-valuemax": "100"},
        ),
    )


def render_alignment_card(alignment: LifePathAlignment, titles: Mapping[str, str]) -> FT:
    if not alignment.life_path_uid:
        return _card(
            HubQuestion.ALIGNMENT,
            _empty(
                "You haven't designated a life path yet. Alignment is measured against it — "
                "knowledge, activity, goals, principles and momentum.",
                href="/lifepath",
                action="Designate your life path",
            ),
        )
    named: list[Any] = []
    if alignment.aligned_goals:
        named.append(
            P(
                "Goals serving it: ",
                *_joined_links("goal", alignment.aligned_goals, titles),
                cls="text-xs text-muted-foreground",
            )
        )
    if alignment.knowledge_gaps:
        named.append(
            P(
                "Knowledge still to master: ",
                *_joined_links("ku", alignment.knowledge_gaps[:5], titles),
                cls="text-xs text-muted-foreground",
            )
        )
    return _card(
        HubQuestion.ALIGNMENT,
        Div(
            Span(f"{alignment.overall_score:.0%}", cls="text-3xl font-semibold tabular-nums"),
            Badge(alignment.alignment_level, variant=_level_variant(alignment.overall_score)),
            cls="flex items-baseline gap-3",
        ),
        Div(
            *[
                _dimension_bar(label, getattr(alignment, attr))
                for attr, label in _ALIGNMENT_DIMENSIONS
            ],
            cls="space-y-2",
        ),
        Ul(
            *[Li(gap, cls="text-xs text-muted-foreground") for gap in alignment.gaps[:3]],
            cls="list-disc pl-4",
        )
        if alignment.gaps
        else None,
        Ul(
            *[Li(rec, cls="text-xs text-foreground/80") for rec in alignment.recommendations[:3]],
            cls="list-disc pl-4",
        )
        if alignment.recommendations
        else None,
        *named,
        footer=ButtonLink("Open your life path", href="/lifepath", size="sm"),
    )


def _level_variant(score: float) -> BadgeT:
    for threshold, variant in _SCORE_BADGE_THRESHOLDS:
        if score >= threshold:
            return variant
    return BadgeT.neutral


def _joined_links(domain: str, uids: Sequence[str], titles: Mapping[str, str]) -> list[Any]:
    parts: list[Any] = []
    for index, uid in enumerate(uids):
        if index:
            parts.append(", ")
        parts.append(_entity_link(domain, uid, titles))
    return parts


# ---------------------------------------------------------------------------
# 8 — What fits right now?
# ---------------------------------------------------------------------------


def render_right_now_card(
    recommendations: Sequence[ScheduleAwareRecommendation], titles: Mapping[str, str]
) -> FT:
    if not recommendations:
        return _card(
            HubQuestion.RIGHT_NOW,
            _empty(
                "Nothing is pressing for this slot. Overdue tasks, at-risk habits, ready "
                "knowledge and your primary goal are the candidates."
            ),
        )
    rows = []
    for rec in recommendations:
        if rec.recommendation_type == "rest":
            rows.append(
                Li(
                    Div(
                        Span(rec.title, cls="font-medium text-foreground"),
                        Badge("rest", variant=BadgeT.accent, cls="shrink-0 whitespace-nowrap"),
                        cls="flex items-start justify-between gap-2",
                    ),
                    P(rec.rationale, cls="text-xs text-muted-foreground mt-0.5"),
                )
            )
            continue
        flags: list[Any] = [
            Badge(rec.recommendation_type, variant=BadgeT.neutral),
            Badge(f"~{rec.estimated_duration_minutes} min", variant=BadgeT.ghost),
            Badge(
                "fits your time" if rec.fits_available_time else "longer than the time you have",
                variant=BadgeT.success if rec.fits_available_time else BadgeT.warning,
            ),
        ]
        if rec.streak_at_risk:
            flags.append(Badge("streak at risk", variant=BadgeT.error))
        if rec.life_path_aligned:
            flags.append(Badge("life path", variant=BadgeT.accent))
        rows.append(
            Li(
                Div(
                    _entity_link(rec.entity_type, rec.uid, titles, rec.title),
                    _score_badge(rec.overall_score),
                    cls="flex items-start justify-between gap-2",
                ),
                P(rec.rationale, cls="text-xs text-muted-foreground mt-0.5"),
                Div(*flags, cls="flex flex-wrap gap-1.5 mt-1.5"),
            )
        )
    return _card(HubQuestion.RIGHT_NOW, _rows(rows))


# ---------------------------------------------------------------------------
# 9 — How well do I know myself?
# ---------------------------------------------------------------------------


def render_perception_card(analysis: PerceptionAnalysis) -> FT:
    checkin_link = ButtonLink("Run a Self Check-In", href="/self-checkin", size="sm")
    if not analysis["has_data"]:
        return _card(
            HubQuestion.PERCEPTION,
            _empty(
                "No self-assessments yet. Rate yourself on a goal, habit or principle, or run a "
                "Self Check-In, and SKUEL compares the rating with what you tracked."
            ),
            footer=checkin_link,
        )
    rows = []
    for rollup in analysis["per_domain"].values():
        direction = rollup["dominant_direction"]
        if not rollup["assessed_count"] or direction is None:
            continue
        text, variant = _DIRECTION_BADGES.get(direction, ("accurate", BadgeT.success))
        rows.append(
            Li(
                Span(rollup["label"], cls="text-sm text-foreground"),
                Div(
                    Badge(text, variant=variant),
                    Span(
                        f"{rollup['assessed_count']} assessed",
                        cls="text-xs text-muted-foreground",
                    ),
                    cls="flex items-center gap-2",
                ),
                cls="flex items-center justify-between gap-2",
            )
        )
    return _card(
        HubQuestion.PERCEPTION,
        Ul(
            *[Li(insight, cls="text-sm text-foreground/90") for insight in analysis["insights"]],
            cls="list-disc pl-4 space-y-1",
        ),
        _rows(rows) if rows else None,
        footer=checkin_link,
    )


__all__ = [
    "STAGED_CRITICAL_PATH_NOTE",
    "render_alignment_card",
    "render_hub_card_error",
    "render_hub_section",
    "render_learn_next_card",
    "render_perception_card",
    "render_right_now_card",
    "render_synergies_card",
    "render_unblock_first_card",
]
