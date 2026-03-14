"""
Goals Three-View Components
===========================

Three-view goal management interface with List, Create, and Calendar views.

Usage:
    from ui.goals.views import GoalsViewComponents

    # Main tabs
    tabs = GoalsViewComponents.render_view_tabs("list")

    # Individual views
    list_view = GoalsViewComponents.render_list_view(goals, filters, stats)
    create_view = GoalsViewComponents.render_create_view(categories)
    calendar_view = GoalsViewComponents.render_calendar_view(goals, today, "month")
"""

from datetime import date
from typing import Any

from fasthtml.common import Div, Option, P, Span

from core.models.goal.goal import Goal
from ui.buttons import Button, ButtonT
from ui.calendar.converters import goal_to_calendar_item
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
        """Render the main view tabs (List, Create, Calendar)."""
        return ActivityViewTabs.list_create_calendar("goals", active_view)

    # ========================================================================
    # LIST VIEW
    # ========================================================================

    @staticmethod
    def render_list_view(
        goals: list[Any],
        filters: dict[str, Any] | None = None,
        stats: dict[str, int] | None = None,
        _categories: list[str] | None = None,
    ) -> Div:
        """Render the sortable, filterable goal list."""
        filters = filters or {}
        stats = stats or {}

        stats_bar = StatsGrid(
            [
                {"label": "Total", "value": stats.get("total", 0)},
                {"label": "Active", "value": stats.get("active", 0), "trend": "up" if stats.get("active", 0) > 0 else "neutral"},
                {"label": "Completed", "value": stats.get("completed", 0)},
            ],
            cols=3,
        )

        filter_bar = ActivityListFilters.render(
            domain="goals",
            status_options=[("all", "All"), ("active", "Active"), ("completed", "Completed"), ("paused", "Paused")],
            sort_options=[("target_date", "Target Date"), ("priority", "Priority"), ("progress", "Progress"), ("created_at", "Created")],
            current_status=filters.get("status", "active"),
            current_sort=filters.get("sort_by", "target_date"),
            list_target="#goal-list",
        )

        goal_items = [GoalsViewComponents._render_goal_item(goal) for goal in goals]

        goal_list = Div(
            *goal_items
            if goal_items
            else [
                P(
                    "No goals found. Create one to get started!",
                    cls="text-muted-foreground text-center py-8",
                )
            ],
            id="goal-list",
            cls="space-y-3",
        )

        return Div(stats_bar, filter_bar, goal_list, id="list-view")

    @staticmethod
    def _render_goal_item(goal: Goal, is_pinned: bool = False) -> Div:
        """Render a single goal item for the list."""
        from ui.patterns.pin_button import PinButton

        uid = goal.uid
        progress = goal.current_value or 0
        target_date = goal.target_date

        metadata: list[Any] = []
        if progress > 0:
            metadata.append(
                Div(
                    Span(f"Progress: {int(progress)}%", cls="text-xs text-muted-foreground"),
                    Progress(value=int(progress), max=100, cls="progress progress-primary w-full h-2 mt-1"),
                    cls="w-full",
                )
            )
        if target_date:
            metadata.append(Span(f"Due: {target_date}", cls="text-xs text-muted-foreground"))

        actions = Div(
            Button("View", variant=ButtonT.outline, size=Size.xs, **{"hx-get": f"/goals/{uid}", "hx-target": "body"}),
            Button("Edit", variant=ButtonT.ghost, size=Size.xs, **{"hx-get": f"/goals/{uid}/edit", "hx-target": "#modal"}),
            PinButton(entity_uid=uid, is_pinned=is_pinned, show_text=True, size="xs"),
            cls="flex gap-2",
        )

        return EntityCard(
            title=goal.title,
            description=goal.description or "",
            status=str(goal.status) if goal.status else None,
            priority=str(goal.priority) if goal.priority else None,
            metadata=metadata,
            actions=actions,
            id=f"goal-{uid}",
        )

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        categories: list[str] | None = None,
        timeframes: list[tuple[str, str]] | None = None,
    ) -> Div:
        """Render the goal creation form."""
        categories = categories or [
            "business", "health", "education", "personal",
            "tech", "creative", "social", "research",
        ]
        timeframes = timeframes or [
            ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly"),
            ("quarterly", "Quarterly"), ("yearly", "Yearly"), ("multi_year", "Multi-Year"),
        ]

        left_column = Div(
            Div(
                Label("Goal Title", cls="label font-semibold"),
                Input(type="text", name="title", placeholder="What do you want to achieve?", required=True, autofocus=True),
                cls="mb-4",
            ),
            Div(
                Label("Description", cls="label font-semibold"),
                Textarea(name="description", placeholder="Describe your goal in detail...", rows="4"),
                cls="mb-4",
            ),
            Div(
                Label("Why is this important?", cls="label font-semibold"),
                Textarea(name="why_important", placeholder="What motivates you to achieve this goal?", rows="3"),
                cls="mb-4",
            ),
            Div(
                Label("Category", cls="label font-semibold"),
                Select(*[Option(cat.title(), value=cat) for cat in categories], name="domain"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        right_column = Div(
            Div(
                Label("Timeframe", cls="label font-semibold"),
                Select(
                    *[Option(label, value=value, selected=(value == "quarterly")) for value, label in timeframes],
                    name="timeframe",
                ),
                P("How long do you have to achieve this goal?", cls="text-xs text-muted-foreground mt-1"),
                cls="mb-4",
            ),
            Div(
                Label("Target Date", cls="label font-semibold"),
                Input(type="date", name="target_date"),
                P("When do you want to complete this goal?", cls="text-xs text-muted-foreground mt-1"),
                cls="mb-4",
            ),
            Div(
                Label("Priority", cls="label font-semibold"),
                Select(
                    Option("P1 - Critical", value="critical"),
                    Option("P2 - High", value="high"),
                    Option("P3 - Medium", value="medium", selected=True),
                    Option("P4 - Low", value="low"),
                    name="priority",
                ),
                cls="mb-4",
            ),
            Div(
                Label("Target Value (optional)", cls="label font-semibold"),
                Input(type="number", name="target_value", placeholder="e.g., 100", min="0"),
                P("Numeric target for measurable goals", cls="text-xs text-muted-foreground mt-1"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        return ActivityCreateForm("goals", "Goal", left_column, right_column)

    # ========================================================================
    # CALENDAR VIEW
    # ========================================================================

    @staticmethod
    def render_calendar_view(
        goals: list[Any],
        current_date: date | None = None,
        calendar_view: str = "month",
    ) -> Div:
        """Render the calendar view with Month/Week/Day sub-views."""
        return render_activity_calendar(
            domain="goals",
            entities=goals,
            converter=goal_to_calendar_item,
            current_date=current_date,
            calendar_view=calendar_view,
        )

    @staticmethod
    def render_hierarchy_view(
        root_uid: str,
        root_goal: Goal,
    ) -> Div:
        """Render goal hierarchy tree view."""
        from fasthtml.common import H2

        from ui.layout import Row, Stack
        from ui.patterns.tree_view import TreeView

        return Stack(
            Div(
                H2(f"Hierarchy: {root_goal.title}", cls="text-2xl font-bold"),
                P("Explore goal breakdown and dependencies", cls="text-muted-foreground text-sm"),
                Row(
                    Button("Expand All", variant="secondary", size="sm", **{"x-on:click": "expandAll()"}),
                    Button("Collapse All", variant="secondary", size="sm", **{"x-on:click": "collapseAll()"}),
                    Button("Select All", variant="secondary", size="sm", **{"x-on:click": "selectAll()"}, **{"x-show": "showCheckboxes"}),
                    gap=2,
                ),
                cls="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6 gap-4",
            ),
            TreeView(
                root_uid=root_uid,
                entity_type="goal",
                children_endpoint="/api/goals/{uid}/children",
                move_endpoint="/api/goals/{uid}/move",
                show_checkboxes=True,
                keyboard_nav=True,
                draggable=True,
            ),
            Div(**{"x-show": "selected.length > 0", "x-cloak": True})(
                Div(
                    Div(
                        Span(**{"x-text": "`${selected.length} items selected`"}, cls="font-medium"),
                        Row(
                            Button("Deselect All", variant="secondary", size="sm", **{"x-on:click": "deselectAll()"}),
                            Button("Delete Selected", variant="danger", size="sm", **{"x-on:click": "bulkDelete()"}),
                            gap=2,
                        ),
                        cls="flex items-center justify-between",
                    ),
                    cls="bg-muted rounded-lg border border-border p-4",
                ),
            ),
            gap=6,
        )


__all__ = ["GoalsViewComponents", "goal_to_calendar_item"]
