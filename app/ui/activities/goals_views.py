"""Goals UI view components.

Pure FastHTML components for rendering goal data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.goals_views import GoalList, GoalStatsBar
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

from core.models.enums.activity_enums import ProgressLevel
from core.utils.activity_stats import compute_goal_stats
from ui.activities._shared import (
    ActivityList,
    ConnectionsSection,
    ConnectionSummary,
    MetadataField,
    PriorityBadgeDropdown,
    safe_id,
)
from ui.components import Icon
from ui.dual_track_card import DualTrackSection
from ui.feedback import Badge, BadgeT, PriorityBadge, Progress, ProgressT, StatusBadge
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import section_label

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.goal.goal import Goal
    from core.models.goal.milestone import Milestone


def GoalStatsBar(goals: list["Goal"]) -> "FT":
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
    goals: list["Goal"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of goal cards. Returns a replaceable container for HTMX."""
    return ActivityList(goals, "goal", GoalCard, connections_map)


def GoalCard(
    goal: "Goal",
    connections: list[dict[str, str]] | None = None,
) -> "FT":
    """Single goal card with progress bar, badges, and connection counts."""
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
        date_cls = "text-destructive font-bold" if overdue else "text-muted-foreground"
        days_left = goal.days_remaining()
        date_str = str(goal.target_date)
        if overdue:
            date_str += " (overdue)"
        elif days_left > 0:
            date_str += f" ({days_left}d left)"
        date_el = Small(date_str, cls=date_cls)

    # Connection count summary
    conn_summary = ConnectionSummary(connections or [])

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
        cls=f"card bg-card text-card-foreground rounded-lg border p-3 mb-2 {completed_cls}",
    )


def GoalDetailView(
    goal: "Goal",
    connections: list[dict[str, str]],
) -> "FT":
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
    track_cls = "text-green-600" if on_track else "text-yellow-600"
    track_text = "On Track" if on_track else "Behind"
    if goal.is_completed:
        track_cls = "text-green-600"
        track_text = "Completed"
    elif goal.is_overdue():
        track_cls = "text-destructive"
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
        due_cls = "text-destructive font-bold" if overdue else ""
        meta_items.append(MetadataField("Target Date", Span(str(goal.target_date), cls=due_cls)))
    if goal.start_date:
        meta_items.append(MetadataField("Start Date", Span(str(goal.start_date))))
    if goal.target_value:
        value_str = f"{goal.current_value}/{goal.target_value}"
        if goal.unit_of_measurement:
            value_str += f" {goal.unit_of_measurement}"
        meta_items.append(MetadataField("Progress", Span(value_str)))
    if goal.created_at:
        meta_items.append(MetadataField("Created", Span(str(goal.created_at)[:10])))

    meta_grid = Div()
    if meta_items:
        meta_grid = Div(
            *meta_items,
            cls="grid grid-cols-2 sm:grid-cols-4 gap-2 my-4",
        )

    # Tags
    tags_el = Div()
    if goal.tags:
        tag_badges = [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in goal.tags]
        tags_el = Div(
            Small("Tags", cls="text-muted-foreground block mb-2"),
            *tag_badges,
            cls="my-4",
        )

    # Milestones section
    milestones_section = Div()
    if goal.milestones:
        milestones_section = MilestonesSection(goal.milestones)

    # Connections section — grouped by domain (gravity well view)
    conn_section = Div()
    if connections:
        conn_section = ConnectionsSection(connections, _CONNECTION_LABELS)

    # Dual-track self-assessment (perception gap + trend) — ADR-030
    dual_track_section = DualTrackSection(
        domain="goals",
        entity_uid=goal.uid,
        level_enum=ProgressLevel,
        label="Progress",
        prompt="How much progress do you feel you've made toward this goal?",
        checkins=goal.dual_track_checkins,
    )

    # Lateral relationships (Vis.js graph, blocking chain, alternatives)
    relationships = EntityRelationshipsSection(
        entity_uid=goal.uid,
        entity_type="goals",
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
        cls="max-w-3xl mx-auto px-4",
    )


def MilestonesSection(milestones: tuple["Milestone", ...]) -> "FT":
    """Visual checklist of goal milestones."""
    items: list[Any] = []
    for ms in milestones:
        icon = "check" if ms.is_completed else "circle"
        icon_cls = "text-green-600" if ms.is_completed else "text-muted-foreground"
        text_cls = "line-through text-muted-foreground" if ms.is_completed else ""

        date_str = ""
        if ms.target_date:
            date_str = f" · {ms.target_date}"
        if ms.achieved_date:
            date_str = f" · Achieved {ms.achieved_date}"

        items.append(
            Li(
                Icon(icon, size=16, cls=f"inline mr-2 {icon_cls}"),
                Span(ms.title, cls=text_cls),
                Small(date_str, cls="text-muted-foreground") if date_str else "",
                cls="mb-2",
            )
        )

    return Div(
        section_label("Milestones"),
        Ul(*items, cls="space-y-2"),
        cls="my-4",
    )


# ConnectionsSection labels: connected_type -> (label, icon, href prefix).
_CONNECTION_LABELS: dict[str, tuple[str, str, str]] = {
    "task": ("Tasks fulfilling this goal", "check-square", "/tasks/detail?uid="),
    "habit": ("Habits supporting this goal", "repeat", "#"),
    "event": ("Events contributing", "calendar", "#"),
    "choice": ("Choices affecting this goal", "git-branch", "#"),
    "principle": ("Principles guiding this goal", "compass", "#"),
    "ku": ("Knowledge connected", "atom", "/explore/ku/"),
}
