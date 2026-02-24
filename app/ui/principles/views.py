"""
Principles Three-View Components
================================

Three-view principle management interface with List, Create, and Analytics views.
Uses Analytics as third tab (not Calendar - principles are not time-based).

Usage:
    from ui.principles.views import PrinciplesViewComponents

    # Main tabs
    tabs = PrinciplesViewComponents.render_view_tabs("list")

    # Individual views
    list_view = PrinciplesViewComponents.render_list_view(principles, filters, stats)
    create_view = PrinciplesViewComponents.render_create_view()
    analytics_view = PrinciplesViewComponents.render_analytics_view(analytics_data)
"""

from typing import Any

from fasthtml.common import H2, H3, A, Form, P

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

logger = get_logger("skuel.components.principles_views")


class PrinciplesViewComponents:
    """
    Three-view principle management interface.

    Views:
    - List: Principle list with strength indicators
    - Create: Principle creation form
    - Analytics: Principle adherence and impact analysis
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
        return ActivityViewTabs.list_create_analytics("principles", active_view)

    # ========================================================================
    # LIST VIEW
    # ========================================================================

    @staticmethod
    def render_list_view(
        principles: list[Any],
        filters: dict[str, Any] | None = None,
        stats: dict[str, int] | None = None,
        categories: list[str] | None = None,
    ) -> Div:
        """
        Render the principle list with strength indicators.

        Args:
            principles: List of principles to display
            filters: Current filter values
            stats: Principle statistics
            categories: Available categories for filtering

        Returns:
            Div containing the list view
        """
        filters = filters or {}
        stats = stats or {}
        categories = categories or [
            "spiritual",
            "ethical",
            "relational",
            "personal",
            "professional",
            "intellectual",
            "health",
            "creative",
        ]

        # Stats bar
        stats_bar = Div(
            Div(
                Span("Total: ", cls="text-gray-500"),
                Span(str(stats.get("total", 0)), cls="font-bold"),
                cls="mr-4",
            ),
            Div(
                Span("Core: ", cls="text-gray-500"),
                Span(str(stats.get("core", 0)), cls="font-bold text-purple-600"),
                cls="mr-4",
            ),
            Div(
                Span("Active: ", cls="text-gray-500"),
                Span(str(stats.get("active", 0)), cls="font-bold text-green-600"),
            ),
            cls="flex items-center mb-4 text-sm",
        )

        # Filter bar
        filter_bar = Div(
            Div(
                Label("Category:", cls="mr-2 text-sm"),
                Select(
                    Option("All", value="all", selected=filters.get("category") == "all"),
                    *[
                        Option(c.title(), value=c, selected=filters.get("category") == c)
                        for c in categories
                    ],
                    name="filter_category",
                    cls="select select-bordered select-sm",
                    **{
                        "hx-get": "/principles/list-fragment",
                        "hx-target": "#principle-list",
                        "hx-include": "[name^='filter_'], [name='sort_by']",
                    },
                ),
                cls="mr-4",
            ),
            Div(
                Label("Strength:", cls="mr-2 text-sm"),
                Select(
                    Option("All", value="all", selected=filters.get("strength") == "all"),
                    Option("Core", value="core", selected=filters.get("strength") == "core"),
                    Option("Strong", value="strong", selected=filters.get("strength") == "strong"),
                    Option(
                        "Developing",
                        value="developing",
                        selected=filters.get("strength") == "developing",
                    ),
                    Option(
                        "Aspirational",
                        value="aspirational",
                        selected=filters.get("strength") == "aspirational",
                    ),
                    name="filter_strength",
                    cls="select select-bordered select-sm",
                    **{
                        "hx-get": "/principles/list-fragment",
                        "hx-target": "#principle-list",
                        "hx-include": "[name^='filter_'], [name='sort_by']",
                    },
                ),
                cls="mr-4",
            ),
            Div(
                Label("Sort:", cls="mr-2 text-sm"),
                Select(
                    Option(
                        "Strength",
                        value="strength",
                        selected=filters.get("sort_by", "strength") == "strength",
                    ),
                    Option("Name", value="title", selected=filters.get("sort_by") == "title"),
                    Option(
                        "Created",
                        value="created_at",
                        selected=filters.get("sort_by") == "created_at",
                    ),
                    name="sort_by",
                    cls="select select-bordered select-sm",
                    **{
                        "hx-get": "/principles/list-fragment",
                        "hx-target": "#principle-list",
                        "hx-include": "[name^='filter_']",
                    },
                ),
            ),
            cls="flex items-center mb-4",
        )

        # Principle list
        principle_items = [
            PrinciplesViewComponents._render_principle_item(principle)
            for principle in principles
        ]

        principle_list = Div(
            *principle_items
            if principle_items
            else [
                P(
                    "No principles found. Create one to get started!",
                    cls="text-gray-500 text-center py-8",
                )
            ],
            id="principle-list",
            cls="space-y-3",
        )

        return Div(
            stats_bar,
            filter_bar,
            principle_list,
            id="list-view",
        )

    @staticmethod
    def _render_principle_item(principle: Any) -> Div:
        """Render a single principle item for the list."""
        from core.models.enums.principle_enums import PrincipleStrength

        uid = getattr(principle, "uid", "")
        # Principle model uses 'name', not 'title'
        title = getattr(principle, "name", getattr(principle, "title", "Untitled"))
        description = getattr(principle, "description", getattr(principle, "statement", ""))
        category = getattr(principle, "category", "personal")
        strength = getattr(principle, "strength", PrincipleStrength.MODERATE)
        is_active = getattr(principle, "is_active", True)

        # Convert strength enum to label and color
        strength_str = (
            strength.value if isinstance(strength, PrincipleStrength) else str(strength).lower()
        )
        strength_labels = {
            "core": ("Core", "badge-primary"),
            "strong": ("Strong", "badge-success"),
            "moderate": ("Moderate", "badge-info"),
            "developing": ("Developing", "badge-warning"),
            "exploring": ("Aspirational", "badge-ghost"),
        }
        strength_label, strength_color = strength_labels.get(
            strength_str, ("Moderate", "badge-info")
        )

        # Category color
        category_str = str(category).lower().replace("principlecategory.", "")
        category_colors = {
            "spiritual": "text-purple-600",
            "ethical": "text-blue-600",
            "relational": "text-pink-600",
            "personal": "text-green-600",
            "professional": "text-orange-600",
            "intellectual": "text-cyan-600",
            "health": "text-red-600",
            "creative": "text-yellow-600",
        }
        category_color = category_colors.get(category_str, "text-gray-600")

        return Div(
            Div(
                # Header row
                Div(
                    H3(title, cls="text-lg font-semibold"),
                    Span(strength_label, cls=f"badge {strength_color} badge-sm ml-2"),
                    Span("Inactive", cls="badge badge-ghost badge-sm ml-2")
                    if not is_active
                    else "",
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
                    Span(f"Category: {category_str.title()}", cls=f"text-xs {category_color} mr-4"),
                    Span(f"Strength: {strength_label}", cls="text-xs text-gray-500"),
                    cls="flex items-center mt-2",
                ),
                # Actions
                Div(
                    Button(
                        "Reflect",
                        cls="btn btn-xs btn-success",
                        **{"hx-get": f"/principles/{uid}/reflect", "hx-target": "#modal"},
                    )
                    if is_active
                    else "",
                    Button(
                        "History",
                        cls="btn btn-xs btn-info",
                        **{
                            "hx-get": f"/principles/{uid}/reflections",
                            "hx-target": "#view-content",
                        },
                    ),
                    Button(
                        "View",
                        cls="btn btn-xs btn-outline",
                        **{"hx-get": f"/principles/{uid}", "hx-target": "body"},
                    ),
                    Button(
                        "Edit",
                        cls="btn btn-xs btn-ghost",
                        **{"hx-get": f"/principles/{uid}/edit", "hx-target": "#modal"},
                    ),
                    cls="flex gap-2 mt-3",
                ),
                cls="p-4",
            ),
            id=f"principle-{uid}",
            cls="card bg-base-100 shadow-sm border border-base-200 hover:shadow-md transition-shadow",
        )

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        categories: list[str] | None = None,
    ) -> Div:
        """
        Render the principle creation form.

        Args:
            categories: List of category names

        Returns:
            Div containing the creation form
        """
        categories = categories or [
            "spiritual",
            "ethical",
            "relational",
            "personal",
            "professional",
            "intellectual",
            "health",
            "creative",
        ]

        # Left column: Core fields
        left_column = Div(
            # Title (required)
            Div(
                Label("Principle Title", cls="label font-semibold"),
                Input(
                    type="text",
                    name="title",
                    placeholder="What principle guides you?",
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
                    "",  # Content argument required for proper HTML rendering
                    name="description",
                    placeholder="Describe this principle and why it matters to you...",
                    rows="4",
                    cls="textarea textarea-bordered w-full",
                    required=True,
                ),
                cls="mb-4",
            ),
            # Statement
            Div(
                Label("Statement", cls="label font-semibold"),
                Input(
                    type="text",
                    name="statement",
                    placeholder="A short, memorable statement (e.g., 'Act with integrity')",
                    cls="input input-bordered w-full",
                ),
                P("A concise statement you can recall easily", cls="text-xs text-gray-500 mt-1"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Right column: Classification
        right_column = Div(
            # Category
            Div(
                Label("Category", cls="label font-semibold"),
                Select(
                    *[Option(c.title(), value=c) for c in categories],
                    name="category",
                    cls="select select-bordered w-full",
                ),
                cls="mb-4",
            ),
            # Initial Strength
            Div(
                Label("Initial Strength", cls="label font-semibold"),
                Select(
                    Option("Aspirational (just starting)", value="0.2"),
                    Option("Developing (working on it)", value="0.5", selected=True),
                    Option("Strong (well-established)", value="0.75"),
                    Option("Core (fundamental to who I am)", value="0.95"),
                    name="strength",
                    cls="select select-bordered w-full",
                ),
                P(
                    "How established is this principle in your life?",
                    cls="text-xs text-gray-500 mt-1",
                ),
                cls="mb-4",
            ),
            # Active toggle
            Div(
                Label(
                    Input(
                        type="checkbox",
                        name="is_active",
                        value="true",
                        checked=True,
                        cls="checkbox checkbox-primary mr-2",
                    ),
                    "Active Principle",
                    cls="label cursor-pointer justify-start",
                ),
                P("Active principles guide your daily decisions", cls="text-xs text-gray-500 mt-1"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        # Submit buttons
        submit_section = Div(
            A(
                "Cancel",
                href="/principles",
                cls="btn btn-ghost btn-lg",
            ),
            Button(
                "Create Principle",
                type="submit",
                cls="btn btn-primary btn-lg",
            ),
            Button(
                "Create & Add Another",
                type="submit",
                name="add_another",
                value="true",
                cls="btn btn-outline btn-lg",
            ),
            cls="flex justify-end gap-2 pt-6 border-t border-base-200",
        )

        return Div(
            H2("Create New Principle", cls="text-2xl font-bold mb-6"),
            Form(
                Div(
                    left_column,
                    right_column,
                    cls="flex flex-col lg:flex-row gap-8",
                ),
                submit_section,
                **{
                    "hx-post": "/principles/quick-add",
                    "hx-target": "#view-content",
                    "hx-swap": "innerHTML",
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
        Render the principle analytics view.

        Args:
            analytics_data: Analytics data including adherence rates, impact

        Returns:
            Div containing the analytics view
        """
        analytics_data = analytics_data or {}

        # Adherence metrics
        adherence_section = Div(
            H3("Principle Adherence", cls="text-lg font-semibold mb-4"),
            Div(
                # Overall adherence
                Div(
                    P("Overall Adherence", cls="text-sm text-gray-500"),
                    P(
                        f"{analytics_data.get('overall_adherence', 0):.0%}",
                        cls="text-3xl font-bold text-green-600",
                    ),
                    cls="text-center p-4 bg-base-200 rounded-lg",
                ),
                # Core principles
                Div(
                    P("Core Principles", cls="text-sm text-gray-500"),
                    P(
                        str(analytics_data.get("core_count", 0)),
                        cls="text-3xl font-bold text-purple-600",
                    ),
                    cls="text-center p-4 bg-base-200 rounded-lg",
                ),
                # Active principles
                Div(
                    P("Active Principles", cls="text-sm text-gray-500"),
                    P(
                        str(analytics_data.get("active_count", 0)),
                        cls="text-3xl font-bold text-blue-600",
                    ),
                    cls="text-center p-4 bg-base-200 rounded-lg",
                ),
                cls="grid grid-cols-3 gap-4 mb-6",
            ),
            cls="card bg-base-100 shadow-lg p-6 mb-6",
        )

        # Impact analysis
        impact_section = Div(
            H3("Principle Impact", cls="text-lg font-semibold mb-4"),
            Div(
                P(
                    "Track how your principles influence your goals and choices.",
                    cls="text-gray-500 mb-4",
                ),
                # Placeholder for charts
                Div(
                    P(
                        "Impact charts will be displayed here",
                        cls="text-gray-400 text-center py-12 border border-dashed border-gray-300 rounded-lg",
                    ),
                    cls="mb-4",
                ),
            ),
            cls="card bg-base-100 shadow-lg p-6 mb-6",
        )

        # Reflection history
        reflections = analytics_data.get("reflections", [])
        if reflections:
            reflection_content = Div(
                P("Your recent principle reflections:", cls="text-gray-500 mb-4"),
                Div(
                    *[PrinciplesViewComponents._render_reflection_card(r) for r in reflections[:5]],
                    cls="space-y-3",
                ),
            )
        else:
            reflection_content = Div(
                P("Track your principle reflections and growth.", cls="text-gray-500 mb-4"),
                P("No reflections recorded yet.", cls="text-gray-400 text-center py-8"),
            )

        reflection_section = Div(
            H3("Recent Reflections", cls="text-lg font-semibold mb-4"),
            reflection_content,
            cls="card bg-base-100 shadow-lg p-6",
        )

        return Div(
            adherence_section,
            impact_section,
            reflection_section,
            id="analytics-view",
        )

    # ========================================================================
    # EDIT FORM
    # ========================================================================

    @staticmethod
    def render_edit_form(
        principle: Any,
        categories: list[str] | None = None,
    ) -> Div:
        """
        Render edit form for a principle (modal content).

        Args:
            principle: Principle to edit
            categories: List of category names

        Returns:
            Div containing the edit form
        """

        categories = categories or [
            "spiritual",
            "ethical",
            "relational",
            "personal",
            "professional",
            "intellectual",
            "health",
            "creative",
        ]

        uid = getattr(principle, "uid", "")
        name = getattr(principle, "name", "")
        statement = getattr(principle, "statement", "")
        description = getattr(principle, "description", "")
        category = getattr(principle, "category", "personal")
        is_active = getattr(principle, "is_active", True)

        category_str = str(category).lower().replace("principlecategory.", "")

        return Div(
            Div(
                H2("Edit Principle", cls="text-xl font-bold mb-4"),
                Form(
                    # Name
                    Div(
                        Label("Name", cls="label font-semibold"),
                        Input(
                            type="text",
                            name="name",
                            value=name,
                            cls="input input-bordered w-full",
                            required=True,
                        ),
                        cls="mb-4",
                    ),
                    # Statement
                    Div(
                        Label("Statement", cls="label font-semibold"),
                        Input(
                            type="text",
                            name="statement",
                            value=statement,
                            placeholder="A short, memorable statement",
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Description
                    Div(
                        Label("Description", cls="label font-semibold"),
                        Textarea(
                            description or "",
                            name="description",
                            rows="3",
                            cls="textarea textarea-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Category
                    Div(
                        Label("Category", cls="label font-semibold"),
                        Select(
                            *[
                                Option(c.title(), value=c, selected=(c == category_str))
                                for c in categories
                            ],
                            name="category",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Active
                    Div(
                        Label(
                            Input(
                                type="checkbox",
                                name="is_active",
                                value="true",
                                checked=is_active,
                                cls="checkbox checkbox-primary mr-2",
                            ),
                            "Active",
                            cls="label cursor-pointer justify-start",
                        ),
                        cls="mb-4",
                    ),
                    # Buttons
                    Div(
                        Button("Save", type="submit", cls="btn btn-primary"),
                        Button(
                            "Cancel",
                            type="button",
                            cls="btn btn-ghost ml-2",
                            **{"onclick": "document.getElementById('modal').innerHTML = ''"},
                        ),
                        cls="flex justify-end",
                    ),
                    **{
                        "hx-post": f"/principles/{uid}/save",
                        "hx-target": "#view-content",
                        "hx-swap": "innerHTML",
                        "hx-on::after-request": "document.getElementById('modal').innerHTML = ''",
                    },
                ),
                cls="card bg-base-100 shadow-xl p-6 max-w-lg mx-auto mt-20",
            ),
            cls="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50",
            id="edit-modal",
        )

    # ========================================================================
    # REFLECT FORM
    # ========================================================================

    @staticmethod
    def render_reflect_form(principle: Any) -> Div:
        """
        Render reflection form for a principle (modal content).

        Args:
            principle: Principle to reflect on

        Returns:
            Div containing the reflection form
        """
        uid = getattr(principle, "uid", "")
        name = getattr(principle, "name", "Untitled")

        return Div(
            Div(
                H2(f"Reflect on: {name}", cls="text-xl font-bold mb-4"),
                P("How well did you align with this principle today?", cls="text-gray-600 mb-4"),
                Form(
                    # Alignment level
                    Div(
                        Label("Alignment Level", cls="label font-semibold"),
                        Select(
                            Option("Aligned - Fully lived this principle", value="aligned"),
                            Option("Mostly Aligned - Minor deviations", value="mostly_aligned"),
                            Option("Partial - Some alignment, room for growth", value="partial"),
                            Option(
                                "Misaligned - Actions contradicted principle", value="misaligned"
                            ),
                            Option("Unknown - Unsure how to assess", value="unknown"),
                            name="alignment_level",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Evidence (what was observed - required)
                    Div(
                        Label("Evidence *", cls="label font-semibold"),
                        Textarea(
                            "",
                            name="evidence",
                            placeholder="What specifically did you observe? What actions did you take? (Required - at least 5 characters)",
                            rows="3",
                            cls="textarea textarea-bordered w-full",
                            required=True,
                            minlength="5",
                        ),
                        P(
                            "Describe what happened that relates to this principle.",
                            cls="text-xs text-gray-500 mt-1",
                        ),
                        cls="mb-4",
                    ),
                    # Reflection notes (optional insights)
                    Div(
                        Label("Additional Notes", cls="label font-semibold"),
                        Textarea(
                            "",
                            name="reflection",
                            placeholder="What did you learn? Any insights? (Optional)",
                            rows="3",
                            cls="textarea textarea-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    # Trigger section (collapsible)
                    Div(
                        Div(
                            Span(
                                "What triggered this reflection?", cls="font-semibold text-gray-700"
                            ),
                            Span("(Optional)", cls="text-xs text-gray-400 ml-2"),
                            cls="mb-2",
                        ),
                        # Trigger type selector
                        Div(
                            Label("Trigger Type", cls="label text-sm"),
                            Select(
                                Option("Manual reflection", value="manual"),
                                Option("Goal-related", value="goal"),
                                Option("Habit check-in", value="habit"),
                                Option("Event occurred", value="event"),
                                Option("Choice/Decision", value="choice"),
                                name="trigger_type",
                                cls="select select-bordered select-sm w-full",
                                id="trigger-type-select",
                                **{
                                    "x-data": "{ showTriggerUid: false }",
                                    "x-on:change": "showTriggerUid = $event.target.value !== 'manual'",
                                },
                            ),
                            cls="mb-2",
                        ),
                        # Trigger UID input (hidden by default, shown when type is not manual)
                        Div(
                            Label("Related Entity UID", cls="label text-sm"),
                            Input(
                                type="text",
                                name="trigger_uid",
                                placeholder="e.g., goal.fitness, habit.meditation",
                                cls="input input-bordered input-sm w-full",
                            ),
                            P(
                                "UID of the goal, habit, event, or choice that prompted this reflection",
                                cls="text-xs text-gray-400 mt-1",
                            ),
                            cls="mb-2",
                            id="trigger-uid-container",
                        ),
                        # Trigger context (situation description)
                        Div(
                            Label("Situation Context", cls="label text-sm"),
                            Textarea(
                                "",
                                name="trigger_context",
                                placeholder="Describe the situation that prompted this reflection...",
                                rows="2",
                                cls="textarea textarea-bordered textarea-sm w-full",
                            ),
                            cls="mb-2",
                        ),
                        cls="bg-base-200 rounded-lg p-3 mb-4",
                    ),
                    # Buttons
                    Div(
                        Button("Save Reflection", type="submit", cls="btn btn-success"),
                        Button(
                            "Cancel",
                            type="button",
                            cls="btn btn-ghost ml-2",
                            **{"onclick": "document.getElementById('modal').innerHTML = ''"},
                        ),
                        cls="flex justify-end",
                    ),
                    **{
                        "hx-post": f"/principles/{uid}/reflect/save",
                        "hx-target": "#view-content",
                        "hx-swap": "innerHTML",
                        "hx-on::after-request": "document.getElementById('modal').innerHTML = ''",
                    },
                ),
                cls="card bg-base-100 shadow-xl p-6 max-w-lg mx-auto mt-20",
            ),
            cls="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50 overflow-y-auto",
            id="reflect-modal",
        )

    # ========================================================================
    # REFLECTION HISTORY
    # ========================================================================

    @staticmethod
    def render_reflection_history(
        principle: Any,
        reflections: list[Any],
    ) -> Div:
        """
        Render reflection history for a principle.

        Args:
            principle: The principle entity
            reflections: List of PrincipleReflection entities

        Returns:
            Div containing reflection history
        """
        uid = getattr(principle, "uid", "")
        name = getattr(principle, "name", "Untitled")

        # Header with back button
        header = Div(
            Button(
                "← Back to List",
                cls="btn btn-ghost btn-sm",
                **{
                    "hx-get": "/principles/view/list",
                    "hx-target": "#view-content",
                },
            ),
            H2(f"Reflection History: {name}", cls="text-xl font-bold mt-4 mb-4"),
            cls="mb-4",
        )

        # Alignment trend link
        trend_link = Div(
            Button(
                "View Alignment Trend",
                cls="btn btn-outline btn-sm",
                **{
                    "hx-get": f"/principles/{uid}/alignment-trend",
                    "hx-target": "#view-content",
                },
            ),
            cls="mb-4",
        )

        # Reflection cards
        if reflections:
            reflection_cards = [
                PrinciplesViewComponents._render_reflection_card(reflection)
                for reflection in reflections
            ]
        else:
            reflection_cards = [
                P(
                    "No reflections yet. Click 'Reflect' on the principle to record your first reflection.",
                    cls="text-gray-500 text-center py-8",
                )
            ]

        return Div(
            header,
            trend_link,
            Div(*reflection_cards, cls="space-y-4"),
            id="reflection-history-view",
        )

    @staticmethod
    def _render_reflection_card(reflection: Any) -> Div:
        """Render a single reflection card."""
        from core.models.enums.principle_enums import AlignmentLevel

        alignment = getattr(reflection, "alignment_level", AlignmentLevel.PARTIAL)
        evidence = getattr(reflection, "evidence", "")
        notes = getattr(reflection, "reflection_notes", "")
        quality = getattr(reflection, "reflection_quality_score", 0.0)
        reflection_date = getattr(reflection, "reflection_date", "")
        trigger_type = getattr(reflection, "trigger_type", "manual")

        # Alignment level styling
        alignment_colors = {
            AlignmentLevel.ALIGNED: ("bg-green-100 text-green-800", "Fully Aligned"),
            AlignmentLevel.MOSTLY_ALIGNED: ("bg-blue-100 text-blue-800", "Mostly Aligned"),
            AlignmentLevel.PARTIAL: ("bg-yellow-100 text-yellow-800", "Partial"),
            AlignmentLevel.MISALIGNED: ("bg-red-100 text-red-800", "Misaligned"),
            AlignmentLevel.UNKNOWN: ("bg-gray-100 text-gray-800", "Unknown"),
        }
        color_cls, alignment_text = alignment_colors.get(
            alignment, ("bg-gray-100 text-gray-800", "Unknown")
        )

        # Quality badge
        quality_label = "deep" if quality >= 0.7 else "moderate" if quality >= 0.4 else "shallow"
        quality_colors = {
            "deep": "badge-success",
            "moderate": "badge-warning",
            "shallow": "badge-ghost",
        }

        return Div(
            Div(
                # Date and alignment
                Div(
                    Span(str(reflection_date), cls="text-sm text-gray-500"),
                    Span(alignment_text, cls=f"badge {color_cls} ml-2"),
                    Span(
                        quality_label,
                        cls=f"badge {quality_colors.get(quality_label, 'badge-ghost')} ml-2",
                    ),
                    cls="flex items-center gap-2 mb-2",
                ),
                # Evidence
                P(evidence, cls="text-gray-700 mb-2") if evidence else None,
                # Notes (if present)
                P(notes, cls="text-gray-600 text-sm italic") if notes else None,
                # Trigger info
                Span(
                    f"Triggered by: {trigger_type}",
                    cls="text-xs text-gray-400 mt-2 block",
                )
                if trigger_type != "manual"
                else None,
                cls="p-4",
            ),
            cls="card bg-base-100 shadow border border-gray-200",
        )

    # ========================================================================
    # ALIGNMENT TREND
    # ========================================================================

    @staticmethod
    def render_alignment_trend(trend: Any) -> Div:
        """
        Render alignment trend visualization for a principle.

        Args:
            trend: AlignmentTrend data object

        Returns:
            Div containing trend visualization
        """
        principle_uid = getattr(trend, "principle_uid", "")
        period_start = getattr(trend, "period_start", "")
        period_end = getattr(trend, "period_end", "")
        reflection_count = getattr(trend, "reflection_count", 0)
        avg_alignment = getattr(trend, "average_alignment", 0.0)
        trend_direction = getattr(trend, "trend_direction", "stable")
        quality_avg = getattr(trend, "quality_average", 0.0)
        trigger_dist = getattr(trend, "trigger_distribution", {})

        # Trend direction styling
        trend_styles = {
            "improving": ("text-green-600", "↑ Improving"),
            "declining": ("text-red-600", "↓ Declining"),
            "stable": ("text-gray-600", "→ Stable"),
        }
        trend_cls, trend_text = trend_styles.get(trend_direction, ("text-gray-600", "→ Stable"))

        # Header with back button
        header = Div(
            Button(
                "← Back to Reflections",
                cls="btn btn-ghost btn-sm",
                **{
                    "hx-get": f"/principles/{principle_uid}/reflections",
                    "hx-target": "#view-content",
                },
            ),
            H2("Alignment Trend", cls="text-xl font-bold mt-4 mb-4"),
            P(f"Period: {period_start} to {period_end}", cls="text-gray-500 mb-4"),
            cls="mb-4",
        )

        # Stats cards
        stats_row = Div(
            # Reflection count
            Div(
                Span("Reflections", cls="text-sm text-gray-500 block"),
                Span(str(reflection_count), cls="text-2xl font-bold"),
                cls="card bg-base-100 shadow p-4 text-center",
            ),
            # Average alignment
            Div(
                Span("Avg Alignment", cls="text-sm text-gray-500 block"),
                Span(f"{avg_alignment:.1f}/4", cls="text-2xl font-bold"),
                cls="card bg-base-100 shadow p-4 text-center",
            ),
            # Trend direction
            Div(
                Span("Trend", cls="text-sm text-gray-500 block"),
                Span(trend_text, cls=f"text-2xl font-bold {trend_cls}"),
                cls="card bg-base-100 shadow p-4 text-center",
            ),
            # Quality average
            Div(
                Span("Quality", cls="text-sm text-gray-500 block"),
                Span(f"{quality_avg:.0%}", cls="text-2xl font-bold"),
                cls="card bg-base-100 shadow p-4 text-center",
            ),
            cls="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6",
        )

        # Trigger distribution
        trigger_items = []
        for trigger_type, count in trigger_dist.items():
            trigger_items.append(
                Div(
                    Span(trigger_type.title(), cls="text-gray-600"),
                    Span(str(count), cls="font-bold ml-auto"),
                    cls="flex justify-between py-2 border-b",
                )
            )

        trigger_section = (
            Div(
                H3("Reflection Triggers", cls="text-lg font-semibold mb-3"),
                *trigger_items if trigger_items else [P("No trigger data", cls="text-gray-500")],
                cls="card bg-base-100 shadow p-4",
            )
            if trigger_dist
            else None
        )

        return Div(
            header,
            stats_row,
            trigger_section,
            id="alignment-trend-view",
        )


__all__ = ["PrinciplesViewComponents"]
