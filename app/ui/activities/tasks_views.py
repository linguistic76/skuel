"""Tasks UI view components.

Pure FastHTML components for rendering task data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.tasks_views import TaskList, TaskStatsBar
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Div,
    Form,
    P,
    Small,
    Span,
)

from core.utils.activity_stats import compute_task_stats
from ui.activities._shared import (
    ActivityList,
    ConnectionBadges,
    MetadataField,
    PriorityBadgeDropdown,
    safe_id,
)
from ui.components import Button, ButtonT, Card, Icon
from ui.feedback import Badge, BadgeT, PriorityBadge, StatusBadge
from ui.forms import Input
from ui.layout import Container, DivHStacked
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import section_label

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.task.task import Task


def TaskStatsBar(tasks: list["Task"]) -> "FT":
    """Quick stats bar showing task counts by status."""
    s = compute_task_stats(tasks)
    stats = [
        StatItem(label="Total", value=s.total, href="/tasks?status=all"),
        StatItem(label="Active", value=s.active, color="primary", href="/tasks?status=active"),
        StatItem(
            label="Completed", value=s.completed, color="success", href="/tasks?status=completed"
        ),
        StatItem(
            label="Overdue",
            value=s.overdue,
            color="error" if s.overdue > 0 else None,
            href="/tasks?status=overdue",
        ),
    ]
    return StatsGrid(stats, cols=4)


def TaskList(
    tasks: list["Task"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of task cards. Returns a replaceable container for HTMX."""
    return ActivityList(tasks, "task", TaskCard, connections_map)


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
        Icon(
            "check" if is_completed else "circle",
            size=16,
            cls=f"inline {'text-green-600' if is_completed else ''}",
        ),
        hx_post=f"/api/tasks/{task.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#task-{safe_id(task.uid)}",
        hx_swap="outerHTML",
        cls=(ButtonT.default, "rounded"),
        size="sm",
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
    badges.append(
        PriorityBadgeDropdown(
            task.uid,
            str(task.priority) if task.priority else None,
            domain="tasks",
            singular="task",
        )
    )
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
        header,
        id=f"task-{safe_id(task.uid)}",
        cls=f"mb-2 p-3 {'opacity-75' if is_completed else ''}",
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


def SubtaskSection(task_uid: str) -> "FT":
    """Section shell that HTMX auto-loads the subtask list on page render."""
    list_id = f"subtasks-list-{safe_id(task_uid)}"
    return Div(
        section_label("Sub-tasks"),
        Div(
            id=list_id,
            hx_get=f"/tasks/subtasks?uid={task_uid}",
            hx_trigger="load",
            hx_swap="outerHTML",
        ),
        cls="my-4",
    )


def SubtaskListFragment(
    parent_uid: str,
    parent: "Task | None",
    children: "list[Task]",
) -> "FT":
    """Replaceable HTMX fragment: parent breadcrumb + child rows + quick-add form."""
    list_id = f"subtasks-list-{safe_id(parent_uid)}"

    parent_el: Any = ""
    if parent:
        parent_el = Div(
            Icon("corner-left-up", size=13, cls="flex-none text-muted-foreground"),
            A(
                parent.title or parent.uid,
                href=f"/tasks/detail?uid={parent.uid}",
                cls="text-xs text-muted-foreground hover:underline",
            ),
            cls="flex items-center gap-1.5 mb-3",
        )

    rows: list[Any] = (
        [_subtask_row(t) for t in children]
        if children
        else [P("No sub-tasks yet.", cls="text-sm text-muted-foreground py-1")]
    )

    add_form = Form(
        DivHStacked(
            Input(
                type="text",
                name="title",
                placeholder="Add sub-task…",
                required=True,
                cls="flex-1 min-w-0",
            ),
            Input(type="hidden", name="parent_uid", value=parent_uid),
            Button("Add", type="submit", cls=ButtonT.primary, size="sm"),
        ),
        hx_post="/tasks/subtasks/add",
        hx_target=f"#{list_id}",
        hx_swap="outerHTML",
        cls="mt-3 pt-3 border-t border-border",
    )

    return Div(
        parent_el,
        *rows,
        add_form,
        id=list_id,
        hx_get=f"/tasks/subtasks?uid={parent_uid}",
        hx_trigger="refresh",
        hx_swap="outerHTML",
    )


def _subtask_row(task: "Task") -> "FT":
    """Compact row: status indicator + title link to the task's own detail page."""
    is_completed = task.status and task.status.value == "completed"
    icon_cls = f"flex-none {'text-success' if is_completed else 'text-muted-foreground'}"
    title_cls = "text-sm line-through text-muted-foreground" if is_completed else "text-sm"
    return Div(
        Icon(
            "check-circle" if is_completed else "circle",
            size=14,
            cls=icon_cls,
        ),
        A(
            task.title or "Untitled",
            href=f"/tasks/detail?uid={task.uid}",
            cls=f"{title_cls} hover:underline",
        ),
        cls="flex items-center gap-2 py-1.5",
    )


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
            section_label("Connections"),
            conn_badges,
            cls="my-4",
        )

    # Sub-tasks (HTMX-loaded: parent breadcrumb + children + quick-add)
    subtasks = SubtaskSection(task.uid)

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
        subtasks,
        relationships,
        size="3xl",
    )
