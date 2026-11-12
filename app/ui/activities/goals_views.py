"""Goals UI view components.

Pure FastHTML components for rendering goal data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.goals_views import GoalList, GoalStatsBar
"""

import json
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Div,
    Form,
    Li,
    P,
    Small,
    Span,
    Ul,
)
from fasthtml.common import Button as HtmlButton

from core.models.enums.activity_enums import ProgressLevel
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.utils.activity_stats import compute_goal_stats
from ui.activities._shared import (
    ActivityList,
    ConnectionRows,
    ConnectionsSection,
    MetadataField,
    PriorityBadgeDropdown,
    TagsBlock,
    safe_id,
)
from ui.components import Button, ButtonT, Icon, Input, Label
from ui.dual_track_card import DualTrackSection
from ui.feedback import Badge, BadgeT, PriorityBadge, Progress, ProgressT, StatusBadge
from ui.patterns.format_date import format_date
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import section_label

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fasthtml.common import FT

    from core.models.goal.goal import Goal
    from core.ports.query_types import EntityConnection


def GoalStatsBar(goals: list[Goal]) -> FT:
    """Quick stats bar showing goal counts by status.

    "Wobbly" is the opposite of "On Track" — goals that need attention:
    behind schedule (progress < expected) or overdue (past target date).
    """
    s = compute_goal_stats(goals)
    stats = [
        StatItem(label="Total", value=s.total, href="/goals?status=all"),
        StatItem(label="Active", value=s.active, color="primary", href="/goals?status=active"),
        StatItem(
            label="On Track", value=s.on_track, color="success", href="/goals?status=on_track"
        ),
        StatItem(
            label="Completed", value=s.completed, color="success", href="/goals?status=completed"
        ),
        StatItem(
            label="Wobbly",
            value=s.wobbly_count,
            color="error" if s.wobbly_count > 0 else None,
            change=s.wobbly_detail,
            trend="down" if s.wobbly_count > 0 else None,
            href="/goals?status=wobbly",
        ),
    ]
    return StatsGrid(stats, cols=5)


def GoalList(
    goals: list[Goal],
    connections_map: Mapping[str, list[EntityConnection]] | None = None,
) -> FT:
    """Render a list of goal cards. Returns a replaceable container for HTMX."""
    return ActivityList(goals, "goal", GoalCard, connections_map)


def GoalCard(
    goal: Goal,
    connections: list[EntityConnection] | None = None,
) -> FT:
    """Single goal card with progress bar, badges, and its links, one line per heading."""
    progress = goal.calculate_progress()
    progress_pct = int(progress * 100)
    overdue = goal.is_overdue()
    on_track = goal.is_on_track()

    # Title — clickable link to detail page
    title_cls = "text-muted-foreground line-through" if goal.is_completed else ""
    title_el = A(
        goal.title or "Untitled",
        href=f"/goals/detail?uid={goal.uid}",
        cls=f"hover:underline {title_cls}",
    )

    # Badges row
    badges: list[Any] = []
    badges.append(
        PriorityBadgeDropdown(
            goal.uid,
            str(goal.priority) if goal.priority else None,
            domain="goals",
            singular="goal",
        )
    )
    if goal.status:
        badges.append(StatusBadge(str(goal.status)))
    if goal.timeframe:
        badges.append(
            Badge(
                str(goal.timeframe.value).replace("_", " ").title(),
                variant=BadgeT.primary,
            )
        )

    # Progress bar — variant mirrors the prior color logic
    # (completed > overdue > on-track > behind).
    if goal.is_completed:
        progress_variant = ProgressT.success
    elif overdue:
        progress_variant = ProgressT.error
    elif on_track:
        progress_variant = ProgressT.success
    else:
        progress_variant = ProgressT.warning

    progress_el = Div(
        Div(
            Span(f"{progress_pct}%", cls="text-sm text-muted-foreground"),
            Progress(value=progress_pct, variant=progress_variant),
            cls="flex-1 min-w-0",
        ),
        cls="mt-2",
    )

    # Target date
    date_el = Span()
    if goal.target_date:
        date_cls = "text-error font-bold" if overdue else "text-muted-foreground"
        days_left = goal.days_remaining()
        date_str = str(goal.target_date)
        if overdue:
            date_str += " (overdue)"
        elif days_left > 0:
            date_str += f" ({days_left}d left)"
        date_el = Small(date_str, cls=date_cls)

    # Page links, one line per heading
    conn_summary = ConnectionRows(connections or [])

    # Card assembly
    header = Div(
        Div(
            Div(title_el, cls="flex items-center flex-wrap"),
            Div(*badges, cls="flex flex-wrap items-center mt-2") if badges else "",
            date_el,
            progress_el,
            conn_summary,
            cls="flex-1 min-w-0",
        ),
        cls="flex items-start",
    )

    completed_cls = "opacity-75" if goal.is_completed else ""
    return Div(
        header,
        id=f"goal-{safe_id(goal.uid)}",
        cls=f"card bg-card text-card-foreground rounded-lg border p-3 {completed_cls}",
    )


def GoalDetailView(
    goal: Goal,
    connections: list[EntityConnection],
) -> FT:
    """Full detail page for a single goal."""
    # Subtitle
    subtitle_parts: list[str] = []
    if goal.status:
        subtitle_parts.append(str(goal.status).replace("_", " ").title())
    if goal.timeframe:
        subtitle_parts.append(str(goal.timeframe.value).replace("_", " ").title())
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

    header = PageHeader(goal.title or "Untitled Goal", subtitle=subtitle)

    # Badges
    badges: list[Any] = []
    if goal.priority:
        badges.append(PriorityBadge(str(goal.priority)))
    if goal.status:
        badges.append(StatusBadge(str(goal.status)))

    # Progress section
    progress = goal.calculate_progress()
    progress_pct = int(progress * 100)
    on_track = goal.is_on_track()
    track_cls = "text-success" if on_track else "text-warning"
    track_text = "On Track" if on_track else "Behind"
    if goal.is_completed:
        track_cls = "text-success"
        track_text = "Completed"
    elif goal.status in _SET_ASIDE:
        # A goal set aside is neither on track nor behind.
        track_cls = "text-muted-foreground"
        track_text = str(goal.status).replace("_", " ").title()
    elif goal.is_overdue():
        track_cls = "text-error"
        track_text = "Overdue"

    progress_section = Div(
        Div(
            Span(f"{progress_pct}%", cls="text-lg font-bold"),
            Span(f" · {track_text}", cls=f"text-sm {track_cls}"),
            cls="mb-2",
        ),
        Progress(
            value=progress_pct,
            variant=ProgressT.success if on_track else ProgressT.warning,
        ),
        _ProgressControl(goal),
        cls="my-4",
    )

    # Description and motivation fields
    text_sections: list[Any] = []
    if goal.description:
        text_sections.append(Div(P(goal.description), cls="my-4"))
    if goal.vision_statement:
        text_sections.append(
            Div(
                MetadataField("Vision", P(goal.vision_statement)),
                cls="my-4",
            )
        )
    if goal.why_important:
        text_sections.append(
            Div(
                MetadataField("Why Important", P(goal.why_important)),
                cls="my-4",
            )
        )
    if goal.success_criteria:
        text_sections.append(
            Div(
                MetadataField("Success Criteria", P(goal.success_criteria)),
                cls="my-4",
            )
        )

    # Metadata grid
    meta_items: list[Any] = []
    if goal.target_date:
        overdue = goal.is_overdue()
        due_cls = "text-error font-bold" if overdue else ""
        meta_items.append(MetadataField("Target Date", Span(str(goal.target_date), cls=due_cls)))
    if goal.start_date:
        meta_items.append(MetadataField("Start Date", Span(str(goal.start_date))))
    if goal.target_value:
        value_str = f"{goal.current_value:g}/{goal.target_value:g}"
        if goal.unit_of_measurement:
            value_str += f" {goal.unit_of_measurement}"
        meta_items.append(MetadataField("Progress", Span(value_str)))
    if goal.created_at:
        meta_items.append(MetadataField("Created", Span(format_date(goal.created_at, "%Y-%m-%d"))))

    meta_grid = Div()
    if meta_items:
        meta_grid = Div(
            *meta_items,
            cls="grid grid-cols-2 sm:grid-cols-4 gap-2 my-4",
        )

    # Tags
    tags_el = TagsBlock(goal.tags)

    # Milestones section
    milestones_section = MilestonesSection(goal)

    # Connections — one list per heading (ADR-090 §2)
    conn_section = ConnectionsSection(connections)

    # Dual-track self-assessment (perception gap + trend) — ADR-030
    dual_track_section = DualTrackSection(
        domain="goals",
        entity_uid=goal.uid,
        level_enum=ProgressLevel,
        label="Progress",
        prompt="How much progress do you feel you've made toward this goal?",
        checkins=goal.dual_track_checkins,
    )

    # Lateral relationships (Vis.js graph, blocking chain, alternatives) + authoring.
    relationships = EntityRelationshipsSection(
        entity_uid=goal.uid,
        entity_type="goals",
        authoring=True,
    )

    return Div(
        header,
        Div(*badges, cls="flex flex-wrap items-center mb-2") if badges else "",
        progress_section,
        *text_sections,
        meta_grid,
        tags_el,
        milestones_section,
        conn_section,
        dual_track_section,
        relationships,
        cls="max-w-3xl mx-auto",
        id=goal_detail_id(goal.uid),
    )


def goal_detail_id(goal_uid: str) -> str:
    """The detail view's element id: what the progress and milestone controls replace."""
    return f"goal-detail-{safe_id(goal_uid)}"


#: Statuses in which a goal's owner has set it aside: its page shows what it holds
#: and offers no progress or milestone control.
_SET_ASIDE = (EntityStatus.CANCELLED, EntityStatus.ARCHIVED, EntityStatus.FAILED)

#: Where a derived figure comes from, for the line shown in place of the control.
_DERIVED_FIGURE_SOURCE: dict[MeasurementType, str] = {
    MeasurementType.TASK_BASED: "Measured from the tasks and events linked to this goal.",
    MeasurementType.HABIT_BASED: "Measured from the streaks of this goal's habits.",
    MeasurementType.MILESTONE: "Measured from this goal's milestones.",
}


def _ProgressControl(goal: Goal) -> FT | None:
    """The control that records a figure the learner enters, or the line saying where
    a derived figure comes from. Posts ``/api/goals/{uid}/progress``.

    A numeric goal is entered in its own unit against its target; the other entered
    types take the percentage. A goal set aside shows neither.
    """
    if goal.status in _SET_ASIDE:
        return None
    measurement = goal.measurement_type or MeasurementType.PERCENTAGE
    if not measurement.takes_entered_figure():
        return P(_DERIVED_FIGURE_SOURCE[measurement], cls="text-sm text-muted-foreground mt-2")

    form_id = safe_id(goal.uid)
    if measurement.entered_in_units():
        if not goal.target_value:
            return P(
                "Set a target value on this goal to record progress.",
                cls="text-sm text-muted-foreground mt-2",
            )
        unit = f" {goal.unit_of_measurement}" if goal.unit_of_measurement else ""
        label = f"Progress so far (of {goal.target_value:g}{unit})"
        value, ceiling = f"{goal.current_value:g}", None
    else:
        label = "Progress so far (%)"
        value, ceiling = f"{goal.progress_percentage or 0.0:g}", 100
    return Form(
        Label(label, fr=f"goal-progress-{form_id}", cls="block mb-2"),
        Div(
            Input(
                name="progress",
                id=f"goal-progress-{form_id}",
                type="number",
                min=0,
                max=ceiling,
                step="any",
                value=value,
                required=True,
                inputmode="decimal",
                cls="sm:w-40",
            ),
            Button("Save progress", type="submit", cls=ButtonT.default, size="field"),
            cls="flex flex-col sm:flex-row gap-2",
        ),
        hx_post=f"/api/goals/{goal.uid}/progress",
        hx_target=f"#{goal_detail_id(goal.uid)}",
        hx_swap="outerHTML",
        hx_disabled_elt="find button[type=submit]",
        cls="mt-4",
        data_goal_progress="1",
    )


def MilestonesSection(goal: Goal) -> FT:
    """A goal's milestones as a checklist, with the controls that add and complete them.

    Each open milestone carries a button that marks it reached
    (``/api/goals/{uid}/milestones/complete``); the form below adds one
    (``/api/goals/{uid}/milestones``). Both are answered with the whole detail view.
    A goal set aside shows its milestones and no control; one with none shows nothing.
    """
    editable = goal.status not in _SET_ASIDE
    if not goal.milestones and not editable:
        return Div()
    target = f"#{goal_detail_id(goal.uid)}"
    items: list[FT] = []
    for ms in goal.milestones:
        icon = "check" if ms.is_completed else "circle"
        icon_cls = "text-success" if ms.is_completed else "text-muted-foreground"
        text_cls = "line-through text-muted-foreground" if ms.is_completed else ""

        date_str = ""
        if ms.target_date:
            date_str = f"By {ms.target_date}"
        if ms.achieved_date:
            date_str = f"Achieved {ms.achieved_date}"

        row: list[FT] = [
            Icon(icon, size=16, cls=f"mt-1 shrink-0 {icon_cls}"),
            Div(
                Span(ms.title, cls=f"break-words {text_cls}".strip()),
                Small(date_str, cls="block text-muted-foreground") if date_str else "",
                P(ms.description, cls="text-sm text-muted-foreground") if ms.description else "",
                cls="flex-1 min-w-0",
            ),
        ]
        if editable and not ms.is_completed:
            row.append(
                HtmlButton(
                    "Complete",
                    type="button",
                    hx_post=f"/api/goals/{goal.uid}/milestones/complete",
                    hx_vals=json.dumps({"milestone_uid": ms.uid}),
                    hx_target=target,
                    hx_swap="outerHTML",
                    hx_disabled_elt="this",
                    cls=(
                        "shrink-0 rounded-md border border-input px-3 h-9 text-sm "
                        "hover:bg-accent disabled:opacity-50"
                    ),
                    aria_label=f"Complete milestone {ms.title}",
                    data_goal_milestone_complete=ms.uid,
                )
            )
        items.append(Li(*row, cls="flex items-start gap-2"))

    return Div(
        section_label("Milestones"),
        Ul(*items, cls="space-y-2") if items else "",
        _AddMilestoneForm(goal, target) if editable else "",
        cls="my-4",
    )


def _AddMilestoneForm(goal: Goal, target: str) -> FT:
    """One more milestone: a title and an optional target date. Posts ``/milestones``."""
    form_id = safe_id(goal.uid)
    return Form(
        Label("Add a milestone", fr=f"milestone-title-{form_id}", cls="block mb-2"),
        Div(
            Input(
                name="title",
                id=f"milestone-title-{form_id}",
                placeholder="Milestone",
                required=True,
                maxlength=200,
                cls="sm:flex-1",
            ),
            Input(
                name="target_date",
                type="date",
                aria_label="Milestone target date (optional)",
                cls="sm:w-44",
            ),
            Button("Add milestone", type="submit", cls=ButtonT.default, size="field"),
            cls="flex flex-col sm:flex-row gap-2",
        ),
        Small(
            "The date is when you aim to reach it. It is optional.",
            cls="block mt-2 text-muted-foreground",
        ),
        hx_post=f"/api/goals/{goal.uid}/milestones",
        hx_target=target,
        hx_swap="outerHTML",
        hx_disabled_elt="find button[type=submit]",
        cls="mt-4",
        data_goal_add_milestone="1",
    )
