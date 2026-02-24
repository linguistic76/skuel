"""
Tasks Three-View Components
===========================

Three-view task management interface with Create, List, and Calendar views.

Usage:
    from ui.tasks.views import TasksViewComponents

    # Main tabs
    tabs = TasksViewComponents.render_view_tabs("list")

    # Individual views
    create_view = TasksViewComponents.render_create_view(projects, tasks, user_uid)
    list_view = TasksViewComponents.render_list_view(tasks, filters, stats, projects, assignees)
    calendar_view = TasksViewComponents.render_calendar_view(tasks, today, "month")
"""

from datetime import date, timedelta
from typing import Any

from fasthtml.common import (
    H2,
    A,
    Datalist,
    Div,
    Form,
    Label,
    Option,
    P,
)

from core.models.event.calendar_models import (
    CalendarData,
    CalendarView,
)
from core.utils.logging import get_logger
from ui.calendar.components import (
    create_day_timeline,
    create_month_grid,
    create_reschedule_form,
    create_week_grid,
)
from ui.calendar.converters import task_to_calendar_item
from ui.daisy_components import Button, ButtonT, Input, Select, Size, Textarea
from ui.patterns.activity_views_base import (
    ActivityCalendarNav,
    ActivityViewSwitcher,
    ActivityViewTabs,
)
from ui.tasks.todoist_components import TodoistTaskComponents

logger = get_logger("skuel.components.tasks_views")


class TasksViewComponents:
    """
    Three-view task management interface.

    Views:
    - Create: Full task creation form
    - List: Sortable, filterable task list
    - Calendar: Month/Week/Day views of tasks
    """

    # ========================================================================
    # MAIN TAB NAVIGATION
    # ========================================================================

    @staticmethod
    def render_view_tabs(active_view: str = "list") -> Div:
        """
        Render the main view tabs (List, Create, Calendar).

        Uses ActivityViewTabs for consistent styling across Activity domains.

        Args:
            active_view: Currently active view ("list", "create", "calendar")

        Returns:
            Div containing the tab navigation
        """
        return ActivityViewTabs.list_create_calendar("tasks", active_view)

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        projects: list[str] | None = None,
        existing_tasks: list[Any] | None = None,
    ) -> Div:
        """
        Render the full task creation form.

        Two-column layout on desktop, stacked on mobile.

        Args:
            projects: List of existing project names for autocomplete
            existing_tasks: List of existing tasks for parent selection

        Returns:
            Div containing the creation form
        """
        projects = projects or []
        existing_tasks = existing_tasks or []

        # Project datalist
        project_options = [Option(value=p) for p in projects]
        project_datalist = Datalist(*project_options, id="create-project-suggestions")

        # Left column: Core fields
        left_column = Div(
            # Title (required)
            Div(
                Label("Title", cls="label font-semibold"),
                Input(
                    type="text",
                    name="title",
                    placeholder="What needs to be done?",
                    cls="input input-bordered w-full",
                    required=True,
                    autofocus=True,
                ),
                cls="mb-4",
            ),
            # Description
            Div(
                Label("Description", cls="label font-semibold"),
                Textarea(
                    name="description",
                    placeholder="Add details, notes, or context...",
                    rows="4",
                    cls="textarea textarea-bordered w-full",
                ),
                cls="mb-4",
            ),
            # Project
            Div(
                Label("Project", cls="label font-semibold"),
                Input(
                    type="text",
                    name="project",
                    placeholder="e.g., Work, Personal, Home",
                    list="create-project-suggestions",
                    cls="input input-bordered w-full",
                ),
                project_datalist,
                cls="mb-4",
            ),
            # Priority
            Div(
                Label("Priority", cls="label font-semibold"),
                Select(
                    Option("P1 - Critical", value="critical"),
                    Option("P2 - High", value="high"),
                    Option("P3 - Medium", value="medium", selected=True),
                    Option("P4 - Low", value="low"),
                    name="priority",
                    cls="select select-bordered w-full",
                ),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Right column: Scheduling and advanced
        right_column = Div(
            # Scheduled date
            Div(
                Label("Start Date", cls="label font-semibold"),
                Input(
                    type="date",
                    name="scheduled_date",
                    cls="input input-bordered w-full",
                ),
                P("When to start working on this task", cls="text-xs text-gray-500 mt-1"),
                cls="mb-4",
            ),
            # Due date
            Div(
                Label("Due Date", cls="label font-semibold"),
                Input(
                    type="date",
                    name="due_date",
                    cls="input input-bordered w-full",
                ),
                P("Deadline for completion", cls="text-xs text-gray-500 mt-1"),
                cls="mb-4",
            ),
            # Duration
            Div(
                Label("Estimated Duration (minutes)", cls="label font-semibold"),
                Input(
                    type="number",
                    name="duration_minutes",
                    placeholder="60",
                    min="5",
                    step="5",
                    cls="input input-bordered w-full",
                ),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Submit buttons
        submit_section = Div(
            A(
                "Cancel",
                href="/tasks",
                cls="btn btn-ghost btn-lg",
            ),
            Button(
                "Create Task",
                type="submit",
                variant=ButtonT.primary,
                size=Size.lg,
            ),
            Button(
                "Create & Add Another",
                type="submit",
                name="add_another",
                value="true",
                variant=ButtonT.outline,
                size=Size.lg,
            ),
            cls="flex justify-end gap-2 pt-6 border-t border-base-200",
        )

        return Div(
            H2("Create New Task", cls="text-2xl font-bold mb-6"),
            Form(
                Div(
                    left_column,
                    right_column,
                    cls="flex flex-col lg:flex-row gap-8",
                ),
                submit_section,
                **{
                    "hx-post": "/tasks/quick-add",
                    "hx-target": "#view-content",
                    "hx-swap": "innerHTML",
                },
                cls="card bg-base-100 shadow-lg p-6",
            ),
            id="create-view",
        )

    # ========================================================================
    # LIST VIEW
    # ========================================================================

    @staticmethod
    def render_list_view(
        tasks: list[Any],
        filters: dict[str, Any] | None = None,
        projects: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> Div:
        """
        Render the sortable, filterable task list.

        Args:
            tasks: List of tasks to display
            filters: Current filter values
            projects: List of project names for filter dropdown
            assignees: List of assignee names for filter dropdown

        Returns:
            Div containing the list view
        """
        filters = filters or {}
        projects = projects or []
        assignees = assignees or []

        # Filter bar (reuse existing component)
        filter_bar = TodoistTaskComponents.render_filter_bar(
            projects=projects,
            assignees=assignees,
            current_filters=filters,
        )

        # Task list (reuse existing component)
        task_list = TodoistTaskComponents.render_task_list(tasks)

        return Div(
            filter_bar,
            Div(
                task_list,
                id="task-list",
            ),
            id="list-view",
        )

    # ========================================================================
    # CALENDAR VIEW
    # ========================================================================

    @staticmethod
    def render_calendar_view(
        tasks: list[Any],
        current_date: date | None = None,
        calendar_view: str = "month",
    ) -> Div:
        """
        Render the calendar view with Month/Week/Day sub-views.

        Args:
            tasks: List of tasks to display
            current_date: Current date for calendar (defaults to today)
            calendar_view: Which view to show ("month", "week", "day")

        Returns:
            Div containing the calendar view
        """
        current_date = current_date or date.today()

        # Convert tasks to CalendarItems
        calendar_items = []
        for task in tasks:
            try:
                # Only include tasks with dates
                if getattr(task, "due_date", None) or getattr(task, "scheduled_date", None):
                    calendar_items.append(task_to_calendar_item(task))
            except Exception as e:
                logger.warning(f"Failed to convert task to calendar item: {e}")
                continue

        # Calculate date range based on view
        if calendar_view == "day":
            start_date = current_date
            end_date = current_date
            view_type = CalendarView.DAY
        elif calendar_view == "week":
            # Start from Monday of current week
            days_since_monday = current_date.weekday()
            start_date = current_date - timedelta(days=days_since_monday)
            end_date = start_date + timedelta(days=6)
            view_type = CalendarView.WEEK
        else:  # month
            start_date = current_date.replace(day=1)
            # Last day of month
            if current_date.month == 12:
                end_date = current_date.replace(
                    year=current_date.year + 1, month=1, day=1
                ) - timedelta(days=1)
            else:
                end_date = current_date.replace(month=current_date.month + 1, day=1) - timedelta(
                    days=1
                )
            view_type = CalendarView.MONTH

        # Filter items to date range
        filtered_items = [
            item for item in calendar_items if start_date <= item.start_time.date() <= end_date
        ]

        # Create CalendarData
        calendar_data = CalendarData(
            items=filtered_items,
            occurrences={},  # No habit occurrences for tasks
            view=view_type,
            start_date=start_date,
            end_date=end_date,
            metadata={},
        )

        # Navigation header with date and prev/next (using shared component)
        nav_header = ActivityCalendarNav.render("tasks", current_date, calendar_view)

        # View switcher for Month/Week/Day (using shared component)
        view_switcher = ActivityViewSwitcher.render("tasks", current_date, calendar_view)

        # Render the appropriate calendar grid
        if calendar_view == "day":
            grid = create_day_timeline(calendar_data)
        elif calendar_view == "week":
            grid = create_week_grid(calendar_data)
        else:
            grid = create_month_grid(calendar_data)

        return Div(
            Div(
                nav_header,
                view_switcher,
                cls="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-4",
            ),
            Div(
                grid,
                id="calendar-grid",
            ),
            # Hidden reschedule form for drag-drop
            create_reschedule_form(),
            id="calendar-view",
            # Alpine.js for drag-drop interactions (no modal)
            **{"x-data": "calendarDrag()"},
        )


__all__ = ["TasksViewComponents", "task_to_calendar_item"]
