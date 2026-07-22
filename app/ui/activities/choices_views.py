"""Choices UI view components.

Pure FastHTML components for rendering choice data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.choices_views import ChoiceList, ChoiceStatsBar
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Div,
    Li,
    P,
    Small,
    Span,
    Ul,
)

from ui.activities._shared import (
    ActivityList,
    ConnectionBadges,
    MetadataField,
    PriorityBadgeDropdown,
    safe_id,
)
from ui.components import Button, ButtonT, Card, Icon
from ui.feedback import Badge, BadgeT, PriorityBadge, StatusBadge
from ui.layout import Container, DivHStacked
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import section_label

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.choice.choice import Choice
    from core.models.choice.choice_option import ChoiceOption


def ChoiceStatsBar(choices: list["Choice"]) -> "FT":
    """Quick stats bar showing choice counts."""
    total = len(choices)
    pending = sum(
        1 for c in choices if not c.decided_at and not (c.status and c.status.value == "completed")
    )
    decided = sum(
        1 for c in choices if c.decided_at or (c.status and c.status.value == "completed")
    )
    satisfaction_scores = [
        c.satisfaction_score
        for c in choices
        if c.satisfaction_score is not None and c.satisfaction_score > 0
    ]
    avg_satisfaction = (
        sum(satisfaction_scores) / len(satisfaction_scores) if satisfaction_scores else 0
    )

    stats = [
        StatItem(label="Total", value=total, href="/choices?status=all"),
        StatItem(
            label="Pending",
            value=pending,
            color="warning" if pending > 0 else None,
            href="/choices?status=pending",
        ),
        StatItem(label="Decided", value=decided, color="success", href="/choices?status=decided"),
        StatItem(
            label="Avg Satisfaction",
            value=f"{avg_satisfaction:.1f}/5" if avg_satisfaction > 0 else "-",
            color="primary" if avg_satisfaction >= 3.5 else None,
        ),
    ]
    return StatsGrid(stats, cols=4)


def ChoiceList(
    choices: list["Choice"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of choice cards. Returns a replaceable container for HTMX."""
    return ActivityList(choices, "choice", ChoiceCard, connections_map)


def ChoiceCard(
    choice: "Choice",
    connections: list[dict[str, str]] | None = None,
) -> "FT":
    """Single choice card with type, deadline, decision status, and connections."""
    is_decided = bool(choice.decided_at) or (choice.status and choice.status.value == "completed")

    # Status toggle button
    new_status = "active" if is_decided else "completed"
    toggle_icon = "check" if is_decided else "git-branch"
    toggle_cls = "text-green-600" if is_decided else ""

    toggle_btn = Button(
        Icon(toggle_icon, size=16, cls=f"inline {toggle_cls}"),
        hx_post=f"/api/choices/{choice.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#choice-{safe_id(choice.uid)}",
        hx_swap="outerHTML",
        cls=(ButtonT.default, "rounded"),
        size="sm",
        title=f"Mark as {new_status}",
    )

    # Title
    title_cls = "text-muted-foreground" if is_decided else ""
    title_el = A(
        choice.title or "Untitled",
        href=f"/choices/detail?uid={choice.uid}",
        cls=f"hover:underline {title_cls}",
    )

    # Badges
    badges: list[Any] = []
    if choice.choice_type:
        badges.append(Badge(str(choice.choice_type.value).title(), variant=BadgeT.primary))
    badges.append(
        PriorityBadgeDropdown(
            choice.uid,
            str(choice.priority) if choice.priority else None,
            domain="choices",
            singular="choice",
        )
    )
    if choice.status:
        badges.append(StatusBadge(str(choice.status)))
    if choice.options:
        badges.append(Badge(f"{len(choice.options)} options", variant=BadgeT.secondary))

    # Deadline
    deadline_el = Span()
    if choice.decision_deadline:
        overdue = choice.is_deadline_past()
        dl_str = str(choice.decision_deadline)[:10]
        if overdue and not is_decided:
            dl_str += " (overdue)"
        dl_cls = (
            "text-destructive font-bold" if overdue and not is_decided else "text-muted-foreground"
        )
        deadline_el = Small(f"Deadline: {dl_str}", cls=dl_cls)

    # Satisfaction score for decided choices
    satisfaction_el = Span()
    if is_decided and choice.satisfaction_score and choice.satisfaction_score > 0:
        satisfaction_el = Small(
            f"Satisfaction: {choice.satisfaction_score}/5",
            cls="text-muted-foreground ml-2",
        )

    # Tags
    tags_el = Span()
    if choice.tags:
        tag_badges = [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in choice.tags[:5]]
        tags_el = Div(*tag_badges, cls="mt-2")

    # Connection badges
    conn_el = ConnectionBadges(connections or [])

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            DivHStacked(title_el, satisfaction_el, cls="flex-wrap"),
            DivHStacked(*badges, cls="flex-wrap mt-2") if badges else "",
            deadline_el,
            tags_el,
            conn_el,
            cls="ml-2 flex-1 min-w-0",
        ),
        cls="flex items-start",
    )

    opacity = "opacity-75" if is_decided else ""
    return Card(
        header,
        id=f"choice-{safe_id(choice.uid)}",
        cls=f"mb-2 p-3 {opacity}",
    )


def ChoiceDetailView(
    choice: "Choice",
    connections: list[dict[str, str]],
) -> "FT":
    """Full detail page for a single choice."""
    is_decided = bool(choice.decided_at) or (choice.status and choice.status.value == "completed")

    # Subtitle
    subtitle_parts: list[str] = []
    if choice.status:
        subtitle_parts.append(str(choice.status).replace("_", " ").title())
    if choice.choice_type:
        subtitle_parts.append(str(choice.choice_type.value).title())
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

    header = PageHeader(choice.title or "Untitled Choice", subtitle=subtitle)

    # Badges
    badges: list[Any] = []
    if choice.choice_type:
        badges.append(Badge(str(choice.choice_type.value).title(), variant=BadgeT.primary))
    if choice.priority:
        badges.append(PriorityBadge(str(choice.priority)))
    if choice.status:
        badges.append(StatusBadge(str(choice.status)))

    # Description
    desc_el = Div()
    if choice.description:
        desc_el = Div(P(choice.description), cls="my-4")

    # Options section
    options_section = Div()
    if choice.options:
        options_section = OptionsSection(choice.options, choice.selected_option_uid)

    # Decision section (criteria, constraints, rationale)
    decision_items: list[Any] = []
    if choice.decision_rationale:
        decision_items.append(MetadataField("Rationale", P(choice.decision_rationale)))
    if choice.decision_criteria:
        criteria_list = Ul(
            *[Li(c) for c in choice.decision_criteria],
            cls="list-disc pl-6",
        )
        decision_items.append(MetadataField("Criteria", criteria_list))
    if choice.constraints:
        constraints_list = Ul(
            *[Li(c) for c in choice.constraints],
            cls="list-disc pl-6",
        )
        decision_items.append(MetadataField("Constraints", constraints_list))
    if choice.stakeholders:
        decision_items.append(MetadataField("Stakeholders", P(", ".join(choice.stakeholders))))
    decision_section = Div()
    if decision_items:
        decision_section = Div(
            section_label("Decision Framework"),
            *decision_items,
            cls="my-4",
        )

    # Outcome section (only if decided)
    outcome_section = Div()
    if is_decided:
        outcome_items: list[Any] = []
        if choice.satisfaction_score and choice.satisfaction_score > 0:
            filled = int(choice.satisfaction_score)
            stars = "★" * filled + "☆" * (5 - filled)
            outcome_items.append(
                MetadataField(
                    "Satisfaction",
                    Span(stars, cls="text-yellow-600", style="font-size: 1.2rem;"),
                    Span(f" {choice.satisfaction_score}/5", cls="text-muted-foreground text-sm"),
                )
            )
        if choice.actual_outcome:
            outcome_items.append(MetadataField("Actual Outcome", P(choice.actual_outcome)))
        if choice.lessons_learned:
            lessons_list = Ul(
                *[Li(lesson) for lesson in choice.lessons_learned],
                cls="list-disc pl-6",
            )
            outcome_items.append(MetadataField("Lessons Learned", lessons_list))
        if outcome_items:
            outcome_section = Div(
                section_label("Outcome"),
                *outcome_items,
                cls="my-4",
            )

    # Timing
    timing_items: list[Any] = []
    if choice.decision_deadline:
        overdue = choice.is_deadline_past() and not is_decided
        dl_cls = "text-destructive font-bold" if overdue else ""
        timing_items.append(
            MetadataField("Deadline", Span(str(choice.decision_deadline)[:10], cls=dl_cls))
        )
    if choice.decided_at:
        timing_items.append(MetadataField("Decided", Span(str(choice.decided_at)[:10])))
    if choice.created_at:
        timing_items.append(MetadataField("Created", Span(str(choice.created_at)[:10])))
    timing_grid = Div()
    if timing_items:
        timing_grid = Div(
            *timing_items,
            cls="grid grid-cols-1 sm:grid-cols-3 gap-2 my-4",
        )

    # Tags
    tags_el = Div()
    if choice.tags:
        tag_badges = [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in choice.tags]
        tags_el = Div(
            Small("Tags", cls="text-muted-foreground block mb-2"),
            *tag_badges,
            cls="my-4",
        )

    # Connections
    conn_section = Div()
    if connections:
        conn_section = Div(
            section_label("Connections"),
            ConnectionBadges(connections),
            cls="my-4",
        )

    # Lateral relationships
    relationships = EntityRelationshipsSection(
        entity_uid=choice.uid,
        entity_type="choices",
        authoring=True,
    )

    return Container(
        header,
        DivHStacked(*badges, cls="flex-wrap mb-2") if badges else "",
        desc_el,
        options_section,
        decision_section,
        outcome_section,
        timing_grid,
        tags_el,
        conn_section,
        relationships,
        size="3xl",
    )


def OptionsSection(options: tuple["ChoiceOption", ...], selected_uid: str | None) -> "FT":
    """Render choice options as a visual list with selected indicator."""
    items: list[Any] = []
    for opt in options:
        is_selected = selected_uid and opt.uid == selected_uid
        icon = "check-circle" if is_selected else "circle"
        icon_cls = "text-green-600" if is_selected else "text-muted-foreground"
        text_cls = "font-bold" if is_selected else ""

        opt_content: list[Any] = [
            Icon(icon, size=16, cls=f"inline mr-2 {icon_cls}"),
            Span(opt.title or opt.uid, cls=text_cls),
        ]
        if is_selected:
            opt_content.append(Small(" (selected)", cls="text-green-600"))
        if opt.description:
            opt_content.append(Small(f" — {opt.description}", cls="text-muted-foreground"))

        items.append(Li(*opt_content, cls="mb-2"))

    return Div(
        section_label("Options"),
        Ul(*items),
        cls="my-4",
    )
