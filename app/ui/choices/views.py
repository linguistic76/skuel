"""
Choices Three-View Components
=============================

Three-view choice management interface with List, Create, and Analytics views.
Uses Analytics as third tab (not Calendar - choices are not time-based).

Usage:
    from ui.choices.views import ChoicesViewComponents

    # Main tabs
    tabs = ChoicesViewComponents.render_view_tabs("list")

    # Individual views
    list_view = ChoicesViewComponents.render_list_view(choices, filters, stats)
    create_view = ChoicesViewComponents.render_create_view()
    analytics_view = ChoicesViewComponents.render_analytics_view(analytics_data)
"""

from typing import Any

from fasthtml.common import H3, Div, Option, P, Span

from core.models.choice.choice import Choice
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.forms import Input, Label, Select, Textarea
from ui.layout import Size
from ui.patterns.activity_views_base import (
    ActivityCreateForm,
    ActivityListFilters,
    ActivityViewTabs,
)
from ui.patterns.entity_card import EntityCard
from ui.patterns.stats_grid import StatsGrid


class ChoicesViewComponents:
    """
    Three-view choice management interface.

    Views:
    - List: Decision list with status indicators
    - Create: Choice creation form with options
    - Analytics: Decision patterns and satisfaction analysis
    """

    # ========================================================================
    # MAIN TAB NAVIGATION
    # ========================================================================

    @staticmethod
    def render_view_tabs(active_view: str = "list") -> Div:
        """Render the main view tabs (List, Create, Analytics)."""
        return ActivityViewTabs.list_create_analytics("choices", active_view)

    # ========================================================================
    # LIST VIEW
    # ========================================================================

    @staticmethod
    def render_list_view(
        choices: list[Any],
        filters: dict[str, Any] | None = None,
        stats: dict[str, int] | None = None,
    ) -> Div:
        """Render the choice list with status indicators."""
        filters = filters or {}
        stats = stats or {}

        stats_bar = StatsGrid(
            [
                {"label": "Total", "value": stats.get("total", 0)},
                {"label": "Pending", "value": stats.get("pending", 0), "trend": "neutral"},
                {"label": "Decided", "value": stats.get("decided", 0), "trend": "up" if stats.get("decided", 0) > 0 else "neutral"},
            ],
            cols=3,
        )

        filter_bar = ActivityListFilters.render(
            domain="choices",
            status_options=[("all", "All"), ("pending", "Pending"), ("decided", "Decided"), ("implemented", "Implemented")],
            sort_options=[("deadline", "Deadline"), ("priority", "Priority"), ("created_at", "Created")],
            current_status=filters.get("status", "pending"),
            current_sort=filters.get("sort_by", "deadline"),
            list_target="#choice-list",
        )

        choice_items = [ChoicesViewComponents._render_choice_item(choice) for choice in choices]

        choice_list = Div(
            *choice_items
            if choice_items
            else [
                P(
                    "No decisions found. Create one to get started!",
                    cls="text-muted-foreground text-center py-8",
                )
            ],
            id="choice-list",
            cls="space-y-3",
        )

        return Div(
            stats_bar, filter_bar, choice_list,
            Div(id="modal"),
            id="list-view",
        )

    @staticmethod
    def _render_choice_item(choice: Choice) -> Div:
        """Render a single choice item for the list."""
        uid = choice.uid
        status = choice.status or "pending"
        deadline = choice.decision_deadline

        from core.utils.type_converters import normalize_enum_str

        status_str = normalize_enum_str(status, "pending")

        metadata: list[Any] = []
        if deadline:
            metadata.append(Span(f"Deadline: {deadline}", cls="text-xs text-muted-foreground"))

        action_buttons: list[Any] = []
        if status_str == "pending":
            action_buttons.append(
                Button("Decide", variant=ButtonT.success, size=Size.xs, **{"hx-get": f"/choices/{uid}/decide", "hx-target": "#modal"})
            )
        action_buttons.extend([
            Button("View", variant=ButtonT.outline, size=Size.xs, **{"hx-get": f"/choices/{uid}", "hx-target": "body"}),
            Button("Edit", variant=ButtonT.ghost, size=Size.xs, **{"hx-get": f"/choices/{uid}/edit", "hx-target": "#modal"}),
        ])
        actions = Div(*action_buttons, cls="flex gap-2")

        return EntityCard(
            title=choice.title,
            description=choice.description or "",
            status=str(choice.status) if choice.status else None,
            priority=str(choice.priority) if choice.priority else None,
            metadata=metadata,
            actions=actions,
            id=f"choice-{uid}",
        )

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        choice_types: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> Div:
        """Render the choice creation form."""
        choice_types = choice_types or ["binary", "multiple", "ranking", "strategic", "operational"]
        domains = domains or ["personal", "business", "health", "finance", "social"]

        left_column = Div(
            Div(
                Label("Decision Title", cls="label font-semibold"),
                Input(type="text", name="title", placeholder="What decision do you need to make?", required=True, autofocus=True),
                cls="mb-4",
            ),
            Div(
                Label("Description", cls="label font-semibold"),
                Textarea(name="description", placeholder="Describe the decision context...", rows="4", required=True),
                cls="mb-4",
            ),
            Div(
                Label("Decision Type", cls="label font-semibold"),
                Select(*[Option(t.title(), value=t) for t in choice_types], name="choice_type"),
                P("Binary (yes/no), Multiple options, Ranking, etc.", cls="text-xs text-muted-foreground mt-1"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        right_column = Div(
            Div(
                Label("Domain", cls="label font-semibold"),
                Select(*[Option(d.title(), value=d) for d in domains], name="domain"),
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
                Label("Decision Deadline", cls="label font-semibold"),
                Input(type="datetime-local", name="decision_deadline"),
                P("When do you need to decide by?", cls="text-xs text-muted-foreground mt-1"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Options section (Alpine.js managed)
        options_section = Div(
            H3("Decision Options", cls="text-lg font-semibold mb-4"),
            P("Add at least 2 options for this decision.", cls="text-sm text-muted-foreground mb-4"),
            Div(
                Card(
                    Div(
                        Span("Option ", Span(**{"x-text": "index + 1"}), cls="font-medium"),
                        Button(
                            "Remove", type="button", variant=ButtonT.ghost, size=Size.xs, cls="text-error",
                            **{"x-show": "canRemove()", "x-on:click": "removeOption(index)"},
                        ),
                        cls="flex justify-between items-center mb-2",
                    ),
                    Div(
                        Label("Title", cls="label text-sm"),
                        Input(
                            type="text", size=Size.sm, placeholder="Option title...", required=True,
                            **{"x-model": "option.title", "x-bind:name": "'options[' + index + '].title'"},
                        ),
                        cls="mb-2",
                    ),
                    Div(
                        Label("Description", cls="label text-sm"),
                        Textarea(
                            size=Size.sm, rows="2", placeholder="Describe this option...", required=True,
                            **{"x-model": "option.description", "x-bind:name": "'options[' + index + '].description'"},
                        ),
                    ),
                    cls="bg-muted p-4 mb-3",
                    **{"x-bind:key": "index"},
                ),
                **{"x-for": "(option, index) in options"},
            ),
            Button(
                "+ Add Another Option", type="button", variant=ButtonT.outline, size=Size.sm, cls="mt-2",
                **{"x-on:click": "addOption()"},
            ),
            cls="mb-6 pt-6 border-t border-border",
        )

        # Custom submit section with validation
        from ui.buttons import ButtonLink

        submit_section = Div(
            Div(
                P("Please fill in all option titles and descriptions.", cls="text-error text-sm"),
                **{"x-show": "!isValid()"},
            ),
            ButtonLink("Cancel", href="/choices", variant=ButtonT.ghost, size=Size.lg),
            Button(
                "Create Decision", type="submit", variant=ButtonT.primary, size=Size.lg,
                **{"x-bind:disabled": "!isValid()"},
            ),
            Button(
                "Create & Add Another", type="submit", name="add_another", value="true",
                variant=ButtonT.outline, size=Size.lg,
                **{"x-bind:disabled": "!isValid()"},
            ),
            cls="flex justify-end items-center gap-2 pt-6 border-t border-border",
        )

        return ActivityCreateForm(
            "choices", "Decision", left_column, right_column,
            extra_sections=[options_section, submit_section],
            form_attrs={"x-data": "choiceOptions()"},
            include_default_submit=False,
        )

    # ========================================================================
    # ANALYTICS VIEW
    # ========================================================================

    @staticmethod
    def render_analytics_view(
        analytics_data: dict[str, Any] | None = None,
    ) -> Div:
        """Render the decision analytics view."""
        analytics_data = analytics_data or {}

        quality_section = Card(
            H3("Decision Quality", cls="text-lg font-semibold mb-4"),
            Div(
                Div(
                    P("Satisfaction Rate", cls="text-sm text-muted-foreground"),
                    P(f"{analytics_data.get('satisfaction_rate', 0):.0%}", cls="text-3xl font-bold text-green-600"),
                    cls="text-center p-4 bg-muted rounded-lg",
                ),
                Div(
                    P("Decisions Made", cls="text-sm text-muted-foreground"),
                    P(str(analytics_data.get("total_decisions", 0)), cls="text-3xl font-bold text-blue-600"),
                    cls="text-center p-4 bg-muted rounded-lg",
                ),
                Div(
                    P("On-Time Rate", cls="text-sm text-muted-foreground"),
                    P(f"{analytics_data.get('on_time_rate', 0):.0%}", cls="text-3xl font-bold text-purple-600"),
                    cls="text-center p-4 bg-muted rounded-lg",
                ),
                cls="grid grid-cols-3 gap-4 mb-6",
            ),
            cls="bg-background shadow-lg p-6 mb-6",
        )

        patterns_section = Card(
            H3("Decision Patterns", cls="text-lg font-semibold mb-4"),
            Div(
                P("Pattern analysis helps you understand your decision-making tendencies.", cls="text-muted-foreground mb-4"),
                Div(
                    P("Charts will be displayed here", cls="text-muted-foreground text-center py-12 border border-dashed border-border rounded-lg"),
                    cls="mb-4",
                ),
            ),
            cls="bg-background shadow-lg p-6 mb-6",
        )

        outcomes_section = Card(
            H3("Recent Outcomes", cls="text-lg font-semibold mb-4"),
            Div(
                P("Track how your past decisions turned out.", cls="text-muted-foreground mb-4"),
                P("No outcomes recorded yet.", cls="text-muted-foreground text-center py-8")
                if not analytics_data.get("outcomes")
                else "",
            ),
            cls="bg-background shadow-lg p-6",
        )

        return Div(quality_section, patterns_section, outcomes_section, id="analytics-view")


__all__ = ["ChoicesViewComponents"]
