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

from fasthtml.common import H2, H3, Div, Option, P, Span

from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.feedback import Badge, BadgeT
from ui.forms import Input, Label, Select, Textarea
from ui.layout import Size
from ui.patterns.activity_views_base import (
    ActivityCreateForm,
    ActivityListFilters,
    ActivityViewTabs,
)
from ui.patterns.entity_card import EntityCard
from ui.patterns.stats_grid import StatsGrid


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
        """Render the main view tabs (List, Create, Analytics)."""
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
        """Render the principle list with strength indicators."""
        filters = filters or {}
        stats = stats or {}
        categories = categories or [
            "spiritual", "ethical", "relational", "personal",
            "professional", "intellectual", "health", "creative",
        ]

        stats_bar = StatsGrid(
            [
                {"label": "Total", "value": stats.get("total", 0)},
                {"label": "Core", "value": stats.get("core", 0)},
                {"label": "Active", "value": stats.get("active", 0), "trend": "up" if stats.get("active", 0) > 0 else "neutral"},
            ],
            cols=3,
        )

        # Principles has 3 filter dropdowns: category, strength, sort
        strength_filter = Div(
            Label("Strength:", cls="mr-2 text-sm"),
            Select(
                Option("All", value="all", selected=filters.get("strength") == "all"),
                Option("Core", value="core", selected=filters.get("strength") == "core"),
                Option("Strong", value="strong", selected=filters.get("strength") == "strong"),
                Option("Developing", value="developing", selected=filters.get("strength") == "developing"),
                Option("Aspirational", value="aspirational", selected=filters.get("strength") == "aspirational"),
                name="filter_strength",
                size=Size.sm,
                full_width=False,
                **{
                    "hx-get": "/principles/list-fragment",
                    "hx-target": "#principle-list",
                    "hx-include": "[name^='filter_'], [name='sort_by']",
                },
            ),
            cls="mr-4",
        )

        filter_bar = ActivityListFilters.render(
            domain="principles",
            status_options=[("all", "All")] + [(c, c.title()) for c in categories],
            sort_options=[("strength", "Strength"), ("title", "Name"), ("created_at", "Created")],
            current_status=filters.get("category", "all"),
            current_sort=filters.get("sort_by", "strength"),
            list_target="#principle-list",
            filter_name="filter_category",
            filter_label="Category",
            extra_filters=[strength_filter],
        )

        principle_items = [
            PrinciplesViewComponents._render_principle_item(principle) for principle in principles
        ]

        principle_list = Div(
            *principle_items
            if principle_items
            else [
                P(
                    "No principles found. Create one to get started!",
                    cls="text-muted-foreground text-center py-8",
                )
            ],
            id="principle-list",
            cls="space-y-3",
        )

        return Div(stats_bar, filter_bar, principle_list, id="list-view")

    @staticmethod
    def _render_principle_item(principle: Any) -> Div:
        """Render a single principle item for the list."""
        from core.models.enums.principle_enums import PrincipleStrength

        uid = getattr(principle, "uid", "")
        title = getattr(principle, "name", getattr(principle, "title", "Untitled"))
        description = getattr(principle, "description", getattr(principle, "statement", ""))
        category = getattr(principle, "category", "personal")
        strength = getattr(principle, "strength", PrincipleStrength.MODERATE)
        is_active = getattr(principle, "is_active", True)

        strength_str = (
            strength.value if isinstance(strength, PrincipleStrength) else str(strength).lower()
        )
        strength_labels = {
            "core": ("Core", BadgeT.primary),
            "strong": ("Strong", BadgeT.success),
            "moderate": ("Moderate", BadgeT.info),
            "developing": ("Developing", BadgeT.warning),
            "exploring": ("Aspirational", BadgeT.ghost),
        }
        strength_label, strength_variant = strength_labels.get(
            strength_str, ("Moderate", BadgeT.info)
        )

        from core.utils.type_converters import normalize_enum_str

        category_str = normalize_enum_str(category, "personal")
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
        category_color = category_colors.get(category_str, "text-muted-foreground")

        metadata: list[Any] = [
            Badge(strength_label, variant=strength_variant),
            Badge("Inactive", variant=BadgeT.ghost) if not is_active else "",
            Span(f"Category: {category_str.title()}", cls=f"text-xs {category_color}"),
        ]
        # Filter out empty strings
        metadata = [m for m in metadata if m]

        action_buttons: list[Any] = []
        if is_active:
            action_buttons.append(
                Button("Reflect", variant=ButtonT.success, size=Size.xs, **{"hx-get": f"/principles/{uid}/reflect", "hx-target": "#modal"})
            )
        action_buttons.extend([
            Button("History", variant=ButtonT.info, size=Size.xs, **{"hx-get": f"/principles/{uid}/reflections", "hx-target": "#view-content"}),
            Button("View", variant=ButtonT.outline, size=Size.xs, **{"hx-get": f"/principles/{uid}", "hx-target": "body"}),
            Button("Edit", variant=ButtonT.ghost, size=Size.xs, **{"hx-get": f"/principles/{uid}/edit", "hx-target": "#modal"}),
        ])
        actions = Div(*action_buttons, cls="flex gap-2")

        return EntityCard(
            title=title,
            description=description or "",
            metadata=metadata,
            actions=actions,
            id=f"principle-{uid}",
        )

    # ========================================================================
    # CREATE VIEW
    # ========================================================================

    @staticmethod
    def render_create_view(
        categories: list[str] | None = None,
    ) -> Div:
        """Render the principle creation form."""
        categories = categories or [
            "spiritual", "ethical", "relational", "personal",
            "professional", "intellectual", "health", "creative",
        ]

        left_column = Div(
            Div(
                Label("Principle Title", cls="label font-semibold"),
                Input(type="text", name="title", placeholder="What principle guides you?", required=True, autofocus=True),
                cls="mb-4",
            ),
            Div(
                Label("Description", cls="label font-semibold"),
                Textarea(
                    "",
                    name="description", placeholder="Describe this principle and why it matters to you...", rows="4", required=True,
                ),
                cls="mb-4",
            ),
            Div(
                Label("Statement", cls="label font-semibold"),
                Input(type="text", name="statement", placeholder="A short, memorable statement (e.g., 'Act with integrity')"),
                P("A concise statement you can recall easily", cls="text-xs text-muted-foreground mt-1"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        right_column = Div(
            Div(
                Label("Category", cls="label font-semibold"),
                Select(*[Option(c.title(), value=c) for c in categories], name="category"),
                cls="mb-4",
            ),
            Div(
                Label("Initial Strength", cls="label font-semibold"),
                Select(
                    Option("Aspirational (just starting)", value="0.2"),
                    Option("Developing (working on it)", value="0.5", selected=True),
                    Option("Strong (well-established)", value="0.75"),
                    Option("Core (fundamental to who I am)", value="0.95"),
                    name="strength",
                ),
                P("How established is this principle in your life?", cls="text-xs text-muted-foreground mt-1"),
                cls="mb-4",
            ),
            Div(
                Label(
                    Input(type="checkbox", name="is_active", value="true", checked=True, cls="uk-checkbox cursor-pointer mr-2"),
                    "Active Principle",
                    cls="label cursor-pointer justify-start",
                ),
                P("Active principles guide your daily decisions", cls="text-xs text-muted-foreground mt-1"),
                cls="mb-4",
            ),
            cls="flex-1",
        )

        return ActivityCreateForm("principles", "Principle", left_column, right_column)

    # ========================================================================
    # ANALYTICS VIEW
    # ========================================================================

    @staticmethod
    def render_analytics_view(
        analytics_data: dict[str, Any] | None = None,
    ) -> Div:
        """Render the principle analytics view."""
        analytics_data = analytics_data or {}

        adherence_section = Card(
            H3("Principle Adherence", cls="text-lg font-semibold mb-4"),
            Div(
                Div(
                    P("Overall Adherence", cls="text-sm text-muted-foreground"),
                    P(f"{analytics_data.get('overall_adherence', 0):.0%}", cls="text-3xl font-bold text-green-600"),
                    cls="text-center p-4 bg-muted rounded-lg",
                ),
                Div(
                    P("Core Principles", cls="text-sm text-muted-foreground"),
                    P(str(analytics_data.get("core_count", 0)), cls="text-3xl font-bold text-purple-600"),
                    cls="text-center p-4 bg-muted rounded-lg",
                ),
                Div(
                    P("Active Principles", cls="text-sm text-muted-foreground"),
                    P(str(analytics_data.get("active_count", 0)), cls="text-3xl font-bold text-blue-600"),
                    cls="text-center p-4 bg-muted rounded-lg",
                ),
                cls="grid grid-cols-3 gap-4 mb-6",
            ),
            cls="bg-background shadow-lg p-6 mb-6",
        )

        impact_section = Card(
            H3("Principle Impact", cls="text-lg font-semibold mb-4"),
            Div(
                P("Track how your principles influence your goals and choices.", cls="text-muted-foreground mb-4"),
                Div(
                    P("Impact charts will be displayed here", cls="text-muted-foreground text-center py-12 border border-dashed border-border rounded-lg"),
                    cls="mb-4",
                ),
            ),
            cls="bg-background shadow-lg p-6 mb-6",
        )

        reflections = analytics_data.get("reflections", [])
        if reflections:
            reflection_content = Div(
                P("Your recent principle reflections:", cls="text-muted-foreground mb-4"),
                Div(
                    *[PrinciplesViewComponents._render_reflection_card(r) for r in reflections[:5]],
                    cls="space-y-3",
                ),
            )
        else:
            reflection_content = Div(
                P("Track your principle reflections and growth.", cls="text-muted-foreground mb-4"),
                P("No reflections recorded yet.", cls="text-muted-foreground text-center py-8"),
            )

        reflection_section = Card(
            H3("Recent Reflections", cls="text-lg font-semibold mb-4"),
            reflection_content,
            cls="bg-background shadow-lg p-6",
        )

        return Div(adherence_section, impact_section, reflection_section, id="analytics-view")

    # ========================================================================
    # EDIT FORM
    # ========================================================================

    @staticmethod
    def render_edit_form(
        principle: Any,
        categories: list[str] | None = None,
    ) -> Div:
        """Render edit form for a principle (modal content)."""
        categories = categories or [
            "spiritual", "ethical", "relational", "personal",
            "professional", "intellectual", "health", "creative",
        ]

        uid = getattr(principle, "uid", "")
        name = getattr(principle, "name", "")
        statement = getattr(principle, "statement", "")
        description = getattr(principle, "description", "")
        category = getattr(principle, "category", "personal")
        is_active = getattr(principle, "is_active", True)

        from fasthtml.common import Form

        from core.utils.type_converters import normalize_enum_str

        category_str = normalize_enum_str(category, "personal")

        return Div(
            Card(
                H2("Edit Principle", cls="text-xl font-bold mb-4"),
                Form(
                    Div(
                        Label("Name", cls="label font-semibold"),
                        Input(type="text", name="name", value=name, required=True),
                        cls="mb-4",
                    ),
                    Div(
                        Label("Statement", cls="label font-semibold"),
                        Input(type="text", name="statement", value=statement, placeholder="A short, memorable statement"),
                        cls="mb-4",
                    ),
                    Div(
                        Label("Description", cls="label font-semibold"),
                        Textarea(description or "", name="description", rows="3"),
                        cls="mb-4",
                    ),
                    Div(
                        Label("Category", cls="label font-semibold"),
                        Select(
                            *[Option(c.title(), value=c, selected=(c == category_str)) for c in categories],
                            name="category",
                        ),
                        cls="mb-4",
                    ),
                    Div(
                        Label(
                            Input(type="checkbox", name="is_active", value="true", checked=is_active, cls="uk-checkbox cursor-pointer mr-2"),
                            "Active",
                            cls="label cursor-pointer justify-start",
                        ),
                        cls="mb-4",
                    ),
                    Div(
                        Button("Save", type="submit", variant=ButtonT.primary),
                        Button(
                            "Cancel", type="button", variant=ButtonT.ghost, cls="ml-2",
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
                cls="bg-background shadow-xl p-6 max-w-lg mx-auto mt-20",
            ),
            cls="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center z-50",
            id="edit-modal",
        )

    # ========================================================================
    # REFLECT FORM
    # ========================================================================

    @staticmethod
    def render_reflect_form(principle: Any) -> Div:
        """Render reflection form for a principle (modal content)."""
        from fasthtml.common import Form

        uid = getattr(principle, "uid", "")
        name = getattr(principle, "name", "Untitled")

        return Div(
            Card(
                H2(f"Reflect on: {name}", cls="text-xl font-bold mb-4"),
                P("How well did you align with this principle today?", cls="text-muted-foreground mb-4"),
                Form(
                    Div(
                        Label("Alignment Level", cls="label font-semibold"),
                        Select(
                            Option("Aligned - Fully lived this principle", value="aligned"),
                            Option("Mostly Aligned - Minor deviations", value="mostly_aligned"),
                            Option("Partial - Some alignment, room for growth", value="partial"),
                            Option("Misaligned - Actions contradicted principle", value="misaligned"),
                            Option("Unknown - Unsure how to assess", value="unknown"),
                            name="alignment_level",
                        ),
                        cls="mb-4",
                    ),
                    Div(
                        Label("Evidence *", cls="label font-semibold"),
                        Textarea(
                            "", name="evidence",
                            placeholder="What specifically did you observe? What actions did you take? (Required - at least 5 characters)",
                            rows="3", required=True, minlength="5",
                        ),
                        P("Describe what happened that relates to this principle.", cls="text-xs text-muted-foreground mt-1"),
                        cls="mb-4",
                    ),
                    Div(
                        Label("Additional Notes", cls="label font-semibold"),
                        Textarea(
                            "", name="reflection",
                            placeholder="What did you learn? Any insights? (Optional)", rows="3",
                        ),
                        cls="mb-4",
                    ),
                    Div(
                        Div(
                            Span("What triggered this reflection?", cls="font-semibold text-muted-foreground"),
                            Span("(Optional)", cls="text-xs text-muted-foreground ml-2"),
                            cls="mb-2",
                        ),
                        Div(
                            Label("Trigger Type", cls="label text-sm"),
                            Select(
                                Option("Manual reflection", value="manual"),
                                Option("Goal-related", value="goal"),
                                Option("Habit check-in", value="habit"),
                                Option("Event occurred", value="event"),
                                Option("Choice/Decision", value="choice"),
                                name="trigger_type", size=Size.sm, id="trigger-type-select",
                                **{
                                    "x-data": "{ showTriggerUid: false }",
                                    "x-on:change": "showTriggerUid = $event.target.value !== 'manual'",
                                },
                            ),
                            cls="mb-2",
                        ),
                        Div(
                            Label("Related Entity UID", cls="label text-sm"),
                            Input(type="text", name="trigger_uid", placeholder="e.g., goal.fitness, habit.meditation", size=Size.sm),
                            P("UID of the goal, habit, event, or choice that prompted this reflection", cls="text-xs text-muted-foreground mt-1"),
                            cls="mb-2", id="trigger-uid-container",
                        ),
                        Div(
                            Label("Situation Context", cls="label text-sm"),
                            Textarea(
                                "", name="trigger_context",
                                placeholder="Describe the situation that prompted this reflection...",
                                rows="2", size=Size.sm,
                            ),
                            cls="mb-2",
                        ),
                        cls="bg-muted rounded-lg p-3 mb-4",
                    ),
                    Div(
                        Button("Save Reflection", type="submit", variant=ButtonT.success),
                        Button(
                            "Cancel", type="button", variant=ButtonT.ghost, cls="ml-2",
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
                cls="bg-background shadow-xl p-6 max-w-lg mx-auto mt-20",
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
        """Render reflection history for a principle."""
        uid = getattr(principle, "uid", "")
        name = getattr(principle, "name", "Untitled")

        header = Div(
            Button(
                "← Back to List", variant=ButtonT.ghost, size=Size.sm,
                **{"hx-get": "/principles/view/list", "hx-target": "#view-content"},
            ),
            H2(f"Reflection History: {name}", cls="text-xl font-bold mt-4 mb-4"),
            cls="mb-4",
        )

        trend_link = Div(
            Button(
                "View Alignment Trend", variant=ButtonT.outline, size=Size.sm,
                **{"hx-get": f"/principles/{uid}/alignment-trend", "hx-target": "#view-content"},
            ),
            cls="mb-4",
        )

        if reflections:
            reflection_cards = [
                PrinciplesViewComponents._render_reflection_card(reflection)
                for reflection in reflections
            ]
        else:
            reflection_cards = [
                P(
                    "No reflections yet. Click 'Reflect' on the principle to record your first reflection.",
                    cls="text-muted-foreground text-center py-8",
                )
            ]

        return Div(header, trend_link, Div(*reflection_cards, cls="space-y-4"), id="reflection-history-view")

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

        alignment_variants = {
            AlignmentLevel.ALIGNED: (BadgeT.success, "Fully Aligned"),
            AlignmentLevel.MOSTLY_ALIGNED: (BadgeT.info, "Mostly Aligned"),
            AlignmentLevel.PARTIAL: (BadgeT.warning, "Partial"),
            AlignmentLevel.MISALIGNED: (BadgeT.error, "Misaligned"),
            AlignmentLevel.UNKNOWN: (BadgeT.ghost, "Unknown"),
        }
        alignment_variant, alignment_text = alignment_variants.get(
            alignment, (BadgeT.ghost, "Unknown")
        )

        quality_label = "deep" if quality >= 0.7 else "moderate" if quality >= 0.4 else "shallow"
        quality_badge_map = {
            "deep": "bg-green-100 text-green-800 border-green-200",
            "moderate": "bg-yellow-100 text-yellow-800 border-yellow-200",
            "shallow": "bg-gray-100 text-gray-600 border-gray-200",
        }

        return Card(
            Div(
                Div(
                    Span(str(reflection_date), cls="text-sm text-muted-foreground"),
                    Badge(alignment_text, variant=alignment_variant, cls="ml-2"),
                    Badge(
                        quality_label, variant=None,
                        cls=f"{quality_badge_map.get(quality_label, 'bg-gray-100 text-gray-600 border-gray-200')} ml-2",
                    ),
                    cls="flex items-center gap-2 mb-2",
                ),
                P(evidence, cls="text-muted-foreground mb-2") if evidence else None,
                P(notes, cls="text-muted-foreground text-sm italic") if notes else None,
                Span(
                    f"Triggered by: {trigger_type}",
                    cls="text-xs text-muted-foreground mt-2 block",
                )
                if trigger_type != "manual"
                else None,
                cls="p-4",
            ),
            cls="bg-background shadow border border-border",
        )

    # ========================================================================
    # ALIGNMENT TREND
    # ========================================================================

    @staticmethod
    def render_alignment_trend(trend: Any) -> Div:
        """Render alignment trend visualization for a principle."""
        principle_uid = getattr(trend, "principle_uid", "")
        period_start = getattr(trend, "period_start", "")
        period_end = getattr(trend, "period_end", "")
        reflection_count = getattr(trend, "reflection_count", 0)
        avg_alignment = getattr(trend, "average_alignment", 0.0)
        trend_direction = getattr(trend, "trend_direction", "stable")
        quality_avg = getattr(trend, "quality_average", 0.0)
        trigger_dist = getattr(trend, "trigger_distribution", {})

        trend_styles = {
            "improving": ("text-green-600", "↑ Improving"),
            "declining": ("text-red-600", "↓ Declining"),
            "stable": ("text-muted-foreground", "→ Stable"),
        }
        trend_cls, trend_text = trend_styles.get(
            trend_direction, ("text-muted-foreground", "→ Stable")
        )

        header = Div(
            Button(
                "← Back to Reflections", variant=ButtonT.ghost, size=Size.sm,
                **{"hx-get": f"/principles/{principle_uid}/reflections", "hx-target": "#view-content"},
            ),
            H2("Alignment Trend", cls="text-xl font-bold mt-4 mb-4"),
            P(f"Period: {period_start} to {period_end}", cls="text-muted-foreground mb-4"),
            cls="mb-4",
        )

        stats_row = Div(
            Card(
                Span("Reflections", cls="text-sm text-muted-foreground block"),
                Span(str(reflection_count), cls="text-2xl font-bold"),
                cls="bg-background shadow p-4 text-center",
            ),
            Card(
                Span("Avg Alignment", cls="text-sm text-muted-foreground block"),
                Span(f"{avg_alignment:.1f}/4", cls="text-2xl font-bold"),
                cls="bg-background shadow p-4 text-center",
            ),
            Card(
                Span("Trend", cls="text-sm text-muted-foreground block"),
                Span(trend_text, cls=f"text-2xl font-bold {trend_cls}"),
                cls="bg-background shadow p-4 text-center",
            ),
            Card(
                Span("Quality", cls="text-sm text-muted-foreground block"),
                Span(f"{quality_avg:.0%}", cls="text-2xl font-bold"),
                cls="bg-background shadow p-4 text-center",
            ),
            cls="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6",
        )

        trigger_items = []
        for trig_type, count in trigger_dist.items():
            trigger_items.append(
                Div(
                    Span(trig_type.title(), cls="text-muted-foreground"),
                    Span(str(count), cls="font-bold ml-auto"),
                    cls="flex justify-between py-2 border-b",
                )
            )

        trigger_section = (
            Card(
                H3("Reflection Triggers", cls="text-lg font-semibold mb-3"),
                *trigger_items
                if trigger_items
                else [P("No trigger data", cls="text-muted-foreground")],
                cls="bg-background shadow p-4",
            )
            if trigger_dist
            else None
        )

        return Div(header, stats_row, trigger_section, id="alignment-trend-view")


__all__ = ["PrinciplesViewComponents"]
