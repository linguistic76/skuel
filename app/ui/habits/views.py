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

from datetime import date
from typing import Any

from fasthtml.common import Div, Option, P, Span

from core.models.habit.habit import Habit as Habit
from ui.buttons import Button, ButtonT
from ui.calendar.converters import habit_to_calendar_items
from ui.feedback import Progress
from ui.forms import Input, Label, Select, Textarea
from ui.layout import Size
from ui.patterns.activity_views_base import (
    ActivityCreateForm,
    ActivityListFilters,
    ActivityViewTabs,
    render_activity_calendar,
)
from ui.patterns.entity_card import EntityCard
from ui.patterns.stats_grid import StatsGrid


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
        """Render the main view tabs (List, Create, Calendar)."""
        return ActivityViewTabs.list_create_calendar("habits", active_view)

    # ========================================================================
    # LIST VIEW
    # ========================================================================

    @staticmethod
    def render_list_view(
        habits: list[Any],
        filters: dict[str, Any] | None = None,
        stats: dict[str, int] | None = None,
        _categories: list[str] | None = None,
    ) -> Div:
        """Render the habit list with streak indicators."""
        filters = filters or {}
        stats = stats or {}

        stats_bar = StatsGrid(
            [
                {"label": "Total", "value": stats.get("total", 0)},
                {"label": "Active Streaks", "value": stats.get("active_streaks", 0), "trend": "up" if stats.get("active_streaks", 0) > 0 else "neutral"},
                {"label": "Completed Today", "value": stats.get("completed_today", 0)},
            ],
            cols=3,
        )

        filter_bar = ActivityListFilters.render(
            domain="habits",
            status_options=[("all", "All"), ("active", "Active"), ("paused", "Paused")],
            sort_options=[("streak", "Streak"), ("name", "Name"), ("created_at", "Created")],
            current_status=filters.get("status", "active"),
            current_sort=filters.get("sort_by", "streak"),
            list_target="#habit-list",
        )

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

        return Div(stats_bar, filter_bar, habit_list, id="list-view")

    @staticmethod
    def _render_habit_item(habit: Habit) -> Div:
        """Render a single habit item for the list."""
        uid = habit.uid
        current_streak = habit.current_streak or 0
        best_streak = habit.best_streak or 0
        frequency = habit.recurrence_pattern or "daily"

        streak_color = "text-success" if current_streak > 0 else "text-muted-foreground"

        metadata: list[Any] = [
            # Streak display
            Div(
                Div(
                    Span("🔥", cls="text-lg mr-1"),
                    Span(f"{current_streak}", cls=f"font-bold {streak_color}"),
                    Span(" day streak", cls="text-muted-foreground text-sm ml-1"),
                    cls="flex items-center",
                ),
                Div(
                    Progress(
                        value=min(current_streak, best_streak) if best_streak > 0 else current_streak,
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
                cls="flex flex-col w-full",
            ),
            Span(f"Frequency: {str(frequency).title()}", cls="text-xs text-muted-foreground"),
        ]

        actions = Div(
            Button(
                "✓ Complete", variant=ButtonT.success, size=Size.xs,
                **{"hx-post": f"/habits/{uid}/complete", "hx-target": f"#habit-{uid}", "hx-swap": "outerHTML"},
            ),
            Button("Edit", variant=ButtonT.primary, size=Size.xs, **{"hx-get": f"/habits/{uid}/edit", "hx-target": "#modal", "hx-swap": "innerHTML"}),
            Button("View", variant=ButtonT.outline, size=Size.xs, **{"hx-get": f"/habits/{uid}", "hx-target": "body"}),
            cls="flex gap-2",
        )

        return EntityCard(
            title=habit.title,
            description=habit.description or "",
            status=str(habit.status) if habit.status else None,
            metadata=metadata,
            actions=actions,
            id=f"habit-{uid}",
        )

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        categories: list[str] | None = None,
    ) -> Div:
        """Render the habit creation form."""
        categories = categories or [
            "health", "fitness", "mindfulness", "learning",
            "productivity", "creative", "social", "financial", "other",
        ]

        left_column = Div(
            Div(
                Label("Habit Name", cls="label font-semibold"),
                Input(type="text", name="name", placeholder="What habit do you want to build?", required=True, autofocus=True),
                cls="mb-4",
            ),
            Div(
                Label("Description", cls="label font-semibold"),
                Textarea(name="description", placeholder="Describe your habit...", rows="3"),
                cls="mb-4",
            ),
            Div(
                Label("Category", cls="label font-semibold"),
                Select(*[Option(cat.title(), value=cat) for cat in categories], name="category"),
                cls="mb-4",
            ),
            Div(
                Label("Habit Type", cls="label font-semibold"),
                Select(
                    Option("Build (positive habit)", value="build", selected=True),
                    Option("Break (habit to stop)", value="break"),
                    name="polarity",
                ),
                P("Are you building a new habit or breaking an old one?", cls="text-xs text-muted-foreground mt-1"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        right_column = Div(
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
            Div(
                Label("Target Days per Week", cls="label font-semibold"),
                Input(type="number", name="target_days_per_week", value="7", min="1", max="7"),
                cls="mb-4",
            ),
            Div(
                Label("Duration (minutes)", cls="label font-semibold"),
                Input(type="number", name="duration_minutes", placeholder="15", min="1"),
                cls="mb-4",
            ),
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

        return ActivityCreateForm("habits", "Habit", left_column, right_column)

    # ========================================================================
    # CALENDAR VIEW
    # ========================================================================

    @staticmethod
    def render_calendar_view(
        habits: list[Any],
        current_date: date | None = None,
        calendar_view: str = "month",
    ) -> Div:
        """Render the calendar view with Month/Week/Day sub-views."""
        return render_activity_calendar(
            domain="habits",
            entities=habits,
            converter=habit_to_calendar_items,
            current_date=current_date,
            calendar_view=calendar_view,
            converter_returns_list=True,
            converter_extra_args=(current_date or date.today(),),
        )


__all__ = ["HabitsViewComponents", "habit_to_calendar_items"]
