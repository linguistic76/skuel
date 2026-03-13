"""
Habits UI Routes - Three-View Standalone Interface
==================================================

Three-view habit management UI with List, Create, and Calendar views.
Uses standalone layout (no sidebar) matching Tasks domain pattern.

Routes:
- GET /habits - Main dashboard with three views (standalone, no drawer)
- GET /habits/view/list - HTMX fragment for list view
- GET /habits/view/create - HTMX fragment for create view
- GET /habits/view/calendar - HTMX fragment for calendar view
- GET /habits/list-fragment - HTMX filtered list (for filter updates)
- POST /habits/quick-add - Create habit via form
"""

__version__ = "2.0"

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from fasthtml.common import H1, H2, H3, Div, P, Span
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.route_factories import QuickAddConfig, QuickAddRouteFactory
from adapters.inbound.ui_helpers import (
    parse_calendar_params,
)
from core.models.enums import Priority
from core.models.enums.entity_enums import EntityStatus
from core.models.habit.habit_request import HabitCreateRequest
from core.ports.query_types import ActivityFilterSpec
from core.services.habits_service import HabitsService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.habits.atomic_achievements import AtomicHabitsBadges
from ui.habits.atomic_analytics import AtomicHabitsAnalytics
from ui.habits.atomic_components import AtomicHabitsComponents
from ui.habits.atomic_intelligence import AtomicHabitsIntelligence
from ui.habits.atomic_mobile import AtomicHabitsMobile
from ui.habits.layout import create_habits_page
from ui.habits.views import HabitsViewComponents
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.navbar import create_navbar_for_request
from ui.layouts.page_types import PageType
from ui.patterns.card_generator import CardGenerator
from ui.patterns.entity_dashboard import SharedUIComponents
from ui.patterns.error_banner import render_error_banner
from ui.patterns.form_generator import FormGenerator
from ui.patterns.relationships import EntityRelationshipsSection
from ui.tokens import Container, Spacing

logger = get_logger("skuel.routes.habits.ui")


# RouteDecorator and Request imported from adapters.inbound.fasthtml_types

# ============================================================================
# UI COMPONENT LIBRARY - Reusable habit components
# ============================================================================


class HabitUIComponents:
    """Centralized habit UI components - no more inline composition"""

    @staticmethod
    def render_habits_content(
        habits=None,
        stats=None,
        categories=None,
    ) -> Any:
        """
        Habits dashboard content (without page wrapper).

        Used by create_profile_page() for Profile Hub integration.
        """
        habits = habits or []
        stats = stats or {}
        categories = categories or ["health", "productivity", "learning", "personal"]

        # Transform stats to shared format
        stats_formatted = {
            "total": {
                "label": "Total Habits",
                "value": stats.get("total_habits", 0),
                "color": "blue",
            },
            "completed": {
                "label": "Completed Today",
                "value": stats.get("completed_today", 0),
                "color": "green",
            },
            "streaks": {
                "label": "Active Streaks",
                "value": stats.get("current_streaks", 0),
                "color": "orange",
            },
            "rate": {
                "label": "Completion Rate",
                "value": f"{stats.get('completion_rate', 0)}%",
                "color": "purple",
            },
        }

        # Define quick actions
        quick_actions = [
            {
                "label": "New Habit",
                "hx_get": "/habits/wizard/step1",
                "hx_target": "#modal",
                "class": "btn-primary",
            },
            {
                "label": "Achievements",
                "hx_get": "/badges/showcase",
                "hx_target": "#main-content",
                "class": "btn-secondary",
            },
            {
                "label": "Analytics",
                "hx_get": "/habits/analytics",
                "hx_target": "#main-content",
                "class": "btn-secondary",
            },
        ]

        # Render content using shared components
        return Div(
            H1("Habit Tracker", cls="text-3xl font-bold mb-6"),
            SharedUIComponents.render_stats_cards(stats_formatted),
            SharedUIComponents.render_quick_actions(quick_actions),
            SharedUIComponents.render_category_filter(categories, "/habits/filter"),
            Div(
                *[HabitUIComponents.render_habit_card(habit) for habit in habits],
                cls="space-y-3",
                id="habits-list",
            )
            if habits
            else P(
                "No habits yet. Create one to get started!",
                cls="text-muted-foreground text-center py-8",
            ),
            Div(id="modal"),  # Modal container for HTMX
        )

    # NOTE: render_habit_stats(), render_action_buttons(), render_todays_habits(),
    # and render_all_habits() have been REMOVED.
    # These are now handled by SharedUIComponents.render_entity_dashboard().
    # Removed ~120 lines of duplicate code.

    @staticmethod
    def render_habit_card(habit, show_complete_button=False) -> Any:
        """
        Individual habit card component.

        ✅ ENHANCED: Now shows identity progress bar for identity-based habits.
        Previously: Basic card with streak indicators.
        Now: Includes Atomic Habits identity visualization when applicable.
        """
        uid = habit.get("uid", "") if isinstance(habit, dict) else habit.uid
        status = habit.get("status", "active") if isinstance(habit, dict) else habit.status
        habit.get("current_streak", 0) if isinstance(habit, dict) else getattr(
            habit, "current_streak", 0
        )

        # Atomic Habits MVP: Check for identity
        identity = (
            habit.get("reinforces_identity")
            if isinstance(habit, dict)
            else getattr(habit, "reinforces_identity", None)
        )
        identity_votes = (
            habit.get("identity_votes_cast", 0)
            if isinstance(habit, dict)
            else getattr(habit, "identity_votes_cast", 0)
        )
        is_identity_habit = identity is not None and identity != ""

        # Custom renderer for streak field
        def render_streak(value) -> Any:
            return Span(
                f"🔥 {value} day streak" if value > 0 else "⭐ Start your streak",
                cls="text-sm text-orange-600 font-medium",
            )

        # Generate card using CardGenerator
        card = CardGenerator.from_dataclass(
            habit,
            display_fields=["name", "description", "category", "recurrence_pattern", "status"],
            field_renderers={
                "current_streak": render_streak  # Custom streak indicator renderer
            },
            card_attrs={
                "id": f"habit-{uid}",
                "cls": f"border-l-4 {'border-blue-500' if str(status) == 'active' else 'border-border'} p-4",
            },
        )

        # MVP: Add identity progress bar if identity-based
        identity_component = None
        if is_identity_habit:
            identity_component = AtomicHabitsComponents.render_identity_progress_bar(
                identity=identity, votes_cast=identity_votes, votes_required=50, size="sm"
            )

        # Action buttons
        buttons = []
        if show_complete_button and str(status) == "active":
            buttons.append(
                Button(
                    "✅ Complete",
                    variant=ButtonT.success,
                    size=Size.sm,
                    hx_post=f"/api/habits/{uid}/track",
                    hx_target="#todays-habits",
                    hx_swap="outerHTML",
                )
            )

        buttons.extend(
            [
                Button(
                    "📊 View",
                    variant=ButtonT.outline,
                    size=Size.sm,
                    hx_get=f"/habits/{uid}/details",
                    hx_target="#modal",
                ),
                Button(
                    "🧠 Patterns",
                    variant=ButtonT.info,
                    size=Size.sm,
                    hx_get=f"/habits/{uid}/patterns",
                    hx_target="#modal",
                    title="AI Pattern Recognition (Phase 2)",
                ),
                Button(
                    "✏️ Edit",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    hx_get=f"/habits/{uid}/edit",
                    hx_target="#modal",
                ),
            ]
        )

        # Wrap card with identity progress (if applicable) and action buttons
        return Card(
            CardBody(
                card,
                identity_component if identity_component else None,
                Div(*buttons, cls="flex gap-2 mt-3"),
            )
        )

    @staticmethod
    def render_create_habit_form() -> Any:
        """
        Create habit form component.

        ✅ MIGRATED: Now uses FormGenerator for 100% dynamic form generation.
        Previously: 72 lines of manual form composition.
        Now: 15 lines using introspection-based generation.
        """
        return Card(
            CardBody(
                H2("➕ Create New Habit", cls="text-xl font-bold mb-4"),
                FormGenerator.from_model(
                    HabitCreateRequest,
                    action="/api/habits",
                    method="POST",
                    include_fields=[
                        "name",
                        "description",
                        "polarity",
                        "category",
                        "difficulty",
                        "recurrence_pattern",
                        "target_days_per_week",
                        "preferred_time",
                        "duration_minutes",
                        "priority",
                        "tags",
                        "cue",
                        "routine",
                        "reward",
                    ],
                    form_attrs={
                        "hx_post": "/api/habits",
                        "hx_target": "#habits-container",
                        "hx_swap": "outerHTML",
                    },
                    submit_label="Create Habit",
                ),
            ),
            cls="max-w-md mx-auto",
        )

    @staticmethod
    def render_habit_analytics_dashboard(request) -> Any:
        """
        Habit analytics dashboard - REFACTORED to use SharedUIComponents.

        BEFORE: Manual card composition
        AFTER: Shared section header component

        Args:
            request: Request object for session-aware navbar
        """
        return Div(
            create_navbar_for_request(request, active_page="habits"),
            SharedUIComponents.render_section_header(
                title="📊 Habit Analytics", subtitle="Performance insights and trends"
            ),
            # Overview cards
            Card(
                CardBody(
                    H2("📈 Performance Overview", cls="text-lg font-semibold mb-4"),
                    P("Analytics charts will be loaded here", cls="text-muted-foreground"),
                ),
                cls="mb-6",
            ),
            # Streak analysis
            Card(
                CardBody(
                    H2("🔥 Streak Analysis", cls="text-lg font-semibold mb-4"),
                    P("Streak patterns and trends", cls="text-muted-foreground"),
                ),
                cls="mb-6",
            ),
            # Behavioral insights
            Card(
                CardBody(
                    H2("🧠 Behavioral Insights", cls="text-lg font-semibold mb-4"),
                    P("AI-powered insights from your habit patterns", cls="text-muted-foreground"),
                ),
            ),
            cls="container mx-auto p-6",
        )

    @staticmethod
    def render_habit_progress_view() -> Any:
        """Habit progress view component"""
        return Div(
            H1("📈 Habit Progress", cls="text-2xl font-bold mb-6"),
            # Progress charts
            Card(
                CardBody(
                    H3("📊 Completion Trends", cls="text-lg font-semibold mb-4"),
                    P("Progress charts will be loaded here", cls="text-muted-foreground"),
                ),
                cls="mb-6",
            ),
            # Goal tracking
            Card(
                CardBody(
                    H3("🎯 Goal Tracking", cls="text-lg font-semibold mb-4"),
                    P("Track your habit goals and milestones", cls="text-muted-foreground"),
                ),
            ),
            cls="container mx-auto p-6",
        )


def get_status_color(status) -> Any:
    """Get color class for habit status"""
    colors = {"active": "success", "paused": "warning", "archived": "info", "completed": "success"}
    return colors.get(status, "ghost")


# ============================================================================
# CLEAN UI ROUTES - Component-based rendering only
# ============================================================================


@dataclass
class Filters:
    """Typed filters for habit list queries."""

    status: str
    sort_by: str


def parse_filters(request) -> Filters:
    """Extract filter parameters from request query params."""
    return Filters(
        status=request.query_params.get("filter_status", "active"),
        sort_by=request.query_params.get("sort_by", "streak"),
    )


def _render_wizard_step(form_data: dict[str, Any], step: int) -> Any:
    """Shared body for all wizard step POST handlers — eliminates 4x duplication."""
    return AtomicHabitsComponents.render_habit_creation_wizard(step=step, form_data=form_data)


def create_habits_ui_routes(_app, rt, habits_service: HabitsService, services: Any = None):
    """
    Create three-view habit UI routes (standalone, no drawer).

    Views:
    - List: Sortable, filterable habit list with streak indicators
    - Create: Full habit creation form (Atomic Habits wizard)
    - Calendar: Month/Week/Day views showing habit schedules
    """

    goals_service = services.goals if services else None
    logger.info("Registering three-view habit routes (standalone)")

    # ========================================================================
    # DATA FETCHING HELPERS
    # ========================================================================

    async def get_all_habits(user_uid: str) -> Result[list[Any]]:
        """Get all habits for user."""
        try:
            result = await habits_service.get_user_habits(user_uid)
            if result.is_error:
                logger.warning(f"Failed to fetch habits: {result.error}")
                return result  # Propagate the error
            return Result.ok(result.value or [])
        except Exception as e:
            logger.error(
                "Error fetching all habits",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to fetch habits: {e}"))

    async def get_categories() -> Result[list[str]]:
        """Get unique habit categories."""
        return Result.ok(
            ["health", "productivity", "learning", "personal", "fitness", "mindfulness"]
        )

    # ========================================================================
    # MAIN DASHBOARD (Standalone Three-View)
    # ========================================================================

    @rt("/habits")
    async def habits_dashboard(request) -> Any:
        """Main habits dashboard with three views (standalone, no drawer)."""
        user_uid = require_authenticated_user(request)

        # Get view parameter (default to list)
        view = request.query_params.get("view", "list")

        # Parse using helpers
        filters = parse_filters(request)
        calendar_params = parse_calendar_params(request)

        # Get data with Result[T]
        filtered_result = await habits_service.get_filtered_context(
            user_uid, filters.status, filters.sort_by
        )
        categories_result = await get_categories()

        # CHECK FOR ERRORS
        if filtered_result.is_error:
            error_content = Div(
                HabitsViewComponents.render_view_tabs(active_view=view),
                render_error_banner("Failed to load habits"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )
            return await create_habits_page(error_content, request=request)

        if categories_result.is_error:
            error_content = Div(
                HabitsViewComponents.render_view_tabs(active_view=view),
                render_error_banner("Failed to load categories"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )
            return await create_habits_page(error_content, request=request)

        # Extract values
        ctx = filtered_result.value
        habits, stats = ctx["entities"], ctx["stats"]
        categories = categories_result.value

        # Render the appropriate view content
        if view == "create":
            view_content = HabitsViewComponents.render_create_view(
                categories=categories,
            )
        elif view == "calendar":
            all_habits_result = await get_all_habits(user_uid)

            # Check for errors
            if all_habits_result.is_error:
                view_content = render_error_banner(
                    f"Failed to load calendar: {all_habits_result.error}"
                )
            else:
                view_content = HabitsViewComponents.render_calendar_view(
                    habits=all_habits_result.value,
                    current_date=calendar_params.current_date,
                    calendar_view=calendar_params.calendar_view,
                )
        else:  # list (default)
            view_content = HabitsViewComponents.render_list_view(
                habits=habits,
                filters={
                    "status": filters.status,
                    "sort_by": filters.sort_by,
                },
                stats=stats,
                categories=categories,
            )

        # Build page with tabs + view content
        page_content = Div(
            HabitsViewComponents.render_view_tabs(active_view=view),
            Div(view_content, id="view-content", role="tabpanel"),
            cls=f"{Spacing.PAGE} {Container.WIDE}",
        )

        return await create_habits_page(page_content, request=request)

    # ========================================================================
    # HTMX VIEW FRAGMENTS
    # ========================================================================

    @rt("/habits/view/list")
    async def habits_view_list(request) -> Any:
        """HTMX fragment for list view."""
        user_uid = require_authenticated_user(request)
        filters = parse_filters(request)

        filtered_result = await habits_service.get_filtered_context(
            user_uid, filters.status, filters.sort_by
        )
        categories_result = await get_categories()

        # Handle errors (return banner directly for HTMX swap)
        if filtered_result.is_error:
            return render_error_banner("Failed to load habits")

        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        ctx = filtered_result.value
        habits, stats = ctx["entities"], ctx["stats"]
        categories = categories_result.value

        filters_dict: ActivityFilterSpec = {"status": filters.status, "sort_by": filters.sort_by}
        return HabitsViewComponents.render_list_view(
            habits=habits,
            filters=filters_dict,
            stats=stats,
            categories=categories,
        )

    @rt("/habits/view/create")
    async def habits_view_create(request) -> Any:
        """HTMX fragment for create view."""
        require_authenticated_user(request)
        categories_result = await get_categories()

        # Handle errors
        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        return HabitsViewComponents.render_create_view(
            categories=categories_result.value,
        )

    @rt("/habits/view/calendar")
    async def habits_view_calendar(request) -> Any:
        """HTMX fragment for calendar view."""
        user_uid = require_authenticated_user(request)
        calendar_params = parse_calendar_params(request)

        habits_result = await get_all_habits(user_uid)

        # Handle errors
        if habits_result.is_error:
            return render_error_banner("Failed to load calendar")

        return HabitsViewComponents.render_calendar_view(
            habits=habits_result.value,
            current_date=calendar_params.current_date,
            calendar_view=calendar_params.calendar_view,
        )

    # ========================================================================
    # LIST FRAGMENT (for filter updates)
    # ========================================================================

    @rt("/habits/list-fragment")
    async def habits_list_fragment(request) -> Any:
        """Return filtered habit list for HTMX updates."""
        user_uid = require_authenticated_user(request)
        filters = parse_filters(request)

        filtered_result = await habits_service.get_filtered_context(
            user_uid, filters.status, filters.sort_by
        )

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load habits")

        ctx = filtered_result.value
        habits = ctx["entities"]

        # Return just the habit items
        habit_items = [HabitsViewComponents._render_habit_item(habit) for habit in habits]

        return Div(
            *habit_items
            if habit_items
            else [P("No habits found.", cls="text-muted-foreground text-center py-8")],
            id="habit-list",
            cls="space-y-3",
        )

    # ========================================================================
    # QUICK ADD (via QuickAddRouteFactory)
    # ========================================================================

    async def create_habit_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Any]:
        """
        Domain-specific habit creation logic.

        Handles form parsing, request building, and service call.
        """
        from core.models.enums import RecurrencePattern
        from core.models.enums.habit_enums import HabitCategory

        # Extract form data
        name = form_data.get("name", "").strip()
        description = form_data.get("description", "").strip() or None
        category_str = form_data.get("category", "other")
        frequency_str = form_data.get("frequency", "daily")
        target_days = form_data.get("target_days_per_week", "7")
        cue = form_data.get("cue", "").strip() or None
        routine = form_data.get("routine", "").strip() or None
        reward = form_data.get("reward", "").strip() or None

        try:
            target_days_int = int(target_days)
        except ValueError:
            target_days_int = 7

        # Map string values to enums
        category = HabitCategory(category_str) if category_str else HabitCategory.OTHER
        recurrence = RecurrencePattern(frequency_str) if frequency_str else RecurrencePattern.DAILY

        # Build create request
        create_request = HabitCreateRequest(
            name=name,
            description=description,
            category=category,
            recurrence_pattern=recurrence,
            target_days_per_week=target_days_int,
            cue=cue,
            routine=routine,
            reward=reward,
        )

        return await habits_service.create_habit(create_request, user_uid)

    async def render_habit_success_view(user_uid: str) -> Any:
        """Render list view after successful habit creation."""
        result = await habits_service.get_filtered_context(user_uid)
        if result.is_error:
            habits, stats = [], {}
        else:
            ctx = result.value
            habits, stats = ctx["entities"], ctx["stats"]
        categories = await get_categories()
        return HabitsViewComponents.render_list_view(
            habits=habits,
            filters={},
            stats=stats,
            categories=categories,
        )

    async def render_habit_add_another_view(user_uid: str) -> Any:
        """Render create view for add-another flow."""
        categories = await get_categories()
        return HabitsViewComponents.render_create_view(categories=categories)

    # Register quick-add route via factory
    habits_quick_add_config = QuickAddConfig(
        domain_name="habits",
        required_field="name",
        create_entity=create_habit_from_form,
        render_success_view=render_habit_success_view,
        render_add_another_view=render_habit_add_another_view,
    )
    QuickAddRouteFactory.register_route(rt, habits_quick_add_config)

    # ========================================================================
    # ATOMIC HABITS WIZARD ROUTES
    # ========================================================================

    @rt("/habits/wizard/step1")
    async def wizard_step1(request) -> Any:
        """Wizard Step 1: Basic habit + identity"""
        return _render_wizard_step(dict(await request.form()), 1)

    @rt("/habits/wizard/step2")
    async def wizard_step2(request) -> Any:
        """Wizard Step 2: Behavior design (cue-routine-reward)"""
        return _render_wizard_step(dict(await request.form()), 2)

    @rt("/habits/wizard/step3")
    async def wizard_step3(request) -> Any:
        """Wizard Step 3: Link to goals with essentiality"""
        return _render_wizard_step(dict(await request.form()), 3)

    @rt("/habits/wizard/step4")
    async def wizard_step4(request) -> Any:
        """Wizard Step 4: Review - just show the review, don't create yet"""
        return _render_wizard_step(dict(await request.form()), 4)

    @rt("/api/habits/create-with-identity")
    async def create_habit_with_identity(request) -> Any:
        """Create habit from wizard with identity and goal linking"""
        user_uid = require_authenticated_user(request)
        form_data = await request.form()
        wizard_data = dict(form_data)

        # Build HabitCreateRequest from wizard data — strip all string fields consistently
        create_request = HabitCreateRequest(
            name=wizard_data.get("name", "").strip(),
            description=wizard_data.get("description", "").strip() or None,
            cue=wizard_data.get("cue", "").strip() or None,
            routine=wizard_data.get("routine", "").strip() or None,
            reward=wizard_data.get("reward", "").strip() or None,
            reinforces_identity=wizard_data.get("identity", "").strip() or None,
            is_identity_habit=bool(wizard_data.get("identity", "").strip()),
        )

        # Extract goal essentiality from form fields (goal_essentiality_goal_123 = "essential")
        goal_essentiality = {
            key.replace("goal_essentiality_", ""): value
            for key, value in wizard_data.items()
            if key.startswith("goal_essentiality_")
        }

        # Create habit + link to goals via service orchestration
        result = await habits_service.create_with_goal_links(
            create_request, user_uid, goal_essentiality or None, goals_service
        )

        if result.is_error:
            logger.error(f"Failed to create habit: {result.error}")
            return Div(
                Card(
                    H2("Error Creating Habit", cls="text-xl font-bold text-red-600 mb-4"),
                    P(f"Failed to create habit: {result.error}", cls="text-muted-foreground mb-4"),
                    Button(
                        "Try Again",
                        variant=ButtonT.primary,
                        hx_get="/habits/wizard/step1",
                        hx_target="#modal",
                    ),
                    cls="p-6",
                )
            )

        habit = result.value

        # Return success message and redirect to habits dashboard
        return Div(
            Card(
                H2("Habit Created!", cls="text-2xl font-bold text-green-600 mb-4 text-center"),
                P(
                    f"Successfully created: {habit.title}",
                    cls="text-lg text-muted-foreground mb-2 text-center",
                ),
                (
                    Div(
                        P(
                            f'"{habit.reinforces_identity}"',
                            cls="italic text-purple-700 text-center",
                        ),
                        P(
                            "Every completion is a vote for this identity!",
                            cls="text-sm text-muted-foreground text-center mt-2",
                        ),
                        cls="p-4 bg-purple-50 rounded-lg mb-6",
                    )
                    if habit.is_identity_habit
                    else None
                ),
                Button(
                    "View Habits Dashboard",
                    variant=ButtonT.primary,
                    cls="w-full",
                    hx_get="/habits",
                    hx_target="#main-content",
                ),
                cls="p-8 max-w-md mx-auto",
            ),
            hx_swap_oob="true",
            id="main-content",
        )

    @rt("/habits/{uid}/complete")
    async def habit_complete(request, uid: str) -> Any:
        """Complete habit: update streak, cast identity vote, recalculate goal impacts"""
        user_uid = require_authenticated_user(request)

        result = await habits_service.complete_with_goal_impacts(uid, user_uid, goals_service)
        if result.is_error:
            logger.warning(f"Habit completion failed for {uid}: {result.error}")
            return Div(P("Error: Could not complete habit", cls="text-red-600"), cls="p-4")

        updated_habit = result.value["habit"]
        goal_impacts = result.value["goal_impacts"]

        return AtomicHabitsComponents.render_habit_completion_celebration(
            habit_name=updated_habit.title,
            identity=updated_habit.reinforces_identity,
            votes_cast=updated_habit.identity_votes_cast,
            votes_required=50,
            goal_impacts=goal_impacts,
        )

    @rt("/habits/{uid}/complete/celebrate")
    async def habit_completion_celebration(_request, _uid: str) -> Any:
        """Show completion celebration (legacy route - redirects to POST /complete)"""
        # Redirect to the actual completion handler
        return Div(
            P(
                "Please use the Complete button to mark habit as done",
                cls="text-muted-foreground p-4",
            )
        )

    # ========================================================================
    # INTELLIGENCE ROUTES
    # ========================================================================

    @rt("/habits/{uid}/patterns")
    async def habit_patterns_view(request, uid: str) -> Any:
        """Pattern recognition for a habit"""
        user_uid = require_authenticated_user(request)

        result = await habits_service.patterns.analyze_patterns(uid, user_uid)
        if result.is_error:
            logger.warning(f"Habit pattern analysis failed for {uid}: {result.error}")
            return Div(P("Error: Could not find habit", cls="text-red-600"), cls="p-4")

        analysis = result.value
        pattern_data = {
            "name": analysis.name,
            "total_completions": analysis.total_completions,
            "success_patterns": analysis.success_patterns,
            "failure_patterns": analysis.failure_patterns,
        }

        return AtomicHabitsIntelligence.render_pattern_recognition(pattern_data)

    @rt("/goals/{uid}/system-health")
    async def goal_system_health_view(_request, uid: str) -> Any:
        """System health diagnostics for a goal"""
        result = await habits_service.goal_analytics.get_system_health(uid)
        if result.is_error:
            logger.error(f"Failed to get system health for goal {uid}: {result.error}")
            return Div(P("Error: Could not analyze goal system", cls="text-red-600"), cls="p-4")

        health = result.value
        system_health = {
            "goal_title": health.goal_title,
            "system_strength": health.system_strength,
            "diagnosis": health.diagnosis,
            "warnings": health.warnings,
            "recommendations": health.recommendations,
            "habit_breakdown": health.habit_breakdown,
            "system_exists": health.system_exists,
        }

        return AtomicHabitsIntelligence.render_system_health_diagnostics(system_health)

    @rt("/goals/{uid}/velocity")
    async def goal_velocity_view(_request, uid: str) -> Any:
        """Velocity tracking for a goal"""
        result = await habits_service.goal_analytics.get_velocity(uid)
        if result.is_error:
            logger.error(f"Failed to get velocity for goal {uid}: {result.error}")
            return Div(P("Error: Could not analyze goal velocity", cls="text-red-600"), cls="p-4")

        vel = result.value
        velocity_data = {
            "goal_title": vel.goal_title,
            "current_velocity": vel.current_velocity,
            "trend": vel.trend,
            "velocity_trend": vel.velocity_trend,
            "weighted_breakdown": vel.weighted_breakdown,
            "total_weighted_completions": vel.total_weighted_completions,
        }

        return AtomicHabitsIntelligence.render_velocity_tracking(velocity_data)

    @rt("/goals/{uid}/impact")
    async def goal_impact_view(_request, uid: str) -> Any:
        """Impact analysis for a goal"""
        result = await habits_service.goal_analytics.get_impact_analysis(uid)
        if result.is_error:
            logger.error(f"Failed to get impact analysis for goal {uid}: {result.error}")
            return Div(P("Error: Could not analyze goal impact", cls="text-red-600"), cls="p-4")

        impact = result.value
        impact_data = {
            "goal_title": impact.goal_title,
            "achievement_probability": impact.achievement_probability,
            "overall_impact": impact.overall_impact,
            "habits": impact.habits,
        }

        return AtomicHabitsIntelligence.render_goal_impact_analysis(impact_data)

    # ========================================================================
    # ACHIEVEMENT BADGE ROUTES
    # ========================================================================

    @rt("/badges/showcase")
    async def badges_showcase_view(request) -> Any:
        """Badge showcase page with all achievements"""
        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        params = dict(request.query_params)
        show_locked = params.get("show_locked", "true").lower() == "true"

        # Fetch real user badge progress from completion tracking service
        if habits_service.completions:
            badge_progress_result = await habits_service.completions.get_badge_progress(user_uid)
            user_data = badge_progress_result.value if badge_progress_result.is_ok else {}
        else:
            user_data = {}

        badges = AtomicHabitsBadges.calculate_badge_progress(user_data)

        return AtomicHabitsBadges.render_badge_showcase(user_badges=badges, show_locked=show_locked)

    @rt("/badges/celebration/{badge_id}")
    async def badge_celebration_modal(request, badge_id: str) -> Any:
        """Show badge unlock celebration modal"""
        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        # Fetch real user badge progress from completion tracking service
        if habits_service.completions:
            badge_progress_result = await habits_service.completions.get_badge_progress(user_uid)
            user_data = badge_progress_result.value if badge_progress_result.is_ok else {}
        else:
            user_data = {}

        # Calculate all badges and find the specific one
        all_badges = AtomicHabitsBadges.calculate_badge_progress(user_data)
        badge = next((b for b in all_badges if b.uid == badge_id), None)

        # Fallback to creating badge if not found
        if not badge:
            badge = AtomicHabitsBadges.create_badge(
                badge_id=badge_id,
                current_value=0.0,
                is_unlocked=False,
                unlock_date=None,
            )

        return AtomicHabitsBadges.render_badge_unlock_celebration(badge)

    @rt("/badges/widget")
    async def badges_progress_widget(request) -> Any:
        """Compact badge progress widget for dashboard"""
        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        # Fetch real user badge progress from completion tracking service
        if habits_service.completions:
            badge_progress_result = await habits_service.completions.get_badge_progress(user_uid)
            user_data = badge_progress_result.value if badge_progress_result.is_ok else {}
        else:
            user_data = {}

        badges = AtomicHabitsBadges.calculate_badge_progress(user_data)

        return AtomicHabitsBadges.render_badge_progress_widget(near_unlock_badges=badges, limit=3)

    # ========================================================================
    # ADVANCED ANALYTICS ROUTES
    # ========================================================================

    @rt("/habits/analytics")
    async def habits_analytics_dashboard(request) -> Any:
        """
        Advanced analytics dashboard.
        Requires authentication.
        """
        # Get authenticated user from session (raises 401 if not authenticated)
        require_authenticated_user(request)

        params = dict(request.query_params)
        date_range_param = params.get("range", "30d")

        # Calculate date range
        end_date = date.today()
        if date_range_param == "7d":
            start_date = end_date - timedelta(days=7)
        elif date_range_param == "90d":
            start_date = end_date - timedelta(days=90)
        elif date_range_param == "365d":
            start_date = end_date - timedelta(days=365)
        else:  # 30d default
            start_date = end_date - timedelta(days=30)

        return AtomicHabitsAnalytics.render_analytics_dashboard(date_range=(start_date, end_date))

    @rt("/analytics/update")
    async def analytics_update_fragment(request) -> Any:
        """Update analytics with new date range"""
        dict(request.query_params)
        return habits_analytics_dashboard(request)

    @rt("/analytics/export")
    async def analytics_export_modal(_request) -> Any:
        """Show export modal"""
        return AtomicHabitsAnalytics.render_export_modal(export_format="csv")

    @rt("/analytics/export/download")
    async def analytics_export_download(_request) -> Any:
        """Download analytics data"""
        # NOTE: Export feature stub - returns placeholder content
        return Response(
            content="CSV export would be generated here",
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=habit_analytics.csv"},
        )

    # ========================================================================
    # MOBILE-OPTIMIZED ROUTES
    # ========================================================================

    @rt("/habits/mobile")
    async def habits_mobile_dashboard(request) -> Any:
        """Mobile-optimized today's habits view"""
        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        # Fetch all user habits
        habits_result = await habits_service.get_user_habits(user_uid)
        all_habits = habits_result.value if habits_result.is_ok else []

        # Fetch today's completions
        completed_habit_uids = set()
        if habits_service.completions:
            completions_result = await habits_service.completions.get_today_completions(user_uid)
            if completions_result.is_ok:
                completed_habit_uids = {item["habit"].uid for item in completions_result.value}

        # Map priority to essentiality
        def priority_to_essentiality(priority: Priority) -> str:
            mapping = {
                Priority.HIGH: "critical",
                Priority.MEDIUM: "essential",
                Priority.LOW: "supporting",
            }
            return mapping.get(priority, "optional")

        # Build habits data for mobile view
        habits_today = [
            {
                "uid": habit.uid,
                "name": habit.title,
                "reinforces_identity": habit.reinforces_identity,
                "essentiality": priority_to_essentiality(habit.priority),
                "cue": habit.cue,
                "completed_today": habit.uid in completed_habit_uids,
            }
            for habit in all_habits
            if habit.status == EntityStatus.ACTIVE
        ]

        # Calculate stats
        completed_today = len(completed_habit_uids)
        total_today = len(habits_today)

        # Get current streak (use first habit's streak or 0)
        current_streak = all_habits[0].current_streak if all_habits else 0

        stats = {
            "current_streak": current_streak,
            "completed_today": completed_today,
            "total_today": total_today,
        }

        return AtomicHabitsMobile.render_mobile_dashboard(habits_today=habits_today, stats=stats)

    @rt("/habits/{uid}/mobile-detail")
    async def habit_mobile_detail_view(request, uid: str) -> Any:
        """Mobile-optimized habit detail view"""
        user_uid = require_authenticated_user(request)

        # Ownership verification - returns NotFound if user doesn't own this habit
        habit_result = await habits_service.core.verify_ownership(uid, user_uid)
        if habit_result.is_error:
            return P("Habit not found", cls="text-center text-muted-foreground py-8")

        habit = habit_result.value

        # Map priority to essentiality
        def priority_to_essentiality(priority: Priority) -> str:
            mapping = {
                Priority.HIGH: "critical",
                Priority.MEDIUM: "essential",
                Priority.LOW: "supporting",
            }
            return mapping.get(priority, "optional")

        # Build habit detail data
        habit_data = {
            "uid": habit.uid,
            "name": habit.title,
            "reinforces_identity": habit.reinforces_identity,
            "essentiality": priority_to_essentiality(habit.priority),
            "cue": habit.cue,
            "routine": habit.routine,
            "reward": habit.reward,
            "identity_votes_cast": habit.identity_votes_cast,
            "current_streak": habit.current_streak,
        }

        return AtomicHabitsMobile.render_mobile_habit_detail(habit_data)

    # ========================================================================
    # HTMX FRAGMENT ENDPOINTS
    # ========================================================================

    @rt("/habits/filter")
    async def habits_filter_fragment(request) -> Any:
        """Return filtered habits fragment for HTMX updates"""
        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        params = dict(request.query_params)
        category = params.get("category", "all")

        # Fetch user habits
        habits_result = await habits_service.get_user_habits(user_uid)
        all_habits = habits_result.value if habits_result.is_ok else []

        # Filter by category if not "all"
        if category != "all":
            filtered_habits = [h for h in all_habits if h.category.value == category]
        else:
            filtered_habits = all_habits

        return (
            Div(
                *[HabitUIComponents.render_habit_card(habit) for habit in filtered_habits],
                cls="space-y-3",
            )
            if filtered_habits
            else P(
                "No habits found for this category", cls="text-center text-muted-foreground py-8"
            )
        )

    @rt("/habits/{uid}/details")
    async def habit_details_modal(_request, uid: str) -> Any:
        """Habit details modal fragment"""
        return Card(
            CardBody(
                H2("📊 Habit Details", cls="text-xl font-bold mb-4"),
                P(
                    f"Detailed view for habit {uid} will be implemented here",
                    cls="text-muted-foreground",
                ),
            ),
        )

    @rt("/habits/{uid}/save", methods=["POST"])
    async def habit_save(request, uid: str) -> Any:
        """Save habit changes"""
        user_uid = require_authenticated_user(request)

        # Ownership verification before mutation
        ownership_result = await habits_service.core.verify_ownership(uid, user_uid)
        if ownership_result.is_error:
            return Card(
                CardBody(
                    H2("Error", cls="text-xl font-bold text-red-600 mb-4"),
                    P("Habit not found", cls="text-muted-foreground"),
                    Button(
                        "Close",
                        size=Size.sm,
                        cls="mt-4",
                        onclick="document.getElementById('modal').innerHTML=''",
                    ),
                ),
            )

        # Get form data
        form_data = await request.form()

        # Prepare update data
        updates = {
            "name": form_data.get("name", "").strip(),
            "description": form_data.get("description", "").strip(),
            "cue": form_data.get("cue", "").strip(),
            "routine": form_data.get("routine", "").strip(),
            "reward": form_data.get("reward", "").strip(),
            "status": form_data.get("status", "active"),
        }

        # Update via service
        result = await habits_service.update(uid, updates)

        if result.is_error:
            logger.error(f"Failed to update habit: {result.error}")
            return Card(
                CardBody(
                    H2("Error", cls="text-xl font-bold text-red-600 mb-4"),
                    P(f"Failed to save: {result.error}", cls="text-muted-foreground"),
                    Button(
                        "Close",
                        size=Size.sm,
                        cls="mt-4",
                        onclick="document.getElementById('modal').innerHTML=''",
                    ),
                ),
            )

        # Return success with redirect
        return Response(
            status_code=200,
            headers={"HX-Redirect": "/habits?view=list"},
        )

    @rt("/habits/{uid}/edit")
    async def habit_edit_form(request, uid: str) -> Any:
        """Edit habit form fragment"""
        user_uid = require_authenticated_user(request)

        # Ownership verification - returns NotFound if user doesn't own this habit
        result = await habits_service.core.verify_ownership(uid, user_uid)
        if result.is_error:
            return Card(
                CardBody(
                    H2("Error", cls="text-xl font-bold text-red-600 mb-4"),
                    P(f"Could not load habit: {result.error}", cls="text-muted-foreground"),
                    Button(
                        "Close",
                        size=Size.sm,
                        cls="mt-4",
                        onclick="document.getElementById('modal').innerHTML=''",
                    ),
                ),
            )

        habit = result.value

        # Get current values
        name = getattr(habit, "name", "")
        description = getattr(habit, "description", "") or ""
        cue = getattr(habit, "cue", "") or ""
        routine = getattr(habit, "routine", "") or ""
        reward = getattr(habit, "reward", "") or ""
        from core.utils.type_converters import normalize_enum_str

        status = normalize_enum_str(getattr(habit, "status", None), "active")

        from fasthtml.common import Form, Label, Option

        from ui.forms import Input, Select, Textarea

        return Card(
            CardBody(
                H2("Edit Habit", cls="text-xl font-bold mb-4"),
                Form(
                    # Name
                    Div(
                        Label("Name", cls="label"),
                        Input(
                            type="text",
                            name="name",
                            value=name,
                            required=True,
                        ),
                        cls="form-control mb-3",
                    ),
                    # Description
                    Div(
                        Label("Description", cls="label"),
                        Textarea(
                            description,
                            name="description",
                            rows="2",
                        ),
                        cls="form-control mb-3",
                    ),
                    # Cue
                    Div(
                        Label("Cue (trigger)", cls="label"),
                        Input(
                            type="text",
                            name="cue",
                            value=cue,
                            placeholder="What triggers this habit?",
                        ),
                        cls="form-control mb-3",
                    ),
                    # Routine
                    Div(
                        Label("Routine (action)", cls="label"),
                        Input(
                            type="text",
                            name="routine",
                            value=routine,
                            placeholder="What do you do?",
                        ),
                        cls="form-control mb-3",
                    ),
                    # Reward
                    Div(
                        Label("Reward", cls="label"),
                        Input(
                            type="text",
                            name="reward",
                            value=reward,
                            placeholder="What's the benefit?",
                        ),
                        cls="form-control mb-3",
                    ),
                    # Status
                    Div(
                        Label("Status", cls="label"),
                        Select(
                            Option("Active", value="active", selected=(status == "active")),
                            Option("Paused", value="paused", selected=(status == "paused")),
                            Option(
                                "Completed", value="completed", selected=(status == "completed")
                            ),
                            name="status",
                        ),
                        cls="form-control mb-4",
                    ),
                    # Buttons
                    Div(
                        Button(
                            "Save Changes",
                            type="submit",
                            variant=ButtonT.primary,
                        ),
                        Button(
                            "Cancel",
                            type="button",
                            variant=ButtonT.ghost,
                            cls="ml-2",
                            onclick="document.getElementById('modal').innerHTML=''",
                        ),
                        cls="flex gap-2",
                    ),
                    **{
                        "hx-post": f"/habits/{uid}/save",
                        "hx-target": "#modal",
                        "hx-swap": "innerHTML",
                    },
                ),
            ),
            cls="max-w-lg",
        )

    # ========================================================================
    # JAVASCRIPT INTEGRATION
    # ========================================================================

    @rt("/static/js/habits.js")
    async def habits_javascript(_request) -> Any:
        """Serve habits-specific JavaScript"""
        js_content = """
        // Habits UI JavaScript - no more inline scripts in routes!

        function closeModal() {
            document.getElementById('modal').innerHTML = '';
        }

        function markHabitComplete(habitUid) {
            htmx.ajax('POST', `/api/habits/${habitUid}/track`, '#todays-habits');
        }

        function refreshHabits() {
            htmx.trigger('#habits-container', 'refresh');
        }

        // HTMX event handlers
        document.addEventListener('htmx:afterSwap', function(evt) {
            if (evt.detail.target.id === 'habits-list') {
                console.log('Habits list updated');
            }
        });

        console.log('Habits UI JavaScript loaded');
        """

        return Response(js_content, media_type="application/javascript")

    # ========================================================================
    # HABIT DETAIL PAGE
    # ========================================================================

    @rt("/habits/{uid}")
    async def habit_detail_view(request: Any, uid: str) -> Any:
        """
        Habit detail view with full context and relationships.

        Shows habit details plus lateral relationships visualization.
        """
        user_uid = require_authenticated_user(request)

        # Fetch habit with ownership verification
        result = await habits_service.get_for_user(uid, user_uid)

        if result.is_error:
            logger.error(f"Failed to get habit {uid}: {result.error}")
            return await BasePage(
                content=Card(
                    H2("Habit Not Found", cls="text-xl font-bold text-error mb-4"),
                    P(f"Could not find habit: {uid}", cls="text-muted-foreground"),
                    Button(
                        "← Back to Habits",
                        **{"hx-get": "/habits", "hx-target": "body"},
                        variant=ButtonT.primary,
                        cls="mt-4",
                    ),
                    cls="p-6",
                ),
                title="Habit Not Found",
                page_type=PageType.STANDARD,
                request=request,
                active_page="habits",
            )

        habit = result.value

        # Render detail page
        content = Div(
            # Header Card
            Card(
                H1(f"🎯 {habit.title}", cls="text-2xl font-bold mb-2"),
                P(habit.description or "No description provided", cls="text-muted-foreground mb-4"),
                # Status and Frequency badges
                Div(
                    Badge(f"Status: {habit.status.value}", variant=BadgeT.info, cls="mr-2"),
                    Badge(
                        f"Frequency: {f'{habit.target_days_per_week}x/week' if habit.target_days_per_week else 'Not set'}",
                        variant=BadgeT.success,
                        cls="mr-2",
                    ),
                    Badge(f"Streak: {habit.current_streak or 0} days", variant=BadgeT.warning),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-6 mb-4",
            ),
            # Details Card
            Card(
                H2("📋 Habit Details", cls="text-xl font-semibold mb-4"),
                Div(
                    # Cue and Response
                    (
                        Div(
                            P("Cue:", cls="text-sm font-semibold text-muted-foreground mb-1"),
                            P(habit.cue or "Not specified", cls="text-foreground mb-3"),
                            cls="mb-4",
                        )
                        if habit.cue
                        else Div()
                    ),
                    # Created Date
                    Div(
                        P("Created:", cls="text-sm font-semibold text-muted-foreground mb-1"),
                        P(str(habit.created_at)[:10], cls="text-muted-foreground text-sm"),
                    ),
                    cls="space-y-2",
                ),
                cls="p-6 mb-4",
            ),
            # Actions Card
            Card(
                Div(
                    Button(
                        "← Back to Habits",
                        **{"hx-get": "/habits", "hx-target": "body"},
                        variant=ButtonT.ghost,
                        cls="mr-2",
                    ),
                    Button(
                        "✏️ Edit Habit",
                        **{"hx-get": f"/habits/{habit.uid}/edit", "hx-target": "#modal"},
                        variant=ButtonT.primary,
                        cls="mr-2",
                    ),
                    Button(
                        "✓ Track Today",
                        **{"hx-post": f"/api/habits/{habit.uid}/track", "hx-target": "body"},
                        variant=ButtonT.success,
                    ),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-4 mb-4",
            ),
            # Lateral Relationships Section
            EntityRelationshipsSection(
                entity_uid=habit.uid,
                entity_type="habits",
            ),
            cls=f"{Container.NARROW} {Spacing.PAGE}",
        )

        return await BasePage(
            content=content,
            title=habit.title,
            page_type=PageType.STANDARD,
            request=request,
            active_page="habits",
        )

    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_habits_ui_routes"]
