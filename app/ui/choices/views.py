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

from fasthtml.common import H2, H3, A, Form, P

from core.models.choice.choice import Choice
from core.utils.logging import get_logger
from ui.daisy_components import (
    Button,
    Div,
    Input,
    Label,
    Option,
    Select,
    Span,
    Textarea,
)
from ui.patterns.activity_views_base import ActivityViewTabs

logger = get_logger("skuel.components.choices_views")


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
        """
        Render the main view tabs (List, Create, Analytics).

        Args:
            active_view: Currently active view ("list", "create", "analytics")

        Returns:
            Div containing the tab navigation
        """
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
        """
        Render the choice list with status indicators.

        Args:
            choices: List of choices to display
            filters: Current filter values
            stats: Choice statistics

        Returns:
            Div containing the list view
        """
        filters = filters or {}
        stats = stats or {}

        # Stats bar
        stats_bar = Div(
            Div(
                Span("Total: ", cls="text-gray-500"),
                Span(str(stats.get("total", 0)), cls="font-bold"),
                cls="mr-4",
            ),
            Div(
                Span("Pending: ", cls="text-gray-500"),
                Span(str(stats.get("pending", 0)), cls="font-bold text-yellow-600"),
                cls="mr-4",
            ),
            Div(
                Span("Decided: ", cls="text-gray-500"),
                Span(str(stats.get("decided", 0)), cls="font-bold text-green-600"),
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
                        "Pending",
                        value="pending",
                        selected=filters.get("status", "pending") == "pending",
                    ),
                    Option("Decided", value="decided", selected=filters.get("status") == "decided"),
                    Option(
                        "Implemented",
                        value="implemented",
                        selected=filters.get("status") == "implemented",
                    ),
                    name="filter_status",
                    cls="select select-bordered select-sm",
                    **{
                        "hx-get": "/choices/list-fragment",
                        "hx-target": "#choice-list",
                        "hx-include": "[name^='filter_'], [name='sort_by']",
                    },
                ),
                cls="mr-4",
            ),
            Div(
                Label("Sort:", cls="mr-2 text-sm"),
                Select(
                    Option(
                        "Deadline",
                        value="deadline",
                        selected=filters.get("sort_by", "deadline") == "deadline",
                    ),
                    Option(
                        "Priority", value="priority", selected=filters.get("sort_by") == "priority"
                    ),
                    Option(
                        "Created",
                        value="created_at",
                        selected=filters.get("sort_by") == "created_at",
                    ),
                    name="sort_by",
                    cls="select select-bordered select-sm",
                    **{
                        "hx-get": "/choices/list-fragment",
                        "hx-target": "#choice-list",
                        "hx-include": "[name^='filter_']",
                    },
                ),
            ),
            cls="flex items-center mb-4",
        )

        # Choice list
        choice_items = [ChoicesViewComponents._render_choice_item(choice) for choice in choices]

        choice_list = Div(
            *choice_items
            if choice_items
            else [
                P(
                    "No decisions found. Create one to get started!",
                    cls="text-gray-500 text-center py-8",
                )
            ],
            id="choice-list",
            cls="space-y-3",
        )

        return Div(
            stats_bar,
            filter_bar,
            choice_list,
            # Modal container for HTMX-loaded modals (Edit, Decide, Add Option)
            Div(id="modal"),
            id="list-view",
        )

    @staticmethod
    def _render_choice_item(choice: Choice) -> Div:
        """Render a single choice item for the list."""
        uid = choice.uid
        title = choice.title
        description = choice.description or ""
        status = choice.status or "pending"
        priority = choice.priority or "medium"
        deadline = choice.decision_deadline

        # Status color
        status_str = str(status).lower().replace("choicestatus.", "")
        status_colors = {
            "pending": "badge-warning",
            "decided": "badge-success",
            "implemented": "badge-info",
            "evaluated": "badge-primary",
        }
        status_badge = status_colors.get(status_str, "badge-ghost")

        # Priority color
        priority_str = str(priority).lower()
        priority_colors = {
            "critical": "text-red-600",
            "high": "text-orange-600",
            "medium": "text-blue-600",
            "low": "text-gray-600",
        }
        priority_color = priority_colors.get(priority_str, "text-gray-600")

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
                    cls="text-gray-600 text-sm mt-1",
                )
                if description
                else "",
                # Meta row
                Div(
                    Span(f"Priority: {priority_str.title()}", cls=f"text-xs {priority_color} mr-4"),
                    Span(f"Deadline: {deadline}", cls="text-xs text-gray-500") if deadline else "",
                    cls="flex items-center mt-2",
                ),
                # Actions
                Div(
                    Button(
                        "Decide",
                        cls="btn btn-xs btn-success",
                        **{"hx-get": f"/choices/{uid}/decide", "hx-target": "#modal"},
                    )
                    if status_str == "pending"
                    else "",
                    Button(
                        "View",
                        cls="btn btn-xs btn-outline",
                        **{"hx-get": f"/choices/{uid}", "hx-target": "body"},
                    ),
                    Button(
                        "Edit",
                        cls="btn btn-xs btn-ghost",
                        **{"hx-get": f"/choices/{uid}/edit", "hx-target": "#modal"},
                    ),
                    cls="flex gap-2 mt-3",
                ),
                cls="p-4",
            ),
            id=f"choice-{uid}",
            cls="card bg-base-100 shadow-sm border border-base-200 hover:shadow-md transition-shadow",
        )

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        choice_types: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> Div:
        """
        Render the choice creation form.

        Args:
            choice_types: List of choice type names
            domains: List of domain names

        Returns:
            Div containing the creation form
        """
        choice_types = choice_types or ["binary", "multiple", "ranking", "strategic", "operational"]
        # Must match Domain enum values in core/models/enums/entity_enums.py
        domains = domains or ["personal", "business", "health", "finance", "social"]

        # Left column: Core fields
        left_column = Div(
            # Title (required)
            Div(
                Label("Decision Title", cls="label font-semibold"),
                Input(
                    type="text",
                    name="title",
                    placeholder="What decision do you need to make?",
                    cls="input input-bordered w-full",
                    required=True,
                    autofocus=True,
                ),
                cls="mb-4",
            ),
            # Description (required)
            Div(
                Label("Description", cls="label font-semibold"),
                Textarea(
                    name="description",
                    placeholder="Describe the decision context...",
                    rows="4",
                    cls="textarea textarea-bordered w-full",
                    required=True,
                ),
                cls="mb-4",
            ),
            # Choice Type
            Div(
                Label("Decision Type", cls="label font-semibold"),
                Select(
                    *[Option(t.title(), value=t) for t in choice_types],
                    name="choice_type",
                    cls="select select-bordered w-full",
                ),
                P(
                    "Binary (yes/no), Multiple options, Ranking, etc.",
                    cls="text-xs text-gray-500 mt-1",
                ),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Right column: Classification and deadline
        right_column = Div(
            # Domain
            Div(
                Label("Domain", cls="label font-semibold"),
                Select(
                    *[Option(d.title(), value=d) for d in domains],
                    name="domain",
                    cls="select select-bordered w-full",
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
            # Decision Deadline
            Div(
                Label("Decision Deadline", cls="label font-semibold"),
                Input(
                    type="datetime-local",
                    name="decision_deadline",
                    cls="input input-bordered w-full",
                ),
                P("When do you need to decide by?", cls="text-xs text-gray-500 mt-1"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Options section (Alpine.js managed)
        options_section = Div(
            H3("Decision Options", cls="text-lg font-semibold mb-4"),
            P("Add at least 2 options for this decision.", cls="text-sm text-gray-500 mb-4"),
            # Options container with x-for loop
            Div(
                # Template for each option (Alpine x-for)
                Div(
                    Div(
                        Span(
                            "Option ",
                            Span(**{"x-text": "index + 1"}),
                            cls="font-medium",
                        ),
                        Button(
                            "Remove",
                            type="button",
                            cls="btn btn-ghost btn-xs text-error",
                            **{
                                "x-show": "canRemove()",
                                "x-on:click": "removeOption(index)",
                            },
                        ),
                        cls="flex justify-between items-center mb-2",
                    ),
                    Div(
                        Label("Title", cls="label text-sm"),
                        Input(
                            type="text",
                            cls="input input-bordered input-sm w-full",
                            placeholder="Option title...",
                            required=True,
                            **{
                                "x-model": "option.title",
                                "x-bind:name": "'options[' + index + '].title'",
                            },
                        ),
                        cls="mb-2",
                    ),
                    Div(
                        Label("Description", cls="label text-sm"),
                        Textarea(
                            cls="textarea textarea-bordered textarea-sm w-full",
                            rows="2",
                            placeholder="Describe this option...",
                            required=True,
                            **{
                                "x-model": "option.description",
                                "x-bind:name": "'options[' + index + '].description'",
                            },
                        ),
                    ),
                    cls="card bg-base-200 p-4 mb-3",
                    **{"x-bind:key": "index"},
                ),
                **{"x-for": "(option, index) in options"},
            ),
            # Add option button
            Button(
                "+ Add Another Option",
                type="button",
                cls="btn btn-outline btn-sm mt-2",
                **{"x-on:click": "addOption()"},
            ),
            cls="mb-6 pt-6 border-t border-base-200",
        )

        # Submit buttons
        submit_section = Div(
            # Validation message
            Div(
                P(
                    "Please fill in all option titles and descriptions.",
                    cls="text-error text-sm",
                ),
                **{"x-show": "!isValid()"},
            ),
            A(
                "Cancel",
                href="/choices",
                cls="btn btn-ghost btn-lg",
            ),
            Button(
                "Create Decision",
                type="submit",
                cls="btn btn-primary btn-lg",
                **{"x-bind:disabled": "!isValid()"},
            ),
            Button(
                "Create & Add Another",
                type="submit",
                name="add_another",
                value="true",
                cls="btn btn-outline btn-lg",
                **{"x-bind:disabled": "!isValid()"},
            ),
            cls="flex justify-end items-center gap-2 pt-6 border-t border-base-200",
        )

        return Div(
            H2("Create New Decision", cls="text-2xl font-bold mb-6"),
            Form(
                Div(
                    left_column,
                    right_column,
                    cls="flex flex-col lg:flex-row gap-8",
                ),
                options_section,
                submit_section,
                **{
                    "hx-post": "/choices/quick-add",
                    "hx-target": "#view-content",
                    "hx-swap": "innerHTML",
                    "x-data": "choiceOptions()",
                },
                cls="card bg-base-100 shadow-lg p-6",
            ),
            id="create-view",
        )

    # ========================================================================
    # ANALYTICS VIEW
    # ========================================================================

    @staticmethod
    def render_analytics_view(
        analytics_data: dict[str, Any] | None = None,
    ) -> Div:
        """
        Render the decision analytics view.

        Args:
            analytics_data: Analytics data including satisfaction rates, patterns

        Returns:
            Div containing the analytics view
        """
        analytics_data = analytics_data or {}

        # Decision quality metrics
        quality_section = Div(
            H3("Decision Quality", cls="text-lg font-semibold mb-4"),
            Div(
                # Satisfaction rate
                Div(
                    P("Satisfaction Rate", cls="text-sm text-gray-500"),
                    P(
                        f"{analytics_data.get('satisfaction_rate', 0):.0%}",
                        cls="text-3xl font-bold text-green-600",
                    ),
                    cls="text-center p-4 bg-base-200 rounded-lg",
                ),
                # Decisions made
                Div(
                    P("Decisions Made", cls="text-sm text-gray-500"),
                    P(
                        str(analytics_data.get("total_decisions", 0)),
                        cls="text-3xl font-bold text-blue-600",
                    ),
                    cls="text-center p-4 bg-base-200 rounded-lg",
                ),
                # On-time decisions
                Div(
                    P("On-Time Rate", cls="text-sm text-gray-500"),
                    P(
                        f"{analytics_data.get('on_time_rate', 0):.0%}",
                        cls="text-3xl font-bold text-purple-600",
                    ),
                    cls="text-center p-4 bg-base-200 rounded-lg",
                ),
                cls="grid grid-cols-3 gap-4 mb-6",
            ),
            cls="card bg-base-100 shadow-lg p-6 mb-6",
        )

        # Decision patterns
        patterns_section = Div(
            H3("Decision Patterns", cls="text-lg font-semibold mb-4"),
            Div(
                P(
                    "Pattern analysis helps you understand your decision-making tendencies.",
                    cls="text-gray-500 mb-4",
                ),
                # Placeholder for charts
                Div(
                    P(
                        "Charts will be displayed here",
                        cls="text-gray-400 text-center py-12 border border-dashed border-gray-300 rounded-lg",
                    ),
                    cls="mb-4",
                ),
            ),
            cls="card bg-base-100 shadow-lg p-6 mb-6",
        )

        # Recent outcomes
        outcomes_section = Div(
            H3("Recent Outcomes", cls="text-lg font-semibold mb-4"),
            Div(
                P("Track how your past decisions turned out.", cls="text-gray-500 mb-4"),
                P("No outcomes recorded yet.", cls="text-gray-400 text-center py-8")
                if not analytics_data.get("outcomes")
                else "",
            ),
            cls="card bg-base-100 shadow-lg p-6",
        )

        return Div(
            quality_section,
            patterns_section,
            outcomes_section,
            id="analytics-view",
        )


__all__ = ["ChoicesViewComponents"]
