"""
Habits Three-View Components
============================

Three-view habit management interface with List, Create, and Calendar views.

Usage:
    from ui.habits.views import HabitsViewComponents

    # Main tabs
    tabs = HabitsViewComponents.render_view_tabs("list")

    # Individual views
    list_view = HabitsViewComponents.render_list_view(habits, filters, stats)
    create_view = HabitsViewComponents.render_create_view(categories)
    calendar_view = HabitsViewComponents.render_calendar_view(habits, today, "month")
"""

from datetime import date, timedelta
from typing import Any

from fasthtml.common import H2, H3, Div, Form, Option, P, Span

from core.models.event.calendar_models import (
    CalendarData,
    CalendarView,
)
from core.models.habit.habit import Habit as Habit
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonLink, ButtonT
from ui.calendar.components import (
    create_day_timeline,
    create_month_grid,
    create_reschedule_form,
    create_week_grid,
)
from ui.calendar.converters import habit_to_calendar_items
from ui.cards import Card
from ui.feedback import Badge, Progress
from ui.forms import Input, Label, Select, Textarea
from ui.layout import Size
from ui.patterns.activity_views_base import (
    ActivityCalendarNav,
    ActivityViewSwitcher,
    ActivityViewTabs,
)

logger = get_logger("skuel.components.habits_views")


class HabitsViewComponents:
    """
    Three-view habit management interface.

    Views:
    - List: Habit list with streak indicators
    - Create: Full habit creation form
    - Calendar: Month/Week/Day views showing habit schedule
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
        return ActivityViewTabs.list_create_calendar("habits", active_view)

    # ========================================================================
    # LIST VIEW
    # ========================================================================

    @staticmethod
    def render_list_view(
        habits: list[Any],
        filters: dict[str, Any] | None = None,
        stats: dict[str, int] | None = None,
        categories: list[str] | None = None,
    ) -> Div:
        """
        Render the habit list with streak indicators.

        Args:
            habits: List of habits to display
            filters: Current filter values
            stats: Habit statistics
            categories: List of category names for filter

        Returns:
            Div containing the list view
        """
        filters = filters or {}
        stats = stats or {}
        categories = categories or []

        # Stats bar
        stats_bar = Div(
            Div(
                Span("Total: ", cls="text-muted-foreground"),
                Span(str(stats.get("total", 0)), cls="font-bold"),
                cls="mr-4",
            ),
            Div(
                Span("Active Streaks: ", cls="text-muted-foreground"),
                Span(str(stats.get("active_streaks", 0)), cls="font-bold text-success"),
                cls="mr-4",
            ),
            Div(
                Span("Completed Today: ", cls="text-muted-foreground"),
                Span(str(stats.get("completed_today", 0)), cls="font-bold text-info"),
            ),
            cls="flex items-center mb-4 text-sm",
        )

        # Filter bar
        filter_bar = Div(
            Div(
                Label("Status:", cls="mr-2 text-sm"),
                Select(
                    Option("All", value="all", selected=filters.get("status") == "all"),
                    Option(
                        "Active",
                        value="active",
                        selected=filters.get("status", "active") == "active",
                    ),
                    Option("Paused", value="paused", selected=filters.get("status") == "paused"),
                    name="filter_status",
                    size=Size.sm,
                    full_width=False,
                    **{
                        "hx-get": "/habits/list-fragment",
                        "hx-target": "#habit-list",
                        "hx-include": "[name^='filter_'], [name='sort_by']",
                    },
                ),
                cls="mr-4",
            ),
            Div(
                Label("Sort:", cls="mr-2 text-sm"),
                Select(
                    Option(
                        "Streak",
                        value="streak",
                        selected=filters.get("sort_by", "streak") == "streak",
                    ),
                    Option("Name", value="name", selected=filters.get("sort_by") == "name"),
                    Option(
                        "Created",
                        value="created_at",
                        selected=filters.get("sort_by") == "created_at",
                    ),
                    name="sort_by",
                    size=Size.sm,
                    full_width=False,
                    **{
                        "hx-get": "/habits/list-fragment",
                        "hx-target": "#habit-list",
                        "hx-include": "[name^='filter_']",
                    },
                ),
            ),
            cls="flex items-center mb-4",
        )

        # Habit list
        habit_items = [HabitsViewComponents._render_habit_item(habit) for habit in habits]

        habit_list = Div(
            *habit_items
            if habit_items
            else [
                P(
                    "No habits found. Create one to get started!",
                    cls="text-muted-foreground text-center py-8",
                )
            ],
            id="habit-list",
            cls="space-y-3",
        )

        return Div(
            stats_bar,
            filter_bar,
            habit_list,
            id="list-view",
        )

    @staticmethod
    def _render_habit_item(habit: Habit) -> Div:
        """Render a single habit item for the list."""
        uid = habit.uid
        name = habit.title
        description = habit.description or ""
        status = habit.status or "active"
        current_streak = habit.current_streak or 0
        best_streak = habit.best_streak or 0
        frequency = habit.recurrence_pattern or "daily"

        # Status color
        from core.utils.type_converters import normalize_enum_str
        from ui.enum_helpers import get_status_badge_class

        status_str = normalize_enum_str(status, "active")
        status_badge = get_status_badge_class(status_str)

        # Streak indicator
        streak_color = "text-success" if current_streak > 0 else "text-muted-foreground"

        return Card(
            Div(
                # Header row
                Div(
                    H3(name, cls="text-lg font-semibold"),
                    Badge(status_str.title(), variant=None, cls=f"{status_badge} ml-2"),
                    cls="flex items-center",
                ),
                # Description
                P(
                    description[:100] + "..."
                    if description and len(description) > 100
                    else description,
                    cls="text-muted-foreground text-sm mt-1",
                )
                if description
                else "",
                # Streak display with progress bar
                Div(
                    Div(
                        Span("🔥", cls="text-lg mr-1"),
                        Span(f"{current_streak}", cls=f"font-bold {streak_color}"),
                        Span(" day streak", cls="text-muted-foreground text-sm ml-1"),
                        cls="flex items-center",
                    ),
                    # Progress bar showing streak vs best
                    Div(
                        Progress(
                            value=min(current_streak, best_streak)
                            if best_streak > 0
                            else current_streak,
                            max=max(best_streak, current_streak, 1),
                            cls="w-24 h-2",
                        ),
                        Span(f"Best: {best_streak}", cls="text-xs text-muted-foreground ml-2"),
                        cls="flex items-center mt-1",
                    )
                    if best_streak > 0
                    else Div(
                        Span(f"Best: {best_streak}", cls="text-xs text-muted-foreground"),
                        cls="ml-4",
                    ),
                    cls="flex flex-col mt-2",
                ),
                # Meta row
                Div(
                    Span(
                        f"Frequency: {str(frequency).title()}",
                        cls="text-xs text-muted-foreground mr-4",
                    ),
                    cls="flex items-center mt-2",
                ),
                # Actions
                Div(
                    Button(
                        "✓ Complete",
                        variant=ButtonT.success,
                        size=Size.xs,
                        **{
                            "hx-post": f"/habits/{uid}/complete",
                            "hx-target": f"#habit-{uid}",
                            "hx-swap": "outerHTML",
                        },
                    ),
                    Button(
                        "Edit",
                        variant=ButtonT.primary,
                        size=Size.xs,
                        **{
                            "hx-get": f"/habits/{uid}/edit",
                            "hx-target": "#modal",
                            "hx-swap": "innerHTML",
                        },
                    ),
                    Button(
                        "View",
                        variant=ButtonT.outline,
                        size=Size.xs,
                        **{"hx-get": f"/habits/{uid}", "hx-target": "body"},
                    ),
                    cls="flex gap-2 mt-3",
                ),
                cls="p-4",
            ),
            id=f"habit-{uid}",
            cls="bg-background shadow-sm border border-border hover:shadow-md transition-shadow",
        )

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        categories: list[str] | None = None,
    ) -> Div:
        """
        Render the habit creation form.

        Two-column layout on desktop, stacked on mobile.

        Args:
            categories: List of category names for dropdown

        Returns:
            Div containing the creation form
        """
        categories = categories or [
            "health",
            "fitness",
            "mindfulness",
            "learning",
            "productivity",
            "creative",
            "social",
            "financial",
            "other",
        ]

        # Left column: Core fields
        left_column = Div(
            # Name (required)
            Div(
                Label("Habit Name", cls="label font-semibold"),
                Input(
                    type="text",
                    name="name",
                    placeholder="What habit do you want to build?",
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
                    placeholder="Describe your habit...",
                    rows="3",
                ),
                cls="mb-4",
            ),
            # Category
            Div(
                Label("Category", cls="label font-semibold"),
                Select(
                    *[Option(cat.title(), value=cat) for cat in categories],
                    name="category",
                ),
                cls="mb-4",
            ),
            # Polarity
            Div(
                Label("Habit Type", cls="label font-semibold"),
                Select(
                    Option("Build (positive habit)", value="build", selected=True),
                    Option("Break (habit to stop)", value="break"),
                    name="polarity",
                ),
                P(
                    "Are you building a new habit or breaking an old one?",
                    cls="text-xs text-muted-foreground mt-1",
                ),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Right column: Scheduling
        right_column = Div(
            # Frequency
            Div(
                Label("Frequency", cls="label font-semibold"),
                Select(
                    Option("Daily", value="daily", selected=True),
                    Option("Weekly", value="weekly"),
                    Option("Monthly", value="monthly"),
                    name="recurrence_pattern",
                ),
                cls="mb-4",
            ),
            # Target days per week (for weekly)
            Div(
                Label("Target Days per Week", cls="label font-semibold"),
                Input(
                    type="number",
                    name="target_days_per_week",
                    value="7",
                    min="1",
                    max="7",
                ),
                cls="mb-4",
            ),
            # Duration
            Div(
                Label("Duration (minutes)", cls="label font-semibold"),
                Input(
                    type="number",
                    name="duration_minutes",
                    placeholder="15",
                    min="1",
                ),
                cls="mb-4",
            ),
            # Difficulty
            Div(
                Label("Difficulty", cls="label font-semibold"),
                Select(
                    Option("Trivial", value="trivial"),
                    Option("Easy", value="easy"),
                    Option("Moderate", value="moderate", selected=True),
                    Option("Challenging", value="challenging"),
                    Option("Hard", value="hard"),
                    name="difficulty",
                ),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Submit buttons
        submit_section = Div(
            ButtonLink(
                "Cancel",
                href="/habits",
                variant=ButtonT.ghost,
                size=Size.lg,
            ),
            Button(
                "Create Habit",
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
            cls="flex justify-end gap-2 pt-6 border-t border-border",
        )

        return Div(
            H2("Create New Habit", cls="text-2xl font-bold mb-6"),
            Form(
                Div(
                    left_column,
                    right_column,
                    cls="flex flex-col lg:flex-row gap-8",
                ),
                submit_section,
                **{
                    "hx-post": "/habits/quick-add",
                    "hx-target": "#view-content",
                    "hx-swap": "innerHTML",
                },
                cls="bg-background shadow-lg p-6",
            ),
            id="create-view",
        )

    # ========================================================================
    # CALENDAR VIEW
    # ========================================================================

    @staticmethod
    def render_calendar_view(
        habits: list[Any],
        current_date: date | None = None,
        calendar_view: str = "month",
    ) -> Div:
        """
        Render the calendar view with Month/Week/Day sub-views.

        Args:
            habits: List of habits to display
            current_date: Current date for calendar (defaults to today)
            calendar_view: Which view to show ("month", "week", "day")

        Returns:
            Div containing the calendar view
        """
        current_date = current_date or date.today()

        # Convert habits to CalendarItems
        calendar_items = []
        for habit in habits:
            try:
                items = habit_to_calendar_items(habit, current_date)
                calendar_items.extend(items)
            except Exception as e:
                logger.warning(f"Failed to convert habit to calendar items: {e}")
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

        # Filter items to date range
        filtered_items = [
            item for item in calendar_items if start_date <= item.start_time.date() <= end_date
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
        nav_header = ActivityCalendarNav.render("habits", current_date, calendar_view)

        # View switcher
        view_switcher = ActivityViewSwitcher.render("habits", current_date, calendar_view)

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


__all__ = ["HabitsViewComponents", "habit_to_calendar_items"]
