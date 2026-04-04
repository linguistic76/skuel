"""Goals UI view components.

Pure FastHTML components for rendering goal data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.goals_views import GoalList, GoalFilterBar, GoalStatsBar
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
    A,
    Div,
    Form,
    Label,
    Li,
    Option,
    P,
    Select,
    Small,
    Span,
    Ul,
)

from ui.activities._shared import PRIORITY_ORDER, ConnectionSummary, MetadataField, safe_id
from ui.feedback import PriorityBadge, StatusBadge
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.goal.goal import Goal
    from core.models.goal.milestone import Milestone


def GoalStatsBar(goals: list["Goal"]) -> "FT":
    """Quick stats bar showing goal counts by status.

    "Wobbly" is the opposite of "On Track" — goals that need attention:
    behind schedule (progress < expected) or overdue (past target date).
    """
    total = len(goals)
    active = sum(1 for g in goals if g.status and g.status.value in ("active", "in_progress"))
    on_track = sum(1 for g in goals if g.is_on_track() and not g.is_completed)
    completed = sum(1 for g in goals if g.is_completed)

    # Wobbly = goals that are NOT on track and NOT completed
    overdue = [g for g in goals if g.is_overdue()]
    behind = [g for g in goals if not g.is_on_track() and not g.is_completed and not g.is_overdue()]
    wobbly_count = len(overdue) + len(behind)

    # Build a breakdown sub-label for the Wobbly card
    wobbly_detail = None
    if wobbly_count > 0:
        parts = []
        if behind:
            parts.append(f"{len(behind)} behind")
        if overdue:
            parts.append(f"{len(overdue)} overdue")
        wobbly_detail = ", ".join(parts)

    stats = [
        StatItem(label="Total", value=total, href="/goals?status=all"),
        StatItem(label="Active", value=active, color="primary", href="/goals?status=active"),
        StatItem(label="On Track", value=on_track, color="success", href="/goals?status=on_track"),
        StatItem(
            label="Completed", value=completed, color="success", href="/goals?status=completed"
        ),
        StatItem(
            label="Wobbly",
            value=wobbly_count,
            color="error" if wobbly_count > 0 else None,
            change=wobbly_detail,
            trend="down" if wobbly_count > 0 else None,
            href="/goals?status=wobbly",
        ),
    ]
    return StatsGrid(stats, cols=5)


def GoalFilterBar(
    status_filter: str = "active",
    sort_by: str = "target_date",
) -> "FT":
    """Filter and sort controls for the goal list. HTMX-powered."""
    return Form(
        Div(
            Div(
                Label("Status", cls="uk-form-label"),
                Select(
                    Option("Active", value="active", selected=status_filter == "active"),
                    Option("On Track", value="on_track", selected=status_filter == "on_track"),
                    Option("Wobbly", value="wobbly", selected=status_filter == "wobbly"),
                    Option("Completed", value="completed", selected=status_filter == "completed"),
                    Option("All", value="all", selected=status_filter == "all"),
                    name="status",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            Div(
                Label("Sort", cls="uk-form-label"),
                Select(
                    Option("Target Date", value="target_date", selected=sort_by == "target_date"),
                    Option("Priority", value="priority", selected=sort_by == "priority"),
                    Option("Progress", value="progress", selected=sort_by == "progress"),
                    Option("Title", value="title", selected=sort_by == "title"),
                    name="sort_by",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            cls="uk-grid uk-grid-small uk-child-width-1-2@s uk-child-width-auto@m",
            **{"uk-grid": "true"},
        ),
        hx_get="/goals/list-fragment",
        hx_target="#goal-list",
        hx_trigger="change",
        hx_include="[name]",
        cls="uk-margin-bottom",
    )


def GoalList(
    goals: list["Goal"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of goal cards. Returns a replaceable container for HTMX."""
    if not goals:
        return Div(
            EmptyState(
                title="No goals found",
                description="Upload YAML files to add goals, or adjust your filters.",
                action_text="Upload Goals",
                action_href="/upload",
            ),
            id="goal-list",
        )

    cards = [
        GoalCard(goal, connections_map.get(goal.uid, []) if connections_map else [])
        for goal in goals
    ]
    return Div(*cards, id="goal-list", cls="uk-margin-top")


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
    title_cls = "uk-text-muted uk-text-line-through" if goal.is_completed else ""
    title_el = A(
        goal.title or "Untitled",
        href=f"/goals/detail?uid={goal.uid}",
        cls=f"uk-link-text {title_cls}",
    )

    # Badges row
    badges: list[Any] = []
    if goal.priority:
        badges.append(PriorityBadge(str(goal.priority)))
    if goal.status:
        badges.append(StatusBadge(str(goal.status)))
    if goal.timeframe:
        badges.append(
            Span(
                str(goal.timeframe.value).replace("_", " ").title(),
                cls="uk-badge",
            )
        )

    # Progress bar
    bar_color = "uk-progress-success" if on_track else "uk-progress-warning"
    if goal.is_completed:
        bar_color = "uk-progress-success"
    elif overdue:
        bar_color = "uk-progress-danger"

    progress_el = Div(
        Div(
            Span(f"{progress_pct}%", cls="uk-text-small uk-text-muted"),
            Div(
                Div(
                    style=f"width: {progress_pct}%",
                    cls=f"uk-progress-bar {bar_color}",
                ),
                cls="uk-progress uk-margin-remove",
                style="height: 6px;",
            ),
            cls="uk-width-expand",
        ),
        cls="uk-margin-small-top",
    )

    # Target date
    date_el = Span()
    if goal.target_date:
        date_cls = "uk-text-danger uk-text-bold" if overdue else "uk-text-muted"
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
            Div(title_el, cls="uk-flex uk-flex-middle uk-flex-wrap"),
            Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-top")
            if badges
            else "",
            date_el,
            progress_el,
            conn_summary,
            cls="uk-width-expand",
        ),
        cls="uk-flex uk-flex-top",
    )

    return Div(
        header,
        id=f"goal-{safe_id(goal.uid)}",
        cls=f"uk-card uk-card-default uk-card-body uk-card-small uk-margin-small-bottom {'uk-opacity-75' if goal.is_completed else ''}",
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
    track_cls = "uk-text-success" if on_track else "uk-text-warning"
    track_text = "On Track" if on_track else "Behind"
    if goal.is_completed:
        track_cls = "uk-text-success"
        track_text = "Completed"
    elif goal.is_overdue():
        track_cls = "uk-text-danger"
        track_text = "Overdue"

    progress_section = Div(
        Div(
            Span(f"{progress_pct}%", cls="uk-text-large uk-text-bold"),
            Span(f" · {track_text}", cls=f"uk-text-small {track_cls}"),
            cls="uk-margin-small-bottom",
        ),
        Div(
            Div(
                style=f"width: {progress_pct}%",
                cls="uk-progress-bar uk-progress-success"
                if on_track
                else "uk-progress-bar uk-progress-warning",
            ),
            cls="uk-progress",
            style="height: 10px;",
        ),
        cls="uk-margin",
    )

    # Description and motivation fields
    text_sections: list[Any] = []
    if goal.description:
        text_sections.append(Div(P(goal.description, cls="uk-text-default"), cls="uk-margin"))
    if goal.vision_statement:
        text_sections.append(
            Div(MetadataField("Vision", P(goal.vision_statement, cls="uk-text-default")), cls="uk-margin")
        )
    if goal.why_important:
        text_sections.append(
            Div(MetadataField("Why Important", P(goal.why_important, cls="uk-text-default")), cls="uk-margin")
        )
    if goal.success_criteria:
        text_sections.append(
            Div(MetadataField("Success Criteria", P(goal.success_criteria, cls="uk-text-default")), cls="uk-margin")
        )

    # Metadata grid
    meta_items: list[Any] = []
    if goal.target_date:
        overdue = goal.is_overdue()
        due_cls = "uk-text-danger uk-text-bold" if overdue else ""
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
            cls="uk-grid uk-grid-small uk-child-width-1-2@s uk-child-width-1-4@m uk-margin",
            **{"uk-grid": "true"},
        )

    # Tags
    tags_el = Div()
    if goal.tags:
        tag_badges = [
            Span(tag, cls="uk-badge uk-badge-secondary uk-margin-small-right") for tag in goal.tags
        ]
        tags_el = Div(
            Small("Tags", cls="uk-text-muted uk-display-block uk-margin-small-bottom"),
            *tag_badges,
            cls="uk-margin",
        )

    # Milestones section
    milestones_section = Div()
    if goal.milestones:
        milestones_section = MilestonesSection(goal.milestones)

    # Connections section — grouped by domain (gravity well view)
    conn_section = Div()
    if connections:
        conn_section = GoalConnectionsSection(connections)

    # Lateral relationships (Vis.js graph, blocking chain, alternatives)
    relationships = EntityRelationshipsSection(
        entity_uid=goal.uid,
        entity_type="goals",
    )

    return Div(
        header,
        Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-bottom")
        if badges
        else "",
        progress_section,
        *text_sections,
        meta_grid,
        tags_el,
        milestones_section,
        conn_section,
        relationships,
        cls="uk-container uk-container-small",
    )


def MilestonesSection(milestones: tuple["Milestone", ...]) -> "FT":
    """Visual checklist of goal milestones."""
    items: list[Any] = []
    for ms in milestones:
        icon = "check" if ms.is_completed else "circle"
        icon_cls = "uk-text-success" if ms.is_completed else "uk-text-muted"
        text_cls = "uk-text-line-through uk-text-muted" if ms.is_completed else ""

        date_str = ""
        if ms.target_date:
            date_str = f" · {ms.target_date}"
        if ms.achieved_date:
            date_str = f" · Achieved {ms.achieved_date}"

        items.append(
            Li(
                Span(cls=f"uk-icon {icon_cls} uk-margin-small-right", **{"uk-icon": icon}),
                Span(ms.title, cls=text_cls),
                Small(date_str, cls="uk-text-muted") if date_str else "",
                cls="uk-margin-small-bottom",
            )
        )

    return Div(
        H3("Milestones", cls="uk-heading-small"),
        Ul(*items, cls="uk-list"),
        cls="uk-margin",
    )


def GoalConnectionsSection(connections: list[dict[str, str]]) -> "FT":
    """Display connections grouped by domain: tasks fulfilling, habits supporting, etc."""
    # Group by source_type
    groups: dict[str, list[dict[str, str]]] = {}
    for conn in connections:
        source_type = conn.get("source_type", "unknown")
        if source_type not in groups:
            groups[source_type] = []
        groups[source_type].append(conn)

    domain_labels = {
        "task": ("Tasks fulfilling this goal", "check-square", "/tasks/detail?uid="),
        "habit": ("Habits supporting this goal", "repeat", "#"),
        "event": ("Events contributing", "calendar", "#"),
        "choice": ("Choices affecting this goal", "git-branch", "#"),
        "principle": ("Principles guiding this goal", "compass", "#"),
        "ku": ("Knowledge connected", "atom", "/ku/get?uid="),
    }

    sections: list[Any] = []
    for domain, conns in groups.items():
        label, icon, base_href = domain_labels.get(
            domain, (f"{domain.title()} connections", "link", "#")
        )
        links = [
            Li(
                Span(
                    cls="uk-icon uk-margin-small-right", **{"uk-icon": f"icon: {icon}; ratio: 0.75"}
                ),
                A(
                    conn.get("title", conn.get("source_uid", "?")),
                    href=f"{base_href}{conn.get('source_uid', '')}" if base_href != "#" else "#",
                    cls="uk-link-muted",
                ),
            )
            for conn in conns
        ]
        sections.append(
            Div(
                Small(
                    label,
                    cls="uk-text-muted uk-text-uppercase uk-text-small uk-display-block uk-margin-small-bottom",
                ),
                Ul(*links, cls="uk-list uk-list-divider"),
                cls="uk-margin-small-bottom",
            )
        )

    return Div(
        H3("Connections", cls="uk-heading-small"),
        *sections,
        cls="uk-margin",
    )


def _sort_by_priority(goal: "Goal") -> int:
    """Sort key: priority order (critical first)."""
    return PRIORITY_ORDER.get(str(goal.priority) if goal.priority else "", 4)


def _sort_by_target_date(goal: "Goal") -> str:
    """Sort key: target_date ascending (no date sorts last)."""
    return str(goal.target_date or "9999-12-31")


def _sort_by_progress(goal: "Goal") -> float:
    """Sort key: progress descending."""
    return -goal.calculate_progress()


def _sort_by_title(goal: "Goal") -> str:
    """Sort key: title alphabetically."""
    return (goal.title or "").lower()


def filter_goals(
    goals: list["Goal"],
    status_filter: str = "active",
    sort_by: str = "target_date",
) -> list["Goal"]:
    """Apply filters and sorting to a goal list."""
    filtered = list(goals)

    # Status filter
    if status_filter == "active":
        filtered = [
            g
            for g in filtered
            if not g.status or g.status.value in ("active", "in_progress", "not_started", "ready")
        ]
    elif status_filter == "completed":
        filtered = [g for g in filtered if g.is_completed]
    elif status_filter == "on_track":
        filtered = [g for g in filtered if g.is_on_track() and not g.is_completed]
    elif status_filter == "wobbly":
        filtered = [g for g in filtered if not g.is_on_track() and not g.is_completed]

    # Sort
    if sort_by == "target_date":
        filtered.sort(key=_sort_by_target_date)
    elif sort_by == "priority":
        filtered.sort(key=_sort_by_priority)
    elif sort_by == "progress":
        filtered.sort(key=_sort_by_progress)
    elif sort_by == "title":
        filtered.sort(key=_sort_by_title)

    return filtered
