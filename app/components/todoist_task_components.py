"""
Todoist-Style Task Components
=============================

Minimal, practical task management UI inspired by Todoist.

Design Principles:
- Zero-friction capture (quick-add always visible)
- Clean visual hierarchy (priority flags, not badges)
- HTMX-powered interactions (instant feedback)
- DaisyUI/Tailwind styling

Usage:
    from components.todoist_task_components import TodoistTaskComponents

    dashboard = TodoistTaskComponents.render_dashboard(tasks, projects, filters)
"""

from datetime import date
from typing import Any

from fasthtml.common import (
    H1,
    H3,
    Button,
    Datalist,
    Div,
    Form,
    Input,
    Label,
    Li,
    NotStr,
    Option,
    P,
    Script,
    Select,
    Span,
    Textarea,
    Ul,
)

from core.models.shared_enums import ActivityStatus, Priority
from core.utils.logging import get_logger

logger = get_logger("skuel.components.todoist")


# Priority to P1-P4 mapping (Todoist style)
PRIORITY_TO_P = {
    Priority.CRITICAL: ("P1", "text-red-500", "fill-red-500"),
    Priority.HIGH: ("P2", "text-orange-500", "fill-orange-500"),
    Priority.MEDIUM: ("P3", "text-blue-500", "fill-blue-500"),
    Priority.LOW: ("P4", "text-gray-400", "fill-gray-400"),
}


class TodoistTaskComponents:
    """
    Todoist-inspired task UI components.

    Core Features:
    - Quick-add form (always visible)
    - Priority flags (P1-P4 colored flags)
    - Project tags (@project badges)
    - HTMX-powered list updates
    """

    # ========================================================================
    # PRIORITY FLAGS
    # ========================================================================

    @staticmethod
    def render_priority_flag(priority: Priority | str) -> Any:
        """
        Render Todoist-style priority flag.

        P1 = Red (CRITICAL)
        P2 = Orange (HIGH)
        P3 = Blue (MEDIUM)
        P4 = Gray (LOW/MINIMAL)
        """
        if isinstance(priority, str):
            try:
                priority = Priority(priority)
            except ValueError:
                priority = Priority.LOW

        p_label, text_class, _fill_class = PRIORITY_TO_P.get(
            priority, ("P4", "text-gray-400", "fill-gray-400")
        )

        # Flag icon SVG - use NotStr to render raw HTML
        flag_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" class="w-4 h-4 {text_class}" fill="currentColor">
            <path d="M3.5 2v12.5a.5.5 0 0 1-1 0V2a.5.5 0 0 1 1 0z"/>
            <path d="M3.5 2h9.004a.5.5 0 0 1 .447.724l-2.5 5 2.5 5a.5.5 0 0 1-.447.724H3.5V2z"/>
        </svg>"""

        return Span(
            Span(NotStr(flag_svg), cls="inline-block"),
            Span(p_label, cls=f"text-xs font-medium ml-0.5 {text_class}"),
            cls="inline-flex items-center",
            title=f"Priority: {priority.value.title()}",
        )

    # ========================================================================
    # PROJECT TAG
    # ========================================================================

    @staticmethod
    def render_project_tag(project: str | None) -> Any:
        """Render @project tag badge."""
        if not project:
            return ""

        return Span(f"@{project}", cls="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded")

    # ========================================================================
    # ASSIGNEE TAG
    # ========================================================================

    @staticmethod
    def render_assignee_tag(assignee: str | None) -> Any:
        """Render assignee tag."""
        if not assignee:
            return ""

        return Span(assignee, cls="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded")

    # ========================================================================
    # DUE DATE DISPLAY
    # ========================================================================

    @staticmethod
    def render_due_date(due_date: date | None, is_completed: bool = False) -> Any:
        """
        Render due date with overdue styling.

        - Overdue: Red text
        - Today: Orange text
        - Future: Gray text
        - Completed: Strikethrough
        """
        if not due_date:
            return ""

        # Convert Neo4j Date to Python date if needed
        if hasattr(due_date, "to_native"):
            due_date = due_date.to_native()
        elif isinstance(due_date, str):
            try:
                due_date = date.fromisoformat(due_date)
            except ValueError:
                return ""

        today = date.today()

        if is_completed:
            cls = "text-xs text-gray-400 line-through"
            label = due_date.strftime("%b %d")
        elif due_date < today:
            cls = "text-xs text-red-500 font-medium"
            days_ago = (today - due_date).days
            label = f"Overdue ({days_ago}d)"
        elif due_date == today:
            cls = "text-xs text-orange-500 font-medium"
            label = "Today"
        else:
            cls = "text-xs text-gray-500"
            days_until = (due_date - today).days
            if days_until == 1:
                label = "Tomorrow"
            elif days_until <= 7:
                label = due_date.strftime("%a")  # e.g., "Mon"
            else:
                label = due_date.strftime("%b %d")  # e.g., "Dec 15"

        return Span(label, cls=cls)

    # ========================================================================
    # TASK LIST ITEM
    # ========================================================================

    @staticmethod
    def render_task_item(task: Any, user_uid: str | None = None) -> Any:
        """
        Render single task row in Todoist style.

        Layout: [checkbox] [clickable: title + @project + P1-4 + due + assignee]
        Clicking the row (not checkbox) opens edit modal via HTMX.
        """
        is_completed = task.status == ActivityStatus.COMPLETED

        # Checkbox - with click.stop to prevent triggering row click
        checkbox = Input(
            type="checkbox",
            checked=is_completed,
            cls="checkbox checkbox-sm",
            hx_post=f"/tasks/{task.uid}/toggle",
            hx_target=f"#task-{task.uid}",
            hx_swap="outerHTML",
            **{"x-on:click.stop": ""},  # Prevent click from bubbling to row
        )

        # Title (with strikethrough if completed)
        title_cls = "text-sm"
        if is_completed:
            title_cls += " line-through text-gray-400"

        # Title with optional description
        description = getattr(task, "description", None)
        if description:
            title_section = Div(
                Span(task.title, cls=title_cls),
                P(description, cls="text-xs text-gray-500 mt-0.5 line-clamp-1"),
                cls="flex-1 min-w-0",
            )
        else:
            title_section = Span(task.title, cls=f"{title_cls} flex-1 min-w-0")

        # Project tag
        project_tag = TodoistTaskComponents.render_project_tag(task.project)

        # Priority flag
        priority_flag = TodoistTaskComponents.render_priority_flag(task.priority)

        # Due date
        due_display = TodoistTaskComponents.render_due_date(task.due_date, is_completed)

        # Assignee
        assignee_tag = TodoistTaskComponents.render_assignee_tag(getattr(task, "assignee", None))

        # Row styling
        row_cls = "flex items-center gap-3 py-3 px-4 hover:bg-base-200/50 border-b border-base-200 transition-colors"
        if is_completed:
            row_cls += " opacity-60"

        # Clickable content area (excludes checkbox)
        # Remove any existing modal before fetching new one to avoid ID conflicts
        clickable_content = Div(
            title_section,
            Div(
                project_tag, priority_flag, due_display, assignee_tag, cls="flex items-center gap-2"
            ),
            cls="flex items-center gap-3 flex-1 cursor-pointer min-w-0",
            **{
                "hx-get": f"/tasks/edit-modal?uid={task.uid}",
                "hx-target": "body",
                "hx-swap": "beforeend",
                "hx-on::before-request": "var old = document.getElementById('task-edit-modal'); if (old) old.remove();",
            },
        )

        return Li(
            checkbox,
            clickable_content,
            id=f"task-{task.uid}",
            cls=row_cls,
        )

    # ========================================================================
    # TASK EDIT MODAL
    # ========================================================================

    @staticmethod
    def render_task_edit_modal(task: Any, projects: list[str] | None = None) -> Any:
        """
        Render task edit modal with form.

        Uses DaisyUI modal + Alpine.js for state management.
        Form submits via HTMX POST to /tasks/update endpoint.

        Args:
            task: Task entity to edit
            projects: List of project names for autocomplete
        """
        projects = projects or []

        # Project datalist for autocomplete
        project_options = [Option(value=p) for p in projects]
        project_datalist = Datalist(*project_options, id="edit-project-suggestions")

        # Status options
        current_status = getattr(task, "status", ActivityStatus.IN_PROGRESS)
        if hasattr(current_status, "value"):
            current_status_value = current_status.value
        else:
            current_status_value = str(current_status)

        status_options = [
            Option("Draft", value="draft", selected=(current_status_value == "draft")),
            Option("Scheduled", value="scheduled", selected=(current_status_value == "scheduled")),
            Option(
                "In Progress", value="in_progress", selected=(current_status_value == "in_progress")
            ),
            Option("Completed", value="completed", selected=(current_status_value == "completed")),
            Option("Blocked", value="blocked", selected=(current_status_value == "blocked")),
            Option("Cancelled", value="cancelled", selected=(current_status_value == "cancelled")),
        ]

        # Priority options
        current_priority = getattr(task, "priority", Priority.MEDIUM)
        if hasattr(current_priority, "value"):
            current_priority_value = current_priority.value
        else:
            current_priority_value = str(current_priority)

        priority_options = [
            Option(
                "P1 - Critical", value="critical", selected=(current_priority_value == "critical")
            ),
            Option("P2 - High", value="high", selected=(current_priority_value == "high")),
            Option("P3 - Medium", value="medium", selected=(current_priority_value == "medium")),
            Option("P4 - Low", value="low", selected=(current_priority_value == "low")),
        ]

        # Tags as comma-separated string
        task_tags = getattr(task, "tags", None) or []
        tags_value = ", ".join(task_tags) if task_tags else ""

        # Format dates for input fields
        due_date = getattr(task, "due_date", None)
        due_date_value = due_date.isoformat() if due_date else ""

        scheduled_date = getattr(task, "scheduled_date", None)
        scheduled_date_value = scheduled_date.isoformat() if scheduled_date else ""

        # Duration
        duration = getattr(task, "duration_minutes", 30) or 30

        form_content = Form(
            # Title (required)
            Div(
                Label("Title", cls="label font-semibold"),
                Input(
                    type="text",
                    name="title",
                    value=task.title,
                    cls="input input-bordered w-full",
                    required=True,
                ),
                cls="mb-4",
            ),
            # Description
            Div(
                Label("Description", cls="label font-semibold"),
                Textarea(
                    getattr(task, "description", "") or "",
                    name="description",
                    placeholder="Add details...",
                    rows="3",
                    cls="textarea textarea-bordered w-full",
                ),
                cls="mb-4",
            ),
            # Two-column layout for dates
            Div(
                Div(
                    Label("Due Date", cls="label font-semibold"),
                    Input(
                        type="date",
                        name="due_date",
                        value=due_date_value,
                        cls="input input-bordered w-full",
                    ),
                    cls="flex-1",
                ),
                Div(
                    Label("Scheduled Date", cls="label font-semibold"),
                    Input(
                        type="date",
                        name="scheduled_date",
                        value=scheduled_date_value,
                        cls="input input-bordered w-full",
                    ),
                    cls="flex-1",
                ),
                cls="flex gap-4 mb-4",
            ),
            # Duration
            Div(
                Label("Duration (minutes)", cls="label font-semibold"),
                Input(
                    type="number",
                    name="duration_minutes",
                    value=str(duration),
                    min="5",
                    max="480",
                    cls="input input-bordered w-full",
                ),
                cls="mb-4",
            ),
            # Two-column layout for priority and status
            Div(
                Div(
                    Label("Priority", cls="label font-semibold"),
                    Select(*priority_options, name="priority", cls="select select-bordered w-full"),
                    cls="flex-1",
                ),
                Div(
                    Label("Status", cls="label font-semibold"),
                    Select(*status_options, name="status", cls="select select-bordered w-full"),
                    cls="flex-1",
                ),
                cls="flex gap-4 mb-4",
            ),
            # Project
            Div(
                Label("Project", cls="label font-semibold"),
                Input(
                    type="text",
                    name="project",
                    value=getattr(task, "project", "") or "",
                    placeholder="e.g., Work, Personal",
                    list="edit-project-suggestions",
                    cls="input input-bordered w-full",
                ),
                project_datalist,
                cls="mb-4",
            ),
            # Tags
            Div(
                Label("Tags (comma-separated)", cls="label font-semibold"),
                Input(
                    type="text",
                    name="tags",
                    value=tags_value,
                    placeholder="tag1, tag2, tag3",
                    cls="input input-bordered w-full",
                ),
                cls="mb-4",
            ),
            # Modal actions
            Div(
                Button(
                    "Cancel",
                    type="button",
                    cls="btn btn-ghost",
                    onclick="document.getElementById('task-edit-modal').close()",
                ),
                Button(
                    "Save Changes",
                    type="button",
                    id="task-save-btn",
                    cls="btn btn-primary",
                ),
                cls="modal-action",
            ),
            id="task-edit-form",
        )

        # Script to open dialog and handle save with fetch
        init_script = Script(f"""
            (function() {{
                var dialog = document.getElementById('task-edit-modal');
                var btn = document.getElementById('task-save-btn');
                var form = document.getElementById('task-edit-form');

                if (dialog) {{
                    dialog.showModal();
                }}

                if (btn && form) {{
                    btn.addEventListener('click', function() {{
                        var formData = new FormData(form);
                        fetch('/tasks/edit-save?uid={task.uid}', {{
                            method: 'POST',
                            body: formData
                        }})
                        .then(function(response) {{ return response.text(); }})
                        .then(function(html) {{
                            var taskEl = document.getElementById('task-{task.uid}');
                            if (taskEl) {{
                                taskEl.outerHTML = html;
                                // Re-process HTMX on the new element so click handlers work
                                var newTaskEl = document.getElementById('task-{task.uid}');
                                if (newTaskEl && window.htmx) {{
                                    window.htmx.process(newTaskEl);
                                }}
                            }}
                            dialog.close();
                        }})
                        .catch(function(err) {{
                            console.error('Save failed:', err);
                            alert('Failed to save task');
                        }});
                    }});
                }}
            }})();
        """)

        from fasthtml.common import Dialog

        return Dialog(
            Div(
                # Close button
                Button(
                    "✕",
                    cls="btn btn-sm btn-circle btn-ghost absolute right-2 top-2",
                    onclick="document.getElementById('task-edit-modal').close()",
                ),
                H3("Edit Task", cls="font-bold text-lg mb-4"),
                form_content,
                cls="modal-box w-11/12 max-w-2xl relative",
            ),
            init_script,
            id="task-edit-modal",
            cls="modal",
        )

    # ========================================================================
    # QUICK ADD FORM
    # ========================================================================

    @staticmethod
    def render_quick_add_form(
        projects: list[str] | None = None,
        user_uid: str | None = None,
        existing_tasks: list[Any] | None = None,
    ) -> Any:
        """
        Render inline quick-add form (always visible).

        Fields: title, project, priority, assignee, dates, description,
                parent_uid (subtask), recurrence_pattern, recurrence_end_date
        """
        projects = projects or []
        existing_tasks = existing_tasks or []

        # Title input (main focus)
        title_input = Input(
            type="text",
            name="title",
            placeholder="Add a task...",
            cls="input input-bordered input-sm flex-1",
            required=True,
        )

        # Project input with datalist for autocomplete (allows typing new projects)
        project_options = [Option(value=p) for p in projects]
        project_datalist = Datalist(*project_options, id="project-suggestions")

        project_input = Input(
            type="text",
            name="project",
            placeholder="Project",
            list="project-suggestions",
            cls="input input-bordered input-sm w-32",
        )

        # Priority dropdown (P1-P4)
        priority_select = Select(
            Option("P4", value="low"),
            Option("P3", value="medium", selected=True),
            Option("P2", value="high"),
            Option("P1", value="critical"),
            name="priority",
            cls="select select-bordered select-sm w-20",
        )

        # Assignee input
        assignee_input = Input(
            type="text",
            name="assignee",
            placeholder="Assignee",
            cls="input input-bordered input-sm w-28",
        )

        # Start date (scheduled_date)
        start_date_input = Input(
            type="date", name="scheduled_date", cls="input input-bordered input-sm w-36"
        )

        # Due date
        due_date_input = Input(
            type="date", name="due_date", cls="input input-bordered input-sm w-36"
        )

        # Description textarea (optional, collapsible)
        description_input = Textarea(
            name="description",
            placeholder="Add description (optional)...",
            rows="2",
            cls="textarea textarea-bordered textarea-sm w-full",
        )

        # Parent task input with datalist (for subtasks)
        parent_options = [
            Option(value=t.uid, label=f"{t.title[:40]}...")
            for t in existing_tasks
            if hasattr(t, "uid") and hasattr(t, "title")
        ]
        parent_datalist = Datalist(*parent_options, id="parent-task-suggestions")

        parent_input = Input(
            type="text",
            name="parent_uid",
            placeholder="Parent task (for subtasks)",
            list="parent-task-suggestions",
            cls="input input-bordered input-sm w-48",
        )

        # Recurrence pattern dropdown
        recurrence_select = Select(
            Option("No repeat", value=""),
            Option("Daily", value="daily"),
            Option("Weekdays", value="weekdays"),
            Option("Weekends", value="weekends"),
            Option("Weekly", value="weekly"),
            Option("Biweekly", value="biweekly"),
            Option("Monthly", value="monthly"),
            Option("Quarterly", value="quarterly"),
            Option("Yearly", value="yearly"),
            name="recurrence_pattern",
            cls="select select-bordered select-sm w-32",
        )

        # Recurrence end date
        recurrence_end_input = Input(
            type="date", name="recurrence_end_date", cls="input input-bordered input-sm w-36"
        )

        # Add button - make it clearly visible
        add_button = Button("Add Task", type="submit", cls="btn btn-primary btn-sm px-4")

        # First row: Title + Project + Priority + Add
        row1 = Div(
            title_input,
            project_input,
            project_datalist,  # Hidden datalist for autocomplete
            priority_select,
            add_button,
            cls="flex items-center gap-2",
        )

        # Second row: Assignee + Start + Due (more visible labels)
        row2 = Div(
            Label("Assignee:", cls="text-sm text-gray-600 font-medium"),
            assignee_input,
            Label("Start:", cls="text-sm text-gray-600 font-medium ml-3"),
            start_date_input,
            Label("Due:", cls="text-sm text-gray-600 font-medium ml-3"),
            due_date_input,
            cls="flex items-center gap-3 mt-4 pt-4 border-t border-base-200",
        )

        # Third row: Description
        row3 = Div(
            Label("Description:", cls="text-sm text-gray-600 font-medium"),
            description_input,
            cls="mt-3",
        )

        # Fourth row: Parent task (subtasks) + Recurrence
        row4 = Div(
            Label("Subtask of:", cls="text-sm text-gray-600 font-medium"),
            parent_input,
            parent_datalist,  # Hidden datalist for autocomplete
            Label("Repeat:", cls="text-sm text-gray-600 font-medium ml-3"),
            recurrence_select,
            Label("Until:", cls="text-sm text-gray-600 font-medium ml-3"),
            recurrence_end_input,
            cls="flex items-center gap-3 mt-4 pt-4 border-t border-base-200",
        )

        return Form(
            row1,
            row2,
            row3,
            row4,
            hx_post="/tasks/quick-add",
            hx_target="#task-list",
            hx_swap="outerHTML",
            hx_on__after_request="this.reset()",
            cls="card bg-base-100 shadow-md border border-base-200 p-6 mb-6 rounded-xl",
        )

    # ========================================================================
    # FILTER BAR
    # ========================================================================

    @staticmethod
    def render_filter_bar(
        projects: list[str] | None = None,
        assignees: list[str] | None = None,
        current_filters: dict[str, Any] | None = None,
    ) -> Any:
        """
        Render filter/sort controls.

        Filters: Project, Assignee, Due (Today/Week/Overdue/All), Status
        Sort: Due Date, Priority, Recently Added
        """
        projects = projects or []
        assignees = assignees or []
        current_filters = current_filters or {}

        # Project filter
        project_options = [Option("All Projects", value="")]
        project_options.extend(Option(p, value=p) for p in projects)

        project_filter = Select(
            *project_options,
            name="filter_project",
            cls="select select-bordered select-sm",
            hx_get="/tasks/list-fragment",
            hx_target="#task-list",
            hx_include="[name^='filter_'],[name='sort_by']",
        )

        # Assignee filter
        assignee_options = [Option("All Assignees", value="")]
        assignee_options.extend(Option(a, value=a) for a in assignees)

        assignee_filter = Select(
            *assignee_options,
            name="filter_assignee",
            cls="select select-bordered select-sm",
            hx_get="/tasks/list-fragment",
            hx_target="#task-list",
            hx_include="[name^='filter_'],[name='sort_by']",
        )

        # Due date filter
        due_filter = Select(
            Option("All Dates", value=""),
            Option("Today", value="today"),
            Option("Tomorrow", value="tomorrow"),
            Option("This Week", value="week"),
            Option("Overdue", value="overdue"),
            name="filter_due",
            cls="select select-bordered select-sm",
            hx_get="/tasks/list-fragment",
            hx_target="#task-list",
            hx_include="[name^='filter_'],[name='sort_by']",
        )

        # Status filter
        status_filter = Select(
            Option("Active", value="active", selected=True),
            Option("Completed", value="completed"),
            Option("All", value="all"),
            name="filter_status",
            cls="select select-bordered select-sm",
            hx_get="/tasks/list-fragment",
            hx_target="#task-list",
            hx_include="[name^='filter_'],[name='sort_by']",
        )

        # Sort dropdown
        sort_select = Select(
            Option("Due Date", value="due_date"),
            Option("Priority", value="priority"),
            Option("Recently Added", value="created_at"),
            Option("Project", value="project"),
            name="sort_by",
            cls="select select-bordered select-sm",
            hx_get="/tasks/list-fragment",
            hx_target="#task-list",
            hx_include="[name^='filter_'],[name='sort_by']",
        )

        return Div(
            Div(
                Label("Project:", cls="text-xs text-gray-500"),
                project_filter,
                cls="flex items-center gap-1",
            ),
            Div(
                Label("Assignee:", cls="text-xs text-gray-500"),
                assignee_filter,
                cls="flex items-center gap-1",
            ),
            Div(
                Label("Due:", cls="text-xs text-gray-500"),
                due_filter,
                cls="flex items-center gap-1",
            ),
            Div(
                Label("Status:", cls="text-xs text-gray-500"),
                status_filter,
                cls="flex items-center gap-1",
            ),
            Div(
                Label("Sort:", cls="text-xs text-gray-500"),
                sort_select,
                cls="flex items-center gap-1",
            ),
            cls="flex flex-wrap items-center gap-4 p-4 bg-base-200/50 rounded-lg mb-6",
        )

    # ========================================================================
    # TASK LIST
    # ========================================================================

    @staticmethod
    def render_task_list(tasks: list[Any], user_uid: str | None = None) -> Any:
        """Render the task list container."""
        if not tasks:
            return Ul(
                Li(
                    Div(
                        P("No tasks yet", cls="text-gray-500 font-medium"),
                        P("Add a task above to get started", cls="text-gray-400 text-sm"),
                        cls="text-center py-8",
                    ),
                    cls="list-none",
                ),
                id="task-list",
                cls="list-none divide-y divide-gray-100",
            )

        task_items = [TodoistTaskComponents.render_task_item(task, user_uid) for task in tasks]

        return Ul(*task_items, id="task-list", cls="list-none")

    # ========================================================================
    # STATS BAR
    # ========================================================================

    @staticmethod
    def render_stats_bar(stats: dict[str, int]) -> Any:
        """Render simple stats: Total | Completed | Overdue."""
        total = stats.get("total", 0)
        completed = stats.get("completed", 0)
        overdue = stats.get("overdue", 0)

        return Div(
            Span(f"{total} tasks", cls="text-sm text-gray-600"),
            Span("|", cls="text-gray-300 mx-2"),
            Span(f"{completed} completed", cls="text-sm text-green-600"),
            Span("|", cls="text-gray-300 mx-2"),
            Span(
                f"{overdue} overdue",
                cls=f"text-sm {'text-red-500 font-medium' if overdue > 0 else 'text-gray-500'}",
            ),
            cls="flex items-center mb-4",
        )

    # ========================================================================
    # MAIN DASHBOARD CONTENT
    # ========================================================================

    @staticmethod
    def render_content(
        tasks: list[Any],
        projects: list[str] | None = None,
        assignees: list[str] | None = None,
        stats: dict[str, int] | None = None,
        filters: dict[str, Any] | None = None,
        user_uid: str | None = None,
    ) -> Any:
        """
        Render task dashboard content (without page wrapper).

        Used by create_profile_page() for ProfileLayout integration.

        Args:
            tasks: List of task entities
            projects: List of project names for dropdowns
            assignees: List of assignee names for dropdowns
            stats: Stats dict with total, completed, overdue counts
            filters: Current filter values
            user_uid: Current user UID
        """
        return Div(
            # Title
            H1("Task Manager", cls="text-3xl font-bold mb-8"),
            # Quick Add Form (Todoist-specific feature) - front and center
            TodoistTaskComponents.render_quick_add_form(projects, user_uid, tasks),
            # Filter Bar (Todoist-specific feature)
            TodoistTaskComponents.render_filter_bar(projects, assignees, filters),
            # Task List
            Div(
                TodoistTaskComponents.render_task_list(tasks, user_uid),
                cls="card bg-base-100 shadow-md border border-base-200 rounded-xl overflow-hidden",
            ),
        )
