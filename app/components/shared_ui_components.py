"""
Shared UI Components Library
=============================

Reusable UI components across all SKUEL domains for consistent dashboard patterns.

Following 100% Dynamic Architecture:
- Generic patterns that work for ANY entity type
- Dynamic rendering via callable entity_renderer
- Composition-based, not inheritance
- DaisyUI component library with type-safe enums

Usage:
    from components.shared_ui_components import SharedUIComponents

    # Render complete dashboard
    dashboard = SharedUIComponents.render_entity_dashboard(
        title="🎯 Habit Tracker",
        stats={'total': 42, 'active': 38},
        entities=habits,
        entity_renderer=HabitUIComponents.render_habit_card,
        quick_actions=[
            {'label': '➕ New Habit', 'href': '/habits/wizard/step1', 'class': 'btn-primary'}
        ]
    )

Version: 2.0.0 (January 2026) - DaisyUI Migration
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H1,
    H2,
    H3,
    A,
    Body,
    Div,
    Form,
    Head,
    Html,
    Label,
    Link,
    Meta,
    Option,
    P,
    Script,
    Span,
    Title,
)

from core.ui.daisy_components import (
    Button,
    ButtonT,
    Card,
    Input,
    InputT,
    Select,
    Size,
)

from core.utils.logging import get_logger
from ui.layouts.navbar import create_navbar, create_navbar_for_request

if TYPE_CHECKING:
    from starlette.requests import Request

logger = get_logger("skuel.components.shared_ui")


class SharedUIComponents:
    """
    Reusable UI components for dashboards across all domains.

    Core Principle: "Write once, render everywhere"
    - Tasks dashboard uses this
    - Habits dashboard uses this
    - Goals dashboard uses this
    - Events dashboard uses this
    All with consistent layout and behavior.
    """

    # ========================================================================
    # DASHBOARD LAYOUT
    # ========================================================================

    @staticmethod
    def render_entity_dashboard(
        title: str,
        stats: dict[str, Any],
        entities: list[Any],
        entity_renderer: Callable[[Any], Any],
        quick_actions: list[dict[str, str]] | None = None,
        categories: list[str] | None = None,
        show_filter: bool = True,
        filter_endpoint: str | None = None,
        navbar: Any | None = None,
        request: "Request | None" = None,
        current_user: str | None = None,
        is_authenticated: bool = False,
        active_page: str = "",
    ) -> Html:
        """
        Generic dashboard layout for any entity type.

        Returns a complete Html document with explicit headers. This ensures
        navigation works correctly by avoiding FastHTML's default HTMX wrapping.

        Args:
            title: Dashboard title (e.g., "🎯 Habit Tracker"),
            stats: Dict of stat cards (see render_stats_cards),
            entities: List of entity instances to display,
            entity_renderer: Callable that renders a single entity card,
            quick_actions: List of action button configs,
            categories: List of category names for filtering,
            show_filter: Whether to show category filter,
            filter_endpoint: HTMX endpoint for category filtering,
            navbar: Optional custom navbar (default: auto-detected from request)
            request: Request object for automatic auth detection (RECOMMENDED)
            current_user: User UID/name for navbar display (fallback if no request)
            is_authenticated: Whether user is logged in (fallback if no request)
            active_page: Current page slug for navbar highlighting

        Returns:
            Complete Html document with dashboard layout

        Example:
            dashboard = SharedUIComponents.render_entity_dashboard(
                title="🎯 Habit Tracker",
                stats={
                    'total': {'label': 'Total Habits', 'value': 42, 'color': 'blue'},
                    'active': {'label': 'Active', 'value': 38, 'color': 'green'}
                },
                entities=habits,
                entity_renderer=HabitUIComponents.render_habit_card,
                quick_actions=[
                    {'label': '➕ New Habit', 'href': '/habits/wizard/step1', 'class': 'btn-primary'}
                ],
                request=request,  # Recommended: auto-detects user/admin from session
                active_page="habits",
            )
        """
        # Prefer request-based navbar (auto-detects user, admin status from session)
        # Falls back to manual parameters for backwards compatibility
        if navbar is None:
            if request is not None:
                navbar = create_navbar_for_request(request, active_page=active_page)
            else:
                navbar = create_navbar(
                    current_user=current_user,
                    is_authenticated=is_authenticated,
                    active_page=active_page,
                )

        quick_actions = quick_actions or []
        categories = categories or []

        # Build dashboard content
        dashboard_content = Div(
            H1(title, cls="text-3xl font-bold mb-6"),
            # Stats cards
            SharedUIComponents.render_stats_cards(stats),
            # Quick actions
            (SharedUIComponents.render_quick_actions(quick_actions) if quick_actions else None),
            # Entity list (with optional filter)
            SharedUIComponents.render_entity_list(
                entities=entities,
                entity_renderer=entity_renderer,
                categories=categories if show_filter else None,
                filter_endpoint=filter_endpoint,
            ),
            cls="container mx-auto p-6",
        )

        # Clean title for page (remove emoji prefix)
        page_title = title.lstrip("📋🎯🔄📅🔀⚖️ ")

        # Return complete Html document with explicit headers
        return Html(
            Head(
                Meta(charset="UTF-8"),
                Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
                Title(f"{page_title} - SKUEL"),
                # DaisyUI CSS
                Link(
                    href="https://cdn.jsdelivr.net/npm/daisyui@4.4.19/dist/full.min.css",
                    rel="stylesheet",
                    type="text/css",
                ),
                # Tailwind CSS
                Script(src="https://cdn.tailwindcss.com"),
                # HTMX - using 1.9.10 to match other working pages
                Script(src="https://unpkg.com/htmx.org@1.9.10"),
                # Alpine.js
                Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
                # SKUEL custom CSS
                Link(rel="stylesheet", href="/static/css/output.css"),
                Link(rel="stylesheet", href="/static/css/skuel.css"),
                # SKUEL JavaScript (Alpine components)
                Script(src="/static/js/skuel.js"),
            ),
            Body(
                navbar,
                dashboard_content,
                # Modal container for edit forms
                Div(id="modal"),
                cls="bg-base-200 min-h-screen",
            ),
            **{"data-theme": "light"},
        )

    # ========================================================================
    # STATS CARDS
    # ========================================================================

    @staticmethod
    def render_stats_cards(stats: dict[str, dict[str, Any]]) -> Div:
        """
        Render statistics cards in grid layout.

        Args:
            stats: Dict mapping stat_key to {label, value, color}

        Example:
            stats = {
                'total': {'label': 'Total Tasks', 'value': 125, 'color': 'blue'},
                'completed': {'label': 'Completed', 'value': 78, 'color': 'green'},
                'overdue': {'label': 'Overdue', 'value': 12, 'color': 'red'}
            }

        Color options: blue, green, orange, purple, red, gray
        """
        if not stats:
            return Div()  # Empty div if no stats

        color_classes = {
            "blue": "text-blue-600",
            "green": "text-green-600",
            "orange": "text-orange-600",
            "purple": "text-purple-600",
            "red": "text-red-600",
            "gray": "text-gray-600",
            "yellow": "text-yellow-600",
            "indigo": "text-indigo-600",
        }

        cards = []
        for stat_key, stat_data in stats.items():
            label = stat_data.get("label", stat_key.title())
            value = stat_data.get("value", 0)
            color = stat_data.get("color", "blue")
            color_class = color_classes.get(color, "text-blue-600")

            cards.append(
                Card(
                    Div(
                        Span(str(value), cls=f"text-3xl font-bold {color_class}"),
                        P(label, cls="text-sm text-gray-600 mt-1"),
                        cls="text-center",
                    ),
                    cls="p-4",
                )
            )

        # Responsive grid: 1 col mobile, 2 cols tablet, 4 cols desktop
        grid_cols = min(len(cards), 4)
        return Div(
            *cards, cls=f"grid grid-cols-1 md:grid-cols-2 lg:grid-cols-{grid_cols} gap-6 mb-8"
        )

    # ========================================================================
    # QUICK ACTIONS
    # ========================================================================

    @staticmethod
    def render_quick_actions(actions: list[dict[str, str]]) -> Div:
        """
        Render quick action buttons.

        Args:
            actions: List of action configs with label, href, class, hx_get, hx_target

        Example:
            actions = [
                {'label': '➕ New Task', 'href': '/tasks/create', 'class': 'btn-primary'},
                {'label': '📊 Analytics', 'hx_get': '/tasks/analytics', 'hx_target': '#main'}
            ]
        """
        if not actions:
            return Div()

        buttons = []
        for action in actions:
            # Parse variant from class string for backwards compatibility
            class_str = action.get("class", "btn-secondary")
            variant = ButtonT.secondary  # default

            # Extract variant from common class patterns
            if "btn-primary" in class_str:
                variant = ButtonT.primary
            elif "btn-secondary" in class_str:
                variant = ButtonT.secondary
            elif "btn-ghost" in class_str:
                variant = ButtonT.ghost
            elif "btn-outline" in class_str:
                variant = ButtonT.outline
            elif "btn-success" in class_str:
                variant = ButtonT.success
            elif "btn-warning" in class_str:
                variant = ButtonT.warning
            elif "btn-error" in class_str:
                variant = ButtonT.error
            elif "btn-info" in class_str:
                variant = ButtonT.info

            btn_attrs = {"variant": variant}

            # Support both href (standard link) and hx_get (HTMX)
            if "href" in action:
                btn_attrs["onclick"] = f"window.location.href='{action['href']}'"
            elif "hx_get" in action:
                btn_attrs["hx_get"] = action["hx_get"]
                if "hx_target" in action:
                    btn_attrs["hx_target"] = action["hx_target"]

            buttons.append(Button(action["label"], **btn_attrs))

        return Card(
            H3("Quick Actions", cls="text-xl font-semibold mb-4"),
            Div(*buttons, cls="flex flex-wrap gap-3"),
            cls="p-6 mb-8",
        )

    # ========================================================================
    # ENTITY LIST/GRID
    # ========================================================================

    @staticmethod
    def render_entity_list(
        entities: list[Any],
        entity_renderer: Callable[[Any], Any],
        categories: list[str] | None = None,
        filter_endpoint: str | None = None,
        empty_message: str = "No items found",
        list_id: str = "entity-list",
    ) -> Div:
        """
        Render list of entities with optional category filter.

        Args:
            entities: List of entity instances,
            entity_renderer: Function that renders a single entity,
            categories: Optional list of category names for filter,
            filter_endpoint: HTMX endpoint for filtering,
            empty_message: Message when no entities,
            list_id: HTML id for list container (for HTMX targeting)

        Example:
            entity_list = SharedUIComponents.render_entity_list(
                entities=tasks,
                entity_renderer=TaskUIComponents.render_task_card,
                categories=["work", "personal", "health"],
                filter_endpoint="/tasks/filter"
            )
        """
        # Build filter dropdown if categories provided
        filter_widget = None
        if categories and filter_endpoint:
            filter_widget = SharedUIComponents.render_category_filter(
                categories=categories, filter_endpoint=filter_endpoint, target_id=f"#{list_id}"
            )

        # Render entity cards
        if entities:
            entity_cards = [entity_renderer(entity) for entity in entities]
        else:
            entity_cards = [P(empty_message, cls="text-center text-gray-500 py-8")]

        return Card(
            H2("📋 All Items", cls="text-xl font-semibold mb-4"),
            filter_widget if filter_widget else None,
            Div(*entity_cards, id=list_id, cls="space-y-3"),
            cls="p-4",
        )

    @staticmethod
    def render_entity_grid(
        entities: list[Any],
        entity_renderer: Callable[[Any], Any],
        columns: int = 3,
        empty_message: str = "No items found",
    ) -> Div:
        """
        Render entities in grid layout (alternative to list).

        Args:
            entities: List of entity instances,
            entity_renderer: Function that renders a single entity,
            columns: Number of columns (1-4),
            empty_message: Message when no entities

        Example:
            grid = SharedUIComponents.render_entity_grid(
                entities=goals,
                entity_renderer=GoalUIComponents.render_goal_card,
                columns=3
            )
        """
        if not entities:
            return Div(P(empty_message, cls="text-center text-gray-500 py-8"))

        entity_cards = [entity_renderer(entity) for entity in entities]

        # Responsive grid
        return Div(
            *entity_cards,
            cls=f"grid grid-cols-1 md:grid-cols-2 lg:grid-cols-{min(columns, 4)} gap-6",
        )

    # ========================================================================
    # FILTERS & SEARCH
    # ========================================================================

    @staticmethod
    def render_category_filter(
        categories: list[str],
        filter_endpoint: str,
        target_id: str = "#entity-list",
        label: str = "Filter by Category",
    ) -> Div:
        """
        Render category filter dropdown.

        Args:
            categories: List of category names,
            filter_endpoint: HTMX endpoint for filtering,
            target_id: HTMX target selector,
            label: Filter label text
        """
        return Div(
            Label(label, cls="label font-semibold"),
            Select(
                Option("All Categories", value="all", selected=True),
                *[Option(cat.title(), value=cat) for cat in categories],
                name="category",
                variant=InputT.bordered,
                hx_get=filter_endpoint,
                hx_target=target_id,
                hx_trigger="change",
            ),
            cls="mb-4",
        )

    @staticmethod
    def render_search_bar(
        search_endpoint: str,
        target_id: str = "#search-results",
        placeholder: str = "Search...",
        include_fields: list[str] | None = None,
    ) -> Form:
        """
        Render search bar with HTMX.

        Args:
            search_endpoint: HTMX endpoint for search,
            target_id: HTMX target selector,
            placeholder: Search input placeholder,
            include_fields: Additional form fields to include in search

        Example:
            search = SharedUIComponents.render_search_bar(
                search_endpoint="/tasks/search",
                target_id="#task-results",
                placeholder="Search tasks..."
            )
        """
        return Form(
            Div(
                Input(
                    type="text",
                    name="query",
                    placeholder=placeholder,
                    variant=InputT.bordered,
                    hx_post=search_endpoint,
                    hx_target=target_id,
                    hx_trigger="keyup changed delay:300ms",
                ),
                cls="flex-1",
            ),
            cls="flex gap-2 mb-6",
        )

    # ========================================================================
    # SECTION HEADERS
    # ========================================================================

    @staticmethod
    def render_section_header(
        title: str, subtitle: str | None = None, actions: list[dict[str, str]] | None = None
    ) -> Div:
        """
        Render section header with optional subtitle and actions.

        Args:
            title: Section title,
            subtitle: Optional subtitle text,
            actions: Optional action buttons (same format as quick_actions)

        Example:
            header = SharedUIComponents.render_section_header(
                title="Today's Tasks",
                subtitle="5 tasks due today",
                actions=[{'label': 'View All', 'href': '/tasks'}]
            )
        """
        action_buttons = []
        if actions:
            for action in actions:
                btn_attrs = {"cls": action.get("class", "btn btn-sm btn-ghost")}
                if "href" in action:
                    btn_attrs["onclick"] = f"window.location.href='{action['href']}'"
                action_buttons.append(Button(action["label"], **btn_attrs))

        return Div(
            Div(
                H2(title, cls="text-2xl font-bold"),
                (P(subtitle, cls="text-sm text-gray-600") if subtitle else None),
                cls="flex-1",
            ),
            (Div(*action_buttons, cls="flex gap-2") if action_buttons else None),
            cls="flex items-center justify-between mb-4",
        )

    # ========================================================================
    # EMPTY STATES
    # ========================================================================

    @staticmethod
    def render_empty_state(
        icon: str, title: str, message: str, action: dict[str, str] | None = None
    ) -> Div:
        """
        Render empty state with optional action.

        Args:
            icon: Emoji icon,
            title: Empty state title,
            message: Explanation message,
            action: Optional action button config

        Example:
            empty = SharedUIComponents.render_empty_state(
                icon="📋",
                title="No tasks yet",
                message="Create your first task to get started",
                action={'label': 'Create Task', 'href': '/tasks/create', 'class': 'btn-primary'}
            )
        """
        action_button = None
        if action:
            # Parse variant from class string for backwards compatibility
            class_str = action.get("class", "btn-primary")
            variant = ButtonT.primary  # default

            # Extract variant from common class patterns
            if "btn-primary" in class_str:
                variant = ButtonT.primary
            elif "btn-secondary" in class_str:
                variant = ButtonT.secondary
            elif "btn-ghost" in class_str:
                variant = ButtonT.ghost
            elif "btn-outline" in class_str:
                variant = ButtonT.outline
            elif "btn-success" in class_str:
                variant = ButtonT.success
            elif "btn-warning" in class_str:
                variant = ButtonT.warning
            elif "btn-error" in class_str:
                variant = ButtonT.error
            elif "btn-info" in class_str:
                variant = ButtonT.info

            btn_attrs = {"variant": variant}
            if "href" in action:
                btn_attrs["onclick"] = f"window.location.href='{action['href']}'"
            elif "hx_get" in action:
                btn_attrs["hx_get"] = action["hx_get"]
                if "hx_target" in action:
                    btn_attrs["hx_target"] = action["hx_target"]
            action_button = Button(action["label"], **btn_attrs)

        return Card(
            Div(
                Span(icon, cls="text-6xl mb-4"),
                H3(title, cls="text-xl font-semibold mb-2"),
                P(message, cls="text-gray-600 mb-6"),
                action_button if action_button else None,
                cls="text-center py-12",
            ),
            cls="p-6",
        )

    # ========================================================================
    # DETAIL VIEW LAYOUT
    # ========================================================================

    @staticmethod
    def render_detail_view(
        title: str,
        entity_card: Any,
        sections: list[dict[str, Any]],
        actions: list[dict[str, str]] | None = None,
        back_link: str | None = None,
        navbar: Any | None = None,
        request: "Request | None" = None,
    ) -> Div:
        """
        Render detail view for a single entity.

        Args:
            title: Page title,
            entity_card: Main entity card component,
            sections: List of section dicts with 'title' and 'content',
            actions: Optional action buttons,
            back_link: Optional back navigation link
            navbar: Optional custom navbar
            request: Request object for automatic auth detection (RECOMMENDED)

        Example:
            detail = SharedUIComponents.render_detail_view(
                title="Task Details",
                entity_card=task_card,
                sections=[
                    {'title': 'Progress', 'content': progress_widget},
                    {'title': 'Comments', 'content': comments_list}
                ],
                actions=[{'label': 'Edit', 'href': '/tasks/123/edit'}],
                back_link="/tasks",
                request=request,
            )
        """
        # Prefer request-based navbar (auto-detects user, admin status from session)
        if navbar is None:
            if request is not None:
                navbar = create_navbar_for_request(request, active_page="")
            else:
                navbar = create_navbar()
        return Div(
            navbar,
            # Back button
            (
                Div(A("← Back", href=back_link, cls="btn btn-ghost btn-sm"), cls="mb-4")
                if back_link
                else None
            ),
            H1(title, cls="text-3xl font-bold mb-6"),
            # Main entity card
            entity_card,
            # Action buttons
            (
                Div(
                    *[
                        Button(
                            a["label"],
                            variant=(
                                ButtonT.primary
                                if "btn-primary" in a.get("class", "")
                                else ButtonT.ghost
                                if "btn-ghost" in a.get("class", "")
                                else ButtonT.outline
                                if "btn-outline" in a.get("class", "")
                                else ButtonT.secondary
                            ),
                            onclick=f"window.location.href='{a['href']}'" if "href" in a else None,
                        )
                        for a in actions
                    ],
                    cls="flex gap-3 my-6",
                )
                if actions
                else None
            ),
            # Additional sections
            *[
                Card(
                    H2(section["title"], cls="text-xl font-semibold mb-4"),
                    section["content"],
                    cls="p-6 mb-6",
                )
                for section in sections
            ],
            cls="container mx-auto p-6",
        )


class SharedUIComponentsExamples:
    """
    Example usage patterns for SharedUIComponents.

    Demonstrates how different domains can use the same components.
    """

    @staticmethod
    def _simple_habit_card(habit) -> Any:
        """Simple habit card renderer for examples."""
        return Card(P(habit.name), cls="p-4")

    @staticmethod
    def _simple_task_card(task) -> Any:
        """Simple task card renderer for examples."""
        return Card(P(task.title), cls="p-4")

    @staticmethod
    def _simple_goal_card(goal) -> Any:
        """Simple goal card renderer for examples."""
        return Card(P(goal.title), cls="p-4")

    @staticmethod
    def habits_dashboard_example(habits) -> Any:
        """Example: Habits dashboard using shared components"""
        return SharedUIComponents.render_entity_dashboard(
            title="🎯 Habit Tracker",
            stats={
                "total": {"label": "Total Habits", "value": len(habits), "color": "blue"},
                "active": {
                    "label": "Active",
                    "value": sum(1 for h in habits if h.status.value == "active"),
                    "color": "green",
                },
                "streaks": {
                    "label": "Active Streaks",
                    "value": sum(1 for h in habits if h.current_streak > 0),
                    "color": "orange",
                },
            },
            entities=habits,
            entity_renderer=SharedUIComponentsExamples._simple_habit_card,
            quick_actions=[
                {"label": "➕ New Habit", "href": "/habits/wizard/step1", "class": "btn-primary"},
                {"label": "📊 Analytics", "href": "/habits/analytics", "class": "btn-secondary"},
            ],
            categories=["health", "productivity", "learning"],
            filter_endpoint="/habits/filter",
        )

    @staticmethod
    def tasks_dashboard_example(tasks) -> Any:
        """Example: Tasks dashboard using shared components"""
        return SharedUIComponents.render_entity_dashboard(
            title="📋 Task Manager",
            stats={
                "total": {"label": "Total Tasks", "value": len(tasks), "color": "blue"},
                "completed": {
                    "label": "Completed",
                    "value": sum(1 for t in tasks if t.status.value == "completed"),
                    "color": "green",
                },
                "overdue": {"label": "Overdue", "value": 0, "color": "red"},
            },
            entities=tasks,
            entity_renderer=SharedUIComponentsExamples._simple_task_card,
            quick_actions=[
                {"label": "➕ New Task", "href": "/tasks/create", "class": "btn-primary"}
            ],
        )

    @staticmethod
    def goals_dashboard_example(goals) -> Any:
        """Example: Goals dashboard using grid layout"""
        from components.shared_ui_components import SharedUIComponents

        stats_cards = SharedUIComponents.render_stats_cards(
            {
                "total": {"label": "Total Goals", "value": len(goals), "color": "purple"},
                "active": {
                    "label": "In Progress",
                    "value": sum(1 for g in goals if g.status.value == "in_progress"),
                    "color": "blue",
                },
            }
        )

        goals_grid = SharedUIComponents.render_entity_grid(
            entities=goals, entity_renderer=SharedUIComponentsExamples._simple_goal_card, columns=3
        )

        return Div(
            create_navbar(),
            H1("🎯 Goals", cls="text-3xl font-bold mb-6"),
            stats_cards,
            goals_grid,
            cls="container mx-auto p-6",
        )


# Export
__all__ = ["SharedUIComponents", "SharedUIComponentsExamples"]
