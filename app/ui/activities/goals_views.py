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
    Option,
    P,
    Small,
    Span,
    Ul,
)
from fasthtml.common import Button as HtmlButton

from core.models.enums.activity_enums import ProgressLevel
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.goal_enums import HabitEssentiality, MeasurementType
from core.models.relationship_names import RelationshipName
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
from ui.components import Button, ButtonT, Icon, Input, Label, Select
from ui.dual_track_card import DualTrackSection
from ui.feedback import Badge, BadgeT, PriorityBadge, Progress, ProgressT, StatusBadge
from ui.patterns.entity_picker import EntityPicker
from ui.patterns.format_date import format_date
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import section_label

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from fasthtml.common import FT

    from core.models.goal.goal import Goal
    from core.models.goal.goal_habit_link import GoalHabitLink
    from core.models.goal.milestone import Milestone
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

    # Connections — one list per heading (ADR-090 §2). The habits that support the goal
    # are listed in their own section, with their tiers, so not here as well.
    conn_section = ConnectionsSection(
        [conn for conn in connections if not _is_supporting_habit(conn)]
    )

    # The goal's habit system — HTMX-loaded (its tiers are read in the fragment route)
    habits_section = content_loading_placeholder(
        f"/goals/habits?uid={goal.uid}", goal_habits_id(goal.uid)
    )

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
        habits_section,
        conn_section,
        dual_track_section,
        relationships,
        cls="max-w-3xl mx-auto",
        id=goal_detail_id(goal.uid),
    )


def goal_detail_id(goal_uid: str) -> str:
    """The detail view's element id: what the progress, milestone and habit controls
    replace."""
    return f"goal-detail-{safe_id(goal_uid)}"


def goal_habits_id(goal_uid: str) -> str:
    """The habit section's element id: the slot its fragment fills."""
    return f"goal-habits-{safe_id(goal_uid)}"


def _is_supporting_habit(conn: EntityConnection) -> bool:
    """A link the habit section lists: a habit supporting this goal."""
    return (
        conn["rel_type"] == RelationshipName.SUPPORTS_GOAL.value
        and conn["connected_type"] == EntityType.HABIT.value
    )


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
    """A goal's milestones as a checklist, with the controls that add, complete and
    reopen them.

    Each open milestone carries a button that marks it reached
    (``/api/goals/{uid}/milestones/complete``), each reached one a button that reopens
    it (``/api/goals/{uid}/milestones/reopen``); the form below adds one
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
        # A reopened milestone keeps the day it was first reached; it shows as open.
        if ms.is_completed and ms.achieved_date:
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
        if editable:
            row.append(_MilestoneButton(goal, ms, target))
        items.append(Li(*row, cls="flex items-start gap-2"))

    return Div(
        section_label("Milestones"),
        Ul(*items, cls="space-y-2") if items else "",
        _AddMilestoneForm(goal, target) if editable else "",
        cls="my-4",
    )


def _MilestoneButton(goal: Goal, ms: Milestone, target: str) -> FT:
    """The one control a milestone row carries: Complete on an open milestone
    (``/milestones/complete``), Reopen on a reached one (``/milestones/reopen``)."""
    action, label = ("reopen", "Reopen") if ms.is_completed else ("complete", "Complete")
    return HtmlButton(
        label,
        type="button",
        hx_post=f"/api/goals/{goal.uid}/milestones/{action}",
        hx_vals=json.dumps({"milestone_uid": ms.uid}),
        hx_target=target,
        hx_swap="outerHTML",
        hx_disabled_elt="this",
        cls=(
            "shrink-0 rounded-md border border-input px-3 h-9 text-sm "
            "hover:bg-accent disabled:opacity-50"
        ),
        aria_label=f"{label} milestone {ms.title}",
        **{f"data-goal-milestone-{action}": ms.uid},
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


#: Each tier's name on the page, in the order the section lists and offers them.
_TIER_LABELS: dict[HabitEssentiality, str] = {
    HabitEssentiality.ESSENTIAL: "Essential",
    HabitEssentiality.CRITICAL: "Critical",
    HabitEssentiality.SUPPORTING: "Supporting",
    HabitEssentiality.OPTIONAL: "Optional",
}


def GoalHabitsSection(goal: Goal, links: Sequence[GoalHabitLink]) -> FT:
    """The habits that support a goal, each at its tier, with the controls that change
    them.

    Each row's tier select moves the habit to another tier
    (``/api/goals/{uid}/habits/essentiality``) and its Unlink button removes it
    (``/api/goals/{uid}/habits/unlink``); the form below links one of the learner's
    habits at a tier (``/api/goals/{uid}/habits``). Each is answered with the whole
    detail view, which loads this section again. A goal set aside shows its habits and
    their tiers, and no control. Rendered by the ``/goals/habits`` fragment route.
    """
    editable = goal.status not in _SET_ASIDE
    target = f"#{goal_detail_id(goal.uid)}"
    rows = [_HabitRow(goal, link, target, editable) for link in links]
    if rows:
        body: FT = Ul(*rows, cls="divide-y")
    else:
        body = P("No habits support this goal yet.", cls="text-sm text-muted-foreground")
    return Div(
        section_label("Habits that support this goal"),
        body,
        _LinkHabitForm(goal, target) if editable else "",
        id=goal_habits_id(goal.uid),
        cls="my-4",
    )


def _HabitRow(goal: Goal, link: GoalHabitLink, target: str, editable: bool) -> FT:
    """One linked habit: its title, then its tier as a select and an Unlink button, or
    as a badge on a goal set aside."""
    title = A(
        link.title or "Untitled habit",
        href=f"/habits/detail?uid={link.habit_uid}",
        cls="break-words hover:underline",
    )
    if not editable:
        return Li(
            Div(title, cls="flex-1 min-w-0"),
            Span(
                _TIER_LABELS[link.essentiality],
                cls=f"shrink-0 rounded-md border px-2 py-0.5 text-xs "
                f"{link.essentiality.get_badge_class()}",
                data_goal_habit_tier=link.essentiality.value,
            ),
            cls="flex items-center gap-2 py-2",
        )
    tier_select = Select(
        *_tier_options(link.essentiality),
        name="new_essentiality",
        hx_post=f"/api/goals/{goal.uid}/habits/essentiality",
        hx_trigger="change",
        hx_vals=json.dumps({"habit_uid": link.habit_uid}),
        hx_target=target,
        hx_swap="outerHTML",
        hx_disabled_elt="this",
        aria_label=f"Tier of habit {link.title}",
        full_width=False,
        cls="sm:w-40",
        data_goal_habit_tier_select=link.habit_uid,
    )
    unlink = HtmlButton(
        "Unlink",
        type="button",
        hx_post=f"/api/goals/{goal.uid}/habits/unlink",
        hx_vals=json.dumps({"habit_uid": link.habit_uid}),
        hx_target=target,
        hx_swap="outerHTML",
        hx_disabled_elt="this",
        cls=(
            "shrink-0 rounded-md border border-input px-3 h-11 md:h-10 text-sm "
            "hover:bg-accent disabled:opacity-50"
        ),
        aria_label=f"Unlink habit {link.title}",
        data_goal_habit_unlink=link.habit_uid,
    )
    return Li(
        Div(title, cls="flex-1 min-w-0"),
        Div(tier_select, unlink, cls="flex items-center gap-2"),
        cls="flex flex-col sm:flex-row sm:items-center gap-2 py-2",
    )


def _tier_options(selected: HabitEssentiality) -> list[FT]:
    """The four tiers as select options, ``selected`` chosen."""
    return [
        Option(label, value=tier.value, selected=tier is selected)
        for tier, label in _TIER_LABELS.items()
    ]


def _LinkHabitForm(goal: Goal, target: str) -> FT:
    """Link one of the learner's habits at a tier. Posts ``/api/goals/{uid}/habits``."""
    form_id = safe_id(goal.uid)
    return Form(
        P("Link a habit", cls="text-sm font-medium mb-2"),
        Div(
            Div(EntityPicker("habit_uid", "habit", required=True), cls="sm:flex-1"),
            Select(
                *_tier_options(HabitEssentiality.SUPPORTING),
                name="essentiality",
                id=f"goal-habit-tier-{form_id}",
                aria_label="Tier of the habit to link",
                full_width=False,
                cls="sm:w-40",
            ),
            Button("Link habit", type="submit", cls=ButtonT.default, size="field"),
            cls="flex flex-col sm:flex-row gap-2",
        ),
        Small(
            "The tier says how much this goal depends on the habit: essential, then "
            "critical, supporting and optional.",
            cls="block mt-2 text-muted-foreground",
        ),
        hx_post=f"/api/goals/{goal.uid}/habits",
        hx_target=target,
        hx_swap="outerHTML",
        hx_disabled_elt="find button[type=submit]",
        cls="mt-4",
        data_goal_link_habit="1",
    )
