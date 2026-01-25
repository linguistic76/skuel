"""
Goals Three-View Components
===========================

Three-view goal management interface with List, Create, and Calendar views.

Usage:
    from components.goals_views import GoalsViewComponents

    # Main tabs
    tabs = GoalsViewComponents.render_view_tabs("list")

    # Individual views
    list_view = GoalsViewComponents.render_list_view(goals, filters, stats)
    create_view = GoalsViewComponents.render_create_view(categories)
    calendar_view = GoalsViewComponents.render_calendar_view(goals, today, "month")
"""

from datetime import date, timedelta
from typing import Any

from fasthtml.common import (
    H2,
    H3,
    Button,
    Div,
    Form,
    Input,
    Label,
    Option,
    P,
    Progress,
    Select,
    Span,
    Textarea,
)

from components.activity_views_base import (
    ActivityCalendarNav,
    ActivityViewSwitcher,
    ActivityViewTabs,
)
from components.calendar_components import (
    create_day_timeline,
    create_month_grid,
    create_reschedule_form,
    create_week_grid,
)
from components.calendar_converters import goal_to_calendar_item
from core.models.event.calendar_models import (
    CalendarData,
    CalendarView,
)
from core.models.goal.goal import Goal
from core.utils.logging import get_logger

logger = get_logger("skuel.components.goals_views")


class GoalsViewComponents:
    """
    Three-view goal management interface.

    Views:
    - List: Sortable, filterable goal list with progress
    - Create: Full goal creation form
    - Calendar: Month/Week/Day views showing goal timelines
    """

    # ========================================================================
    # MAIN TAB NAVIGATION
    # ========================================================================

    @staticmethod
    def render_view_tabs(active_view: str = "list") -> Div:
        """
        Render the main view tabs (List, Create, Calendar).

        Args:
            active_view: Currently active view ("list", "create", "calendar")

        Returns:
            Div containing the tab navigation
        """
        return ActivityViewTabs.list_create_calendar("goals", active_view)

    # ========================================================================
    # LIST VIEW
    # ========================================================================

    @staticmethod
    def render_list_view(
        goals: list[Any],
        filters: dict[str, Any] | None = None,
        stats: dict[str, int] | None = None,
        categories: list[str] | None = None,
        user_uid: str | None = None,
    ) -> Div:
        """
        Render the sortable, filterable goal list.

        Args:
            goals: List of goals to display
            filters: Current filter values
            stats: Goal statistics
            categories: List of category names for filter
            user_uid: Current user UID

        Returns:
            Div containing the list view
        """
        filters = filters or {}
        stats = stats or {}
        categories = categories or []

        # Stats bar
        stats_bar = Div(
            Div(
                Span("Total: ", cls="text-base-content/60"),
                Span(str(stats.get("total", 0)), cls="font-bold"),
                cls="mr-4",
            ),
            Div(
                Span("Active: ", cls="text-base-content/60"),
                Span(str(stats.get("active", 0)), cls="font-bold text-success"),
                cls="mr-4",
            ),
            Div(
                Span("Completed: ", cls="text-base-content/60"),
                Span(str(stats.get("completed", 0)), cls="font-bold text-info"),
            ),
            cls="flex items-center mb-4 text-sm",
        )

        # Filter bar
        filter_bar = Div(
            # Status filter
            Div(
                Label("Status:", cls="mr-2 text-sm"),
                Select(
                    Option("All", value="all", selected=filters.get("status") == "all"),
                    Option(
                        "Active",
                        value="active",
                        selected=filters.get("status", "active") == "active",
                    ),
                    Option(
                        "Completed",
                        value="completed",
                        selected=filters.get("status") == "completed",
                    ),
                    Option("Paused", value="paused", selected=filters.get("status") == "paused"),
                    name="filter_status",
                    cls="select select-bordered select-sm",
                    **{
                        "hx-get": "/goals/list-fragment",
                        "hx-target": "#goal-list",
                        "hx-include": "[name^='filter_'], [name='sort_by']",
                    },
                ),
                cls="mr-4",
            ),
            # Sort
            Div(
                Label("Sort:", cls="mr-2 text-sm"),
                Select(
                    Option(
                        "Target Date",
                        value="target_date",
                        selected=filters.get("sort_by", "target_date") == "target_date",
                    ),
                    Option(
                        "Priority", value="priority", selected=filters.get("sort_by") == "priority"
                    ),
                    Option(
                        "Progress", value="progress", selected=filters.get("sort_by") == "progress"
                    ),
                    Option(
                        "Created",
                        value="created_at",
                        selected=filters.get("sort_by") == "created_at",
                    ),
                    name="sort_by",
                    cls="select select-bordered select-sm",
                    **{
                        "hx-get": "/goals/list-fragment",
                        "hx-target": "#goal-list",
                        "hx-include": "[name^='filter_']",
                    },
                ),
            ),
            cls="flex items-center mb-4",
        )

        # Goal list
        goal_items = [GoalsViewComponents._render_goal_item(goal, user_uid) for goal in goals]

        goal_list = Div(
            *goal_items
            if goal_items
            else [
                P(
                    "No goals found. Create one to get started!",
                    cls="text-base-content/60 text-center py-8",
                )
            ],
            id="goal-list",
            cls="space-y-3",
        )

        return Div(
            stats_bar,
            filter_bar,
            goal_list,
            id="list-view",
        )

    @staticmethod
    def _render_goal_item(goal: Goal, user_uid: str | None = None) -> Div:
        """Render a single goal item for the list."""
        uid = goal.uid
        title = goal.title
        description = goal.description or ""
        status = goal.status or "active"
        priority = goal.priority or "medium"
        progress = goal.current_value or 0
        target_date = goal.target_date

        # Status color
        status_str = str(status).lower().replace("goalstatus.", "")
        status_colors = {
            "active": "badge-success",
            "completed": "badge-info",
            "paused": "badge-warning",
            "cancelled": "badge-error",
        }
        status_badge = status_colors.get(status_str, "badge-ghost")

        # Priority color
        priority_str = str(priority).lower()
        priority_colors = {
            "critical": "text-error",
            "high": "text-warning",
            "medium": "text-info",
            "low": "text-base-content/70",
        }
        priority_color = priority_colors.get(priority_str, "text-base-content/70")

        return Div(
            Div(
                # Header row
                Div(
                    H3(title, cls="text-lg font-semibold"),
                    Span(status_str.title(), cls=f"badge {status_badge} badge-sm ml-2"),
                    cls="flex items-center",
                ),
                # Description
                P(
                    description[:100] + "..."
                    if description and len(description) > 100
                    else description,
                    cls="text-base-content/70 text-sm mt-1",
                )
                if description
                else "",
                # Progress bar
                Div(
                    Div(
                        Span(f"Progress: {int(progress)}%", cls="text-xs text-base-content/60"),
                        Progress(
                            value=int(progress),
                            max=100,
                            cls="progress progress-primary w-full h-2 mt-1",
                        ),
                    ),
                    cls="mt-2",
                )
                if progress > 0
                else "",
                # Meta row
                Div(
                    Span(f"Priority: {priority_str.title()}", cls=f"text-xs {priority_color} mr-4"),
                    Span(f"Due: {target_date}", cls="text-xs text-base-content/60")
                    if target_date
                    else "",
                    cls="flex items-center mt-2",
                ),
                # Actions
                Div(
                    Button(
                        "View",
                        cls="btn btn-xs btn-outline",
                        **{"hx-get": f"/goals/{uid}", "hx-target": "body"},
                    ),
                    Button(
                        "Edit",
                        cls="btn btn-xs btn-ghost",
                        **{"hx-get": f"/goals/{uid}/edit", "hx-target": "#modal"},
                    ),
                    cls="flex gap-2 mt-3",
                ),
                cls="p-4",
            ),
            id=f"goal-{uid}",
            cls="card bg-base-100 shadow-sm border border-base-200 hover:shadow-md transition-shadow",
        )

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        categories: list[str] | None = None,
        timeframes: list[tuple[str, str]] | None = None,
        user_uid: str | None = None,
    ) -> Div:
        """
        Render the goal creation form.

        Two-column layout on desktop, stacked on mobile.

        Args:
            categories: List of category names for dropdown
            timeframes: List of (value, label) tuples for timeframe
            user_uid: Current user UID

        Returns:
            Div containing the creation form
        """
        # Valid Domain enum values for goal categorization
        categories = categories or [
            "business",
            "health",
            "education",
            "personal",
            "tech",
            "creative",
            "social",
            "research",
        ]
        timeframes = timeframes or [
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("yearly", "Yearly"),
            ("multi_year", "Multi-Year"),
        ]

        # Left column: Core fields
        left_column = Div(
            # Title (required)
            Div(
                Label("Goal Title", cls="label font-semibold"),
                Input(
                    type="text",
                    name="title",
                    placeholder="What do you want to achieve?",
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
                    placeholder="Describe your goal in detail...",
                    rows="4",
                    cls="textarea textarea-bordered w-full",
                ),
                cls="mb-4",
            ),
            # Why Important
            Div(
                Label("Why is this important?", cls="label font-semibold"),
                Textarea(
                    name="why_important",
                    placeholder="What motivates you to achieve this goal?",
                    rows="3",
                    cls="textarea textarea-bordered w-full",
                ),
                cls="mb-4",
            ),
            # Domain/Category
            Div(
                Label("Category", cls="label font-semibold"),
                Select(
                    *[Option(cat.title(), value=cat) for cat in categories],
                    name="domain",
                    cls="select select-bordered w-full",
                ),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Right column: Scheduling and classification
        right_column = Div(
            # Timeframe
            Div(
                Label("Timeframe", cls="label font-semibold"),
                Select(
                    *[
                        Option(label, value=value, selected=(value == "quarterly"))
                        for value, label in timeframes
                    ],
                    name="timeframe",
                    cls="select select-bordered w-full",
                ),
                P(
                    "How long do you have to achieve this goal?",
                    cls="text-xs text-base-content/60 mt-1",
                ),
                cls="mb-4",
            ),
            # Target Date
            Div(
                Label("Target Date", cls="label font-semibold"),
                Input(
                    type="date",
                    name="target_date",
                    cls="input input-bordered w-full",
                ),
                P(
                    "When do you want to complete this goal?",
                    cls="text-xs text-base-content/60 mt-1",
                ),
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
            # Target Value (optional)
            Div(
                Label("Target Value (optional)", cls="label font-semibold"),
                Input(
                    type="number",
                    name="target_value",
                    placeholder="e.g., 100",
                    min="0",
                    cls="input input-bordered w-full",
                ),
                P("Numeric target for measurable goals", cls="text-xs text-base-content/60 mt-1"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Submit buttons
        submit_section = Div(
            Button(
                "Create Goal",
                type="submit",
                cls="btn btn-primary btn-lg",
            ),
            Button(
                "Create & Add Another",
                type="submit",
                name="add_another",
                value="true",
                cls="btn btn-outline btn-lg ml-2",
            ),
            cls="flex justify-end pt-6 border-t border-base-200",
        )

        return Div(
            H2("Create New Goal", cls="text-2xl font-bold mb-6"),
            Form(
                Div(
                    left_column,
                    right_column,
                    cls="flex flex-col lg:flex-row gap-8",
                ),
                submit_section,
                **{
                    "hx-post": "/goals/quick-add",
                    "hx-target": "#view-content",
                    "hx-swap": "innerHTML",
                },
                cls="card bg-base-100 shadow-lg p-6",
            ),
            id="create-view",
        )

    # ========================================================================
    # CALENDAR VIEW
    # ========================================================================

    @staticmethod
    def render_calendar_view(
        goals: list[Any],
        current_date: date | None = None,
        calendar_view: str = "month",
    ) -> Div:
        """
        Render the calendar view with Month/Week/Day sub-views.

        Args:
            goals: List of goals to display
            current_date: Current date for calendar (defaults to today)
            calendar_view: Which view to show ("month", "week", "day")

        Returns:
            Div containing the calendar view
        """
        current_date = current_date or date.today()

        # Convert goals to CalendarItems
        calendar_items = []
        for goal in goals:
            try:
                item = goal_to_calendar_item(goal)
                if item:
                    calendar_items.append(item)
            except Exception as e:
                logger.warning(f"Failed to convert goal to calendar item: {e}")
                continue

        # Calculate date range based on view
        if calendar_view == "day":
            start_date = current_date
            end_date = current_date
            view_type = CalendarView.DAY
        elif calendar_view == "week":
            days_since_monday = current_date.weekday()
            start_date = current_date - timedelta(days=days_since_monday)
            end_date = start_date + timedelta(days=6)
            view_type = CalendarView.WEEK
        else:  # month
            start_date = current_date.replace(day=1)
            if current_date.month == 12:
                end_date = current_date.replace(
                    year=current_date.year + 1, month=1, day=1
                ) - timedelta(days=1)
            else:
                end_date = current_date.replace(month=current_date.month + 1, day=1) - timedelta(
                    days=1
                )
            view_type = CalendarView.MONTH

        # Filter items to date range (check if target date falls in range)
        filtered_items = [
            item
            for item in calendar_items
            if start_date <= item.end_time.date() <= end_date
            or start_date <= item.start_time.date() <= end_date
        ]

        # Create CalendarData
        calendar_data = CalendarData(
            items=filtered_items,
            occurrences={},
            view=view_type,
            start_date=start_date,
            end_date=end_date,
            metadata={},
        )

        # Navigation header
        nav_header = ActivityCalendarNav.render("goals", current_date, calendar_view)

        # View switcher
        view_switcher = ActivityViewSwitcher.render("goals", current_date, calendar_view)

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
            create_reschedule_form(),
            id="calendar-view",
            **{"x-data": "calendarDrag()"},
        )


__all__ = ["GoalsViewComponents", "goal_to_calendar_item"]
