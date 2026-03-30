"""Tasks UI view components.

Pure FastHTML components for rendering task data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.tasks_views import TaskList, TaskFilterBar, TaskStatsBar
"""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Button,
    Div,
    Form,
    Label,
    Option,
    Select,
    Small,
    Span,
)

from ui.feedback import PriorityBadge, StatusBadge
from ui.patterns.empty_state import EmptyState
from ui.patterns.stats_grid import StatItem, StatsGrid

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
    overdue = sum(1 for t in tasks if _is_overdue(t))

    stats = [
        StatItem(label="Total", value=total),
        StatItem(label="Active", value=active, color="primary"),
        StatItem(label="Completed", value=completed, color="success"),
        StatItem(label="Overdue", value=overdue, color="error" if overdue > 0 else None),
    ]
    return StatsGrid(stats, cols=4)


def TaskFilterBar(
    status_filter: str = "active",
    priority_filter: str = "all",
    sort_by: str = "priority",
) -> "FT":
    """Filter and sort controls for the task list. HTMX-powered."""
    return Form(
        Div(
            Div(
                Label("Status", cls="uk-form-label"),
                Select(
                    Option("Active", value="active", selected=status_filter == "active"),
                    Option("Completed", value="completed", selected=status_filter == "completed"),
                    Option("All", value="all", selected=status_filter == "all"),
                    name="status",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            Div(
                Label("Priority", cls="uk-form-label"),
                Select(
                    Option("All", value="all", selected=priority_filter == "all"),
                    Option("Critical", value="critical", selected=priority_filter == "critical"),
                    Option("High", value="high", selected=priority_filter == "high"),
                    Option("Medium", value="medium", selected=priority_filter == "medium"),
                    Option("Low", value="low", selected=priority_filter == "low"),
                    name="priority",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            Div(
                Label("Sort", cls="uk-form-label"),
                Select(
                    Option("Priority", value="priority", selected=sort_by == "priority"),
                    Option("Due Date", value="due_date", selected=sort_by == "due_date"),
                    Option("Recently Updated", value="updated", selected=sort_by == "updated"),
                    Option("Title", value="title", selected=sort_by == "title"),
                    name="sort_by",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            cls="uk-grid uk-grid-small uk-child-width-1-3@s uk-child-width-auto@m",
            **{"uk-grid": "true"},
        ),
        hx_get="/tasks/list-fragment",
        hx_target="#task-list",
        hx_trigger="change",
        hx_include="[name]",
        cls="uk-margin-bottom",
    )


def TaskList(
    tasks: list["Task"],
    knowledge_map: dict[str, list[dict[str, str]]] | None = None,
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
        TaskCard(task, knowledge_map.get(task.uid, []) if knowledge_map else []) for task in tasks
    ]
    return Div(*cards, id="task-list", cls="uk-margin-top")


def TaskCard(
    task: "Task",
    knowledge_connections: list[dict[str, str]] | None = None,
) -> "FT":
    """Single task card with status toggle, priority, due date, and connections."""
    is_completed = task.status and task.status.value == "completed"
    overdue = _is_overdue(task)

    # Status toggle button
    new_status = "active" if is_completed else "completed"
    toggle_btn = Button(
        Span(
            cls=f"uk-icon {'uk-text-success' if is_completed else ''}",
            **{"uk-icon": "check" if is_completed else "circle"},
        ),
        hx_post=f"/api/tasks/{task.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#task-{_safe_id(task.uid)}",
        hx_swap="outerHTML",
        cls="uk-button uk-button-default uk-button-small uk-border-rounded",
        title=f"Mark as {new_status}",
    )

    # Title
    title_cls = "uk-text-muted uk-text-line-through" if is_completed else ""
    title_el = Span(task.title or "Untitled", cls=title_cls)

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
        due_cls = "uk-text-danger uk-text-bold" if overdue else "uk-text-muted"
        due_el = Small(f"Due: {due_str}", cls=due_cls)

    # Tags
    tags_el = None
    if task.tags:
        tag_badges = [
            Span(tag, cls="uk-badge uk-badge-secondary uk-margin-small-right")
            for tag in task.tags[:5]
        ]
        tags_el = Div(*tag_badges, cls="uk-margin-small-top")

    # Knowledge connections
    knowledge_el = None
    if knowledge_connections:
        links = [
            A(
                conn.get("title", conn.get("uid", "?")),
                href=f"/ku/get?uid={conn['uid']}" if conn.get("uid", "").startswith("ku") else "#",
                cls="uk-link-muted uk-margin-small-right",
            )
            for conn in knowledge_connections
        ]
        knowledge_el = Div(
            Small("Applies: ", cls="uk-text-muted"),
            *links,
            cls="uk-margin-small-top",
        )
    elif task.fulfills_goal_uid:
        knowledge_el = Div(
            Small(f"Goal: {task.fulfills_goal_uid}", cls="uk-text-muted"),
            cls="uk-margin-small-top",
        )

    # Duration
    duration_el = None
    if task.duration_minutes:
        duration_el = Small(
            f"{task.duration_minutes} min", cls="uk-text-muted uk-margin-small-left"
        )

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            Div(title_el, duration_el, cls="uk-flex uk-flex-middle uk-flex-wrap"),
            Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-top")
            if badges
            else "",
            due_el or "",
            tags_el or "",
            knowledge_el or "",
            cls="uk-margin-small-left uk-width-expand",
        ),
        cls="uk-flex uk-flex-top",
    )

    return Div(
        header,
        id=f"task-{_safe_id(task.uid)}",
        cls=f"uk-card uk-card-default uk-card-body uk-card-small uk-margin-small-bottom {'uk-opacity-75' if is_completed else ''}",
    )


def _is_overdue(task: "Task") -> bool:
    """Check if a task is overdue (has due_date in the past and not completed)."""
    if not task.due_date:
        return False
    if task.status and task.status.value == "completed":
        return False
    try:
        if isinstance(task.due_date, date):
            return task.due_date < date.today()
        due = datetime.fromisoformat(str(task.due_date)).date()
        return due < date.today()
    except (ValueError, TypeError):
        return False


def _safe_id(uid: str) -> str:
    """Convert a UID to a safe HTML id attribute value."""
    return uid.replace(".", "-").replace(":", "-")


_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _sort_by_priority(task: "Task") -> int:
    """Sort key: priority order (critical first)."""
    return _PRIORITY_ORDER.get(str(task.priority) if task.priority else "", 4)


def _sort_by_due_date(task: "Task") -> str:
    """Sort key: due date ascending (no date sorts last)."""
    return str(task.due_date or "9999-12-31")


def _sort_by_title(task: "Task") -> str:
    """Sort key: title alphabetically."""
    return (task.title or "").lower()


def _sort_by_updated(task: "Task") -> str:
    """Sort key: updated_at descending."""
    return str(task.updated_at or "")


def filter_tasks(
    tasks: list["Task"],
    status_filter: str = "active",
    priority_filter: str = "all",
    sort_by: str = "priority",
) -> list["Task"]:
    """Apply filters and sorting to a task list.

    Args:
        tasks: Full list of user tasks
        status_filter: "active", "completed", or "all"
        priority_filter: "critical", "high", "medium", "low", or "all"
        sort_by: "priority", "due_date", "updated", or "title"

    Returns:
        Filtered and sorted task list
    """
    filtered = list(tasks)

    # Status filter
    if status_filter == "active":
        filtered = [
            t
            for t in filtered
            if not t.status
            or t.status.value in ("active", "in_progress", "ready", "draft", "blocked")
        ]
    elif status_filter == "completed":
        filtered = [t for t in filtered if t.status and t.status.value == "completed"]

    # Priority filter
    if priority_filter != "all":
        filtered = [t for t in filtered if t.priority and str(t.priority) == priority_filter]

    # Sort
    if sort_by == "priority":
        filtered.sort(key=_sort_by_priority)
    elif sort_by == "due_date":
        filtered.sort(key=_sort_by_due_date)
    elif sort_by == "title":
        filtered.sort(key=_sort_by_title)
    elif sort_by == "updated":
        filtered.sort(key=_sort_by_updated, reverse=True)

    return filtered
