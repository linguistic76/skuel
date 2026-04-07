"""Tasks UI view components.

Pure FastHTML components for rendering task data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.tasks_views import TaskList, TASK_FILTER_CONFIG, TaskStatsBar
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Div,
    P,
    Small,
    Span,
)
from monsterui.franken import UkIcon  # type: ignore[import-untyped]

from ui.activities._shared import ConnectionBadges, MetadataField, safe_id
from ui.activities.filter_bar import FilterBarConfig, FilterSelect
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT, PriorityBadge, StatusBadge
from ui.layout import Container, DivHStacked
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.text import SectionTitle

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.task.task import Task


def TaskStatsBar(tasks: list["Task"]) -> "FT":
    """Quick stats bar showing task counts by status."""
    total = len(tasks)
    active = sum(
        1 for t in tasks if t.status and t.status.value in ("active", "in_progress", "ready")
    )
    completed = sum(1 for t in tasks if t.status and t.status.value == "completed")
    overdue = sum(1 for t in tasks if t.is_overdue())

    stats = [
        StatItem(label="Total", value=total, href="/tasks?status=all"),
        StatItem(label="Active", value=active, color="primary", href="/tasks?status=active"),
        StatItem(
            label="Completed", value=completed, color="success", href="/tasks?status=completed"
        ),
        StatItem(
            label="Overdue",
            value=overdue,
            color="error" if overdue > 0 else None,
            href="/tasks?status=overdue",
        ),
    ]
    return StatsGrid(stats, cols=4)


TASK_FILTER_CONFIG = FilterBarConfig(
    fragment_url="/tasks/list-fragment",
    list_target_id="task-list",
    filters=[
        FilterSelect(
            name="status",
            label="Status",
            options=[
                ("Active", "active"),
                ("Completed", "completed"),
                ("Overdue", "overdue"),
                ("All", "all"),
            ],
            default="active",
        ),
        FilterSelect(
            name="priority",
            label="Priority",
            options=[
                ("All", "all"),
                ("Critical", "critical"),
                ("High", "high"),
                ("Medium", "medium"),
                ("Low", "low"),
            ],
            default="all",
        ),
    ],
    sort_options=[
        ("Priority", "priority"),
        ("Due Date", "due_date"),
        ("Recently Updated", "updated"),
        ("Title", "title"),
    ],
    sort_default="priority",
)


def TaskList(
    tasks: list["Task"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of task cards. Returns a replaceable container for HTMX."""
    if not tasks:
        return Div(
            EmptyState(
                title="No tasks found",
                description="Upload YAML files to add tasks, or adjust your filters.",
                action_text="Upload Tasks",
                action_href="/upload",
            ),
            id="task-list",
        )

    cards = [
        TaskCard(task, connections_map.get(task.uid, []) if connections_map else [])
        for task in tasks
    ]
    return Div(*cards, id="task-list", cls="mt-4 space-y-3")


def TaskCard(
    task: "Task",
    knowledge_connections: list[dict[str, str]] | None = None,
) -> "FT":
    """Single task card with status toggle, priority, due date, and connections."""
    is_completed = task.status and task.status.value == "completed"
    overdue = task.is_overdue()

    # Status toggle button
    new_status = "active" if is_completed else "completed"
    toggle_btn = Button(
        UkIcon(
            "check" if is_completed else "circle",
            height=16,
            width=16,
            cls=f"inline {'text-green-600' if is_completed else ''}",
        ),
        hx_post=f"/api/tasks/{task.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#task-{safe_id(task.uid)}",
        hx_swap="outerHTML",
        variant=ButtonT.neutral,
        size="sm",
        cls="rounded",
        title=f"Mark as {new_status}",
    )

    # Title — clickable link to detail page
    title_cls = "text-muted-foreground line-through" if is_completed else ""
    title_el = A(
        task.title or "Untitled",
        href=f"/tasks/detail?uid={task.uid}",
        cls=f"hover:underline {title_cls}",
    )

    # Badges row
    badges: list[Any] = []
    if task.priority:
        badges.append(PriorityBadge(str(task.priority)))
    if task.status:
        badges.append(StatusBadge(str(task.status)))

    # Due date
    due_el = None
    if task.due_date:
        due_str = str(task.due_date)
        due_cls = "text-destructive font-bold" if overdue else "text-muted-foreground"
        due_el = Small(f"Due: {due_str}", cls=due_cls)

    # Tags
    tags_el = None
    if task.tags:
        tag_badges = [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in task.tags[:5]]
        tags_el = Div(*tag_badges, cls="mt-2")

    # Cross-domain connection badges
    knowledge_el = _task_connection_badges(task, knowledge_connections or [])

    # Duration
    duration_el = None
    if task.duration_minutes:
        duration_el = Small(f"{task.duration_minutes} min", cls="text-muted-foreground ml-2")

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            DivHStacked(title_el, duration_el, cls="flex-wrap"),
            DivHStacked(*badges, cls="flex-wrap mt-2") if badges else "",
            due_el or "",
            tags_el or "",
            knowledge_el or "",
            cls="ml-2 flex-1 min-w-0",
        ),
        cls="flex items-start",
    )

    return Card(
        CardBody(header, cls="p-3"),
        id=f"task-{safe_id(task.uid)}",
        cls=f"mb-2 {'opacity-75' if is_completed else ''}",
    )




def _task_connection_badges(
    task: "Task",
    connections: list[dict[str, str]],
) -> "FT":
    """Connection badges with task-specific fallback to fulfills_goal_uid."""
    if connections:
        return ConnectionBadges(connections)

    # Fallback to model field if no connection data was fetched
    if task.fulfills_goal_uid:
        return ConnectionBadges(
            [
                {
                    "connected_type": "goal",
                    "title": task.fulfills_goal_uid,
                    "connected_uid": task.fulfills_goal_uid,
                }
            ]
        )

    return Span()


def TaskDetailView(
    task: "Task",
    connections: list[dict[str, str]],
) -> "FT":
    """Full detail page for a single task."""
    # Header badges
    badges: list[Any] = []
    if task.priority:
        badges.append(PriorityBadge(str(task.priority)))
    if task.status:
        badges.append(StatusBadge(str(task.status)))

    subtitle_parts: list[str] = []
    if task.status:
        subtitle_parts.append(str(task.status).replace("_", " ").title())
    if task.priority:
        subtitle_parts.append(f"{str(task.priority).title()} priority")
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

    header = PageHeader(task.title or "Untitled Task", subtitle=subtitle)

    # Description
    desc_el = Div()
    if task.description:
        desc_el = Div(
            P(task.description),
            cls="my-4",
        )

    # Metadata grid
    meta_items: list[Any] = []
    if task.due_date:
        overdue = task.is_overdue()
        due_cls = "text-destructive font-bold" if overdue else ""
        meta_items.append(MetadataField("Due Date", Span(str(task.due_date), cls=due_cls)))
    if task.duration_minutes:
        meta_items.append(MetadataField("Duration", Span(f"{task.duration_minutes} min")))
    if task.project:
        meta_items.append(MetadataField("Project", Span(str(task.project))))
    if task.created_at:
        meta_items.append(MetadataField("Created", Span(str(task.created_at)[:10])))

    meta_grid = Div()
    if meta_items:
        meta_grid = Div(
            *meta_items,
            cls="grid grid-cols-2 sm:grid-cols-4 gap-2 my-4",
        )

    # Tags
    tags_el = Div()
    if task.tags:
        tag_badges = [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in task.tags]
        tags_el = Div(
            Small("Tags", cls="text-muted-foreground block mb-2"),
            *tag_badges,
            cls="my-4",
        )

    # Connections section
    conn_section = Div()
    conn_badges = _task_connection_badges(task, connections)
    if connections or task.fulfills_goal_uid:
        conn_section = Div(
            SectionTitle("Connections"),
            conn_badges,
            cls="my-4",
        )

    # Lateral relationships (Vis.js graph, blocking chain, alternatives)
    relationships = EntityRelationshipsSection(
        entity_uid=task.uid,
        entity_type="tasks",
    )

    return Container(
        header,
        DivHStacked(*badges, cls="flex-wrap mb-2") if badges else "",
        desc_el,
        meta_grid,
        tags_el,
        conn_section,
        relationships,
        size="3xl",
    )


