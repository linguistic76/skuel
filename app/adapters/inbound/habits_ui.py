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
from operator import itemgetter
from typing import Any, Protocol

from fasthtml.common import H1, H2, H3, P
from starlette.responses import Response

from components.atomic_habits_achievements import AtomicHabitsBadges
from components.atomic_habits_analytics import AtomicHabitsAnalytics
from components.atomic_habits_components import AtomicHabitsComponents
from components.atomic_habits_intelligence import AtomicHabitsIntelligence
from components.atomic_habits_mobile import AtomicHabitsMobile
from components.card_generator import CardGenerator
from components.error_components import ErrorComponents
from components.form_generator import FormGenerator
from components.habits_views import HabitsViewComponents
from components.shared_ui_components import SharedUIComponents
from core.auth import require_authenticated_user
from core.infrastructure.routes import QuickAddConfig, QuickAddRouteFactory
from core.models.enums import Priority
from core.models.enums.ku_enums import KuStatus
from core.models.habit.habit_request import HabitCreateRequest
from core.services.protocols.facade_protocols import GoalsFacadeProtocol, HabitsFacadeProtocol
from core.services.protocols.query_types import ActivityFilterSpec
from core.ui.daisy_components import Button, ButtonT, Card, CardBody, Div, Size, Span
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import (
    get_created_at_attr,
    get_current_streak,
    get_name_lower,
    get_recurrence_pattern,
)
from ui.habits.layout import create_habits_page
from ui.layouts.base_page import BasePage
from ui.layouts.navbar import create_navbar_for_request
from ui.layouts.page_types import PageType
from ui.patterns.relationships import EntityRelationshipsSection
from ui.tokens import Container, Spacing

logger = get_logger("skuel.routes.habits.ui")


# ============================================================================
# TYPE PROTOCOLS
# ============================================================================


class RouteDecorator(Protocol):
    """Protocol for FastHTML route decorator."""

    def __call__(self, path: str, methods: list[str] | None = None) -> Any: ...


class Request(Protocol):
    """Protocol for Starlette Request (lightweight)."""

    query_params: dict[str, str]

    async def form(self) -> dict[str, Any]: ...


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
                "No habits yet. Create one to get started!", cls="text-gray-500 text-center py-8"
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

        ✅ ENHANCED: Now shows identity progress bar for identity-based habits (Phase 1 MVP).
        Previously: Basic card with streak indicators.
        Now: Includes Atomic Habits identity visualization when applicable.
        """
        uid = habit.get("uid", "") if isinstance(habit, dict) else habit.uid
        status = habit.get("status", "active") if isinstance(habit, dict) else habit.status
        habit.get("current_streak", 0) if isinstance(habit, dict) else getattr(
            habit, "current_streak", 0
        )

        # Atomic Habits Phase 1 MVP: Check for identity
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
                "cls": f"border-l-4 {'border-blue-500' if str(status) == 'active' else 'border-gray-300'} p-4",
            },
        )

        # Phase 1 MVP: Add identity progress bar if identity-based
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
                    P("Analytics charts will be loaded here", cls="text-gray-500"),
                ),
                cls="mb-6",
            ),
            # Streak analysis
            Card(
                CardBody(
                    H2("🔥 Streak Analysis", cls="text-lg font-semibold mb-4"),
                    P("Streak patterns and trends", cls="text-gray-500"),
                ),
                cls="mb-6",
            ),
            # Behavioral insights
            Card(
                CardBody(
                    H2("🧠 Behavioral Insights", cls="text-lg font-semibold mb-4"),
                    P("AI-powered insights from your habit patterns", cls="text-gray-500"),
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
                    P("Progress charts will be loaded here", cls="text-gray-500"),
                ),
                cls="mb-6",
            ),
            # Goal tracking
            Card(
                CardBody(
                    H3("🎯 Goal Tracking", cls="text-lg font-semibold mb-4"),
                    P("Track your habit goals and milestones", cls="text-gray-500"),
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


def create_habits_ui_routes(
    _app, rt, habits_service: HabitsFacadeProtocol, goals_service: GoalsFacadeProtocol | None = None
):
    """
    Create three-view habit UI routes (standalone, no drawer).

    Views:
    - List: Sortable, filterable habit list with streak indicators
    - Create: Full habit creation form (Atomic Habits wizard)
    - Calendar: Month/Week/Day views showing habit schedules

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        habits_service: Habits service
        goals_service: Goals service for habit-goal linking and goal diagnostics
    """

    logger.info("Registering three-view habit routes (standalone)")

    # ========================================================================
    # QUERY PARAM TYPES
    # ========================================================================

    @dataclass
    class Filters:
        """Typed filters for habit list queries."""

        status: str
        sort_by: str

    @dataclass
    class CalendarParams:
        """Typed params for calendar view."""

        calendar_view: str
        current_date: date

    # ========================================================================
    # HELPER FUNCTIONS
    # ========================================================================

    def parse_filters(request) -> Filters:
        """Extract filter parameters from request query params."""
        return Filters(
            status=request.query_params.get("filter_status", "active"),
            sort_by=request.query_params.get("sort_by", "streak"),
        )

    def parse_calendar_params(request) -> CalendarParams:
        """Extract calendar view parameters from request query params."""
        calendar_view = request.query_params.get("calendar_view", "month")
        date_str = request.query_params.get("date", "")

        # Parse date or use today
        try:
            current_date = date.fromisoformat(date_str) if date_str else date.today()
        except ValueError:
            current_date = date.today()

        return CalendarParams(calendar_view=calendar_view, current_date=current_date)

    # Error rendering moved to components.error_components.ErrorComponents

    # ========================================================================
    # ERROR HANDLING
    # ========================================================================

    def render_safe_error_response(
        user_message: str,
        error_context: Any,
        logger_instance,
        log_extra: dict[str, Any],
        status_code: int = 500,
    ) -> Response:
        """
        Return sanitized error to client, log detailed error server-side.

        Args:
            user_message: Safe message for client (e.g., "Failed to update habit")
            error_context: Detailed error (logged but NOT sent to client)
            logger_instance: Logger instance for structured logging
            log_extra: Additional context for logs (user_uid, entity_uid, etc.)
            status_code: HTTP status code

        Returns:
            Response with sanitized message
        """
        # Log detailed error server-side
        logger_instance.error(
            user_message,
            extra={
                {
                    **log_extra,
                    "error_type": type(error_context).__name__,
                    "error_detail": str(error_context),
                }
            },
        )

        # Return safe message to client
        return Response(user_message, status_code=status_code)

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

    # ========================================================================
    # PURE COMPUTATION HELPERS (Testable without mocks)
    # ========================================================================

    def validate_habit_form_data(form_data: dict[str, Any]) -> Result[None]:
        """
        Validate habit form data early.

        Pure function: returns clear error messages for UI.

        Args:
            form_data: Raw form data from request

        Returns:
            Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
        """
        # Required fields
        title = form_data.get("title", "").strip()
        if not title:
            return Result.fail(Errors.validation("Habit title is required"))

        if len(title) > 200:
            return Result.fail(Errors.validation("Habit title must be 200 characters or less"))

        # Frequency validation
        frequency_str = form_data.get("frequency", "")
        if frequency_str:
            try:
                frequency = int(frequency_str)
                if frequency < 1:
                    return Result.fail(Errors.validation("Frequency must be at least 1"))
                if frequency > 365:
                    return Result.fail(Errors.validation("Frequency must be 365 or less"))
            except ValueError:
                return Result.fail(Errors.validation("Invalid frequency"))

        return Result.ok(None)

    def compute_habit_stats(habits: list[Any]) -> dict[str, int]:
        """Calculate habit statistics.

        Pure function: testable without database or async.

        Args:
            habits: List of habit entities

        Returns:
            Stats dict with counts
        """
        return {
            "total": len(habits),
            "active": sum(1 for h in habits if str(h.status.value).lower() == "active"),
            "streaks": sum(1 for h in habits if h.current_streak > 0),
        }

    def apply_habit_filters(
        habits: list[Any],
        status_filter: str = "active",
    ) -> list[Any]:
        """Apply filter criteria to habit list.

        Pure function: testable without database or async.

        Args:
            habits: List of habit entities
            status_filter: Status filter (active, paused, completed, all)

        Returns:
            Filtered list of habits
        """
        # Filter by status
        if status_filter == "active":
            return [h for h in habits if str(h.status.value).lower() == "active"]
        elif status_filter == "paused":
            return [h for h in habits if str(h.status.value).lower() == "paused"]
        elif status_filter == "completed":
            return [h for h in habits if str(h.status.value).lower() == "completed"]
        # "all" - no filtering
        return habits

    def apply_habit_sort(habits: list[Any], sort_by: str = "streak") -> list[Any]:
        """Sort habits by specified field.

        Pure function: testable without database or async.

        Args:
            habits: List of habit entities
            sort_by: Sort field (streak, name, created_at, frequency)

        Returns:
            Sorted list of habits
        """
        if sort_by == "streak":
            return sorted(habits, key=get_current_streak, reverse=True)
        elif sort_by == "name":
            return sorted(habits, key=get_name_lower)
        elif sort_by == "created_at":
            return sorted(habits, key=get_created_at_attr, reverse=True)
        elif sort_by == "frequency":
            return sorted(habits, key=get_recurrence_pattern)
        else:
            # Default: streak
            return sorted(habits, key=get_current_streak, reverse=True)

    async def get_filtered_habits(
        user_uid: str,
        status_filter: str = "active",
        sort_by: str = "streak",
    ) -> Result[tuple[list[Any], dict[str, int]]]:
        """Get filtered and sorted habits with stats.

        Orchestrates: fetch (I/O) → stats → filter → sort.
        Pure computation delegated to testable helper functions.
        """
        try:
            # I/O: Fetch all habits
            habits_result = await get_all_habits(user_uid)
            if habits_result.is_error:
                return Result.fail(habits_result)

            habits = habits_result.value

            # Computation: Calculate stats BEFORE filtering
            stats = compute_habit_stats(habits)

            # Computation: Apply filters
            filtered_habits = apply_habit_filters(habits, status_filter)

            # Computation: Apply sort
            sorted_habits = apply_habit_sort(filtered_habits, sort_by)

            return Result.ok((sorted_habits, stats))
        except Exception as e:
            logger.error(
                "Error filtering habits",
                extra={
                    "user_uid": user_uid,
                    "status_filter": status_filter,
                    "sort_by": sort_by,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to filter habits: {e}"))

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
        filtered_result = await get_filtered_habits(user_uid, filters.status, filters.sort_by)
        categories_result = await get_categories()

        # CHECK FOR ERRORS
        if filtered_result.is_error:
            error_content = Div(
                HabitsViewComponents.render_view_tabs(active_view=view),
                ErrorComponents.render_error_banner("Failed to load habits"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )
            return await create_habits_page(error_content, request=request)

        if categories_result.is_error:
            error_content = Div(
                HabitsViewComponents.render_view_tabs(active_view=view),
                ErrorComponents.render_error_banner("Failed to load categories"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )
            return await create_habits_page(error_content, request=request)

        # Extract values
        habits, stats = filtered_result.value
        categories = categories_result.value

        # Render the appropriate view content
        if view == "create":
            view_content = HabitsViewComponents.render_create_view(
                categories=categories,
                user_uid=user_uid,
            )
        elif view == "calendar":
            all_habits_result = await get_all_habits(user_uid)

            # Check for errors
            if all_habits_result.is_error:
                view_content = ErrorComponents.render_error_banner(
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
                user_uid=user_uid,
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

        filtered_result = await get_filtered_habits(user_uid, filters.status, filters.sort_by)
        categories_result = await get_categories()

        # Handle errors (return banner directly for HTMX swap)
        if filtered_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load habits")

        if categories_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load categories")

        habits, stats = filtered_result.value
        categories = categories_result.value

        filters_dict: ActivityFilterSpec = {"status": filters.status, "sort_by": filters.sort_by}
        return HabitsViewComponents.render_list_view(
            habits=habits,
            filters=filters_dict,
            stats=stats,
            categories=categories,
            user_uid=user_uid,
        )

    @rt("/habits/view/create")
    async def habits_view_create(request) -> Any:
        """HTMX fragment for create view."""
        user_uid = require_authenticated_user(request)
        categories_result = await get_categories()

        # Handle errors
        if categories_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load categories")

        return HabitsViewComponents.render_create_view(
            categories=categories_result.value,
            user_uid=user_uid,
        )

    @rt("/habits/view/calendar")
    async def habits_view_calendar(request) -> Any:
        """HTMX fragment for calendar view."""
        user_uid = require_authenticated_user(request)
        calendar_params = parse_calendar_params(request)

        habits_result = await get_all_habits(user_uid)

        # Handle errors
        if habits_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load calendar")

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

        filtered_result = await get_filtered_habits(user_uid, filters.status, filters.sort_by)

        # Handle errors
        if filtered_result.is_error:
            return ErrorComponents.render_error_banner("Failed to load habits")

        habits, _stats = filtered_result.value

        # Return just the habit items
        habit_items = [HabitsViewComponents._render_habit_item(habit, user_uid) for habit in habits]

        return Div(
            *habit_items
            if habit_items
            else [P("No habits found.", cls="text-gray-500 text-center py-8")],
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
        from core.models.enums.ku_enums import HabitCategory
        from core.models.habit.habit_request import HabitCreateRequest

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
        result = await get_filtered_habits(user_uid, "active", "streak")
        if result.is_error:
            habits, stats = [], {}
        else:
            habits, stats = result.value
        categories = await get_categories()
        return HabitsViewComponents.render_list_view(
            habits=habits,
            filters={},
            stats=stats,
            categories=categories,
            user_uid=user_uid,
        )

    async def render_habit_add_another_view(user_uid: str) -> Any:
        """Render create view for add-another flow."""
        categories = await get_categories()
        return HabitsViewComponents.render_create_view(categories=categories, user_uid=user_uid)

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
    # ATOMIC HABITS WIZARD ROUTES (Phase 1 MVP)
    # ========================================================================

    @rt("/habits/wizard/step1")
    async def wizard_step1(request) -> Any:
        """Wizard Step 1: Basic habit + identity"""
        form_data = await request.form()
        return AtomicHabitsComponents.render_habit_creation_wizard(
            step=1, form_data=dict(form_data)
        )

    @rt("/habits/wizard/step2")
    async def wizard_step2(request) -> Any:
        """Wizard Step 2: Behavior design (cue-routine-reward)"""
        form_data = await request.form()
        return AtomicHabitsComponents.render_habit_creation_wizard(
            step=2, form_data=dict(form_data)
        )

    @rt("/habits/wizard/step3")
    async def wizard_step3(request) -> Any:
        """Wizard Step 3: Link to goals with essentiality"""
        form_data = await request.form()
        return AtomicHabitsComponents.render_habit_creation_wizard(
            step=3, form_data=dict(form_data)
        )

    @rt("/habits/wizard/step4")
    async def wizard_step4(request) -> Any:
        """Wizard Step 4: Review - just show the review, don't create yet"""
        form_data = await request.form()
        return AtomicHabitsComponents.render_habit_creation_wizard(
            step=4, form_data=dict(form_data)
        )

    @rt("/api/habits/create-with-identity")
    async def create_habit_with_identity(request) -> Any:
        """Create habit from wizard with identity and goal linking"""
        from core.models.habit.habit_request import HabitCreateRequest

        form_data = await request.form()
        wizard_data = dict(form_data)

        # Get user_uid from session or form data
        user_uid = wizard_data.get("user_uid", "")
        if not user_uid:
            # Try to get from request session if available
            user_uid = getattr(request, "user_uid", "default_user")

        # Build HabitCreateRequest from wizard data
        create_request = HabitCreateRequest(
            name=wizard_data.get("name", ""),
            description=wizard_data.get("description", "") or None,
            cue=wizard_data.get("cue", "") or None,
            routine=wizard_data.get("routine", "") or None,
            reward=wizard_data.get("reward", "") or None,
            reinforces_identity=wizard_data.get("identity", "") or None,
            is_identity_habit=bool(wizard_data.get("identity")),
        )

        # Create habit via service
        result = await habits_service.create_habit(create_request, user_uid)

        if result.is_error:
            logger.error(f"Failed to create habit: {result.error}")
            return Div(
                Card(
                    H2("Error Creating Habit", cls="text-xl font-bold text-red-600 mb-4"),
                    P(f"Failed to create habit: {result.error}", cls="text-gray-700 mb-4"),
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

        # Link to goals with essentiality if goals_service is available
        if goals_service:
            # Extract goal essentiality from form data
            # Form fields like: goal_essentiality_goal_123 = "essential"
            goal_essentiality = {}
            for key, value in wizard_data.items():
                if key.startswith("goal_essentiality_"):
                    goal_uid = key.replace("goal_essentiality_", "")
                    goal_essentiality[goal_uid] = value

            # Link habit to each goal with essentiality
            for goal_uid, essentiality in goal_essentiality.items():
                try:
                    # Create relationship with essentiality property
                    await goals_service.link_goal_to_habit(
                        goal_uid=goal_uid, habit_uid=habit.uid, contribution_type=essentiality
                    )
                except Exception as e:
                    logger.warning(f"Failed to link habit to goal {goal_uid}: {e}")

        # Return success message and redirect to habits dashboard
        return Div(
            Card(
                H2("✅ Habit Created!", cls="text-2xl font-bold text-green-600 mb-4 text-center"),
                P(
                    f"Successfully created: {habit.title}",
                    cls="text-lg text-gray-700 mb-2 text-center",
                ),
                (
                    Div(
                        P(
                            f'"{habit.reinforces_identity}"',
                            cls="italic text-purple-700 text-center",
                        ),
                        P(
                            "Every completion is a vote for this identity!",
                            cls="text-sm text-gray-600 text-center mt-2",
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
        from datetime import date

        user_uid = require_authenticated_user(request)

        # Ownership verification before mutation
        habit_result = await habits_service.core.verify_ownership(uid, user_uid)
        if habit_result.is_error:
            logger.warning(f"Habit access denied or not found: {uid} for user {user_uid}")
            return Div(P("Error: Could not find habit", cls="text-red-600"), cls="p-4")

        habit = habit_result.value

        # Store old values for delta calculation

        # Update completion tracking
        completion_date = date.today()
        updates = {
            "total_completions": habit.total_completions + 1,
            "last_completed": completion_date,
        }

        # Update streak
        if habit.last_completed:
            days_since = (completion_date - habit.last_completed).days
            if days_since == 1:
                updates["current_streak"] = habit.current_streak + 1
            elif days_since > 1:
                updates["current_streak"] = 1  # Streak broken, restart
        else:
            updates["current_streak"] = 1  # First completion

        current_streak: int = updates.get("current_streak", 1)  # type: ignore[assignment]
        updates["best_streak"] = max(current_streak, habit.best_streak)

        # Cast identity vote if applicable
        if habit.is_identity_habit:
            updates["identity_votes_cast"] = habit.identity_votes_cast + 1

        # Update habit via service
        update_result = await habits_service.update(uid, updates)
        if update_result.is_error:
            logger.error(f"Failed to update habit: {update_result.error}")
            return Div(P("Error: Could not complete habit", cls="text-red-600"), cls="p-4")

        updated_habit = update_result.value

        # Calculate goal impacts if goals_service available
        goal_impacts = []
        linked_goal_uids: list[str] = getattr(habit, "linked_goal_uids", [])
        if goals_service and linked_goal_uids:
            for goal_uid in linked_goal_uids:
                try:
                    goal_result = await goals_service.get_goal(goal_uid)
                    if goal_result.is_error:
                        continue

                    goal = goal_result.value
                    if goal is None:
                        continue

                    # Store old values
                    old_strength = getattr(goal, "cached_system_strength", None)
                    if old_strength is None:
                        try:
                            old_strength = goal.calculate_system_strength()
                        except (AttributeError, ValueError, TypeError) as e:
                            logger.warning(
                                f"Failed to calculate system strength for {goal_uid}: {e}"
                            )
                            old_strength = 0

                    # Recalculate system strength
                    try:
                        new_strength = goal.calculate_system_strength()
                        strength_delta = (new_strength - old_strength) * 100
                    except Exception as e:
                        logger.warning(f"Failed to calculate system strength for {goal_uid}: {e}")
                        strength_delta = 0

                    # Calculate velocity change (simplified - just show positive impact)
                    velocity_delta = 1  # Each completion adds to velocity

                    goal_impacts.append(
                        {
                            "title": goal.title,
                            "system_strength_delta": round(strength_delta, 1),
                            "velocity_delta": velocity_delta,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to calculate impact for goal {goal_uid}: {e}")

        # Render celebration modal
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
            P("Please use the Complete button to mark habit as done", cls="text-gray-600 p-4")
        )

    # ========================================================================
    # PHASE 2: INTELLIGENCE ROUTES
    # ========================================================================

    @rt("/habits/{uid}/patterns")
    async def habit_patterns_view(request, uid: str) -> Any:
        """Pattern recognition for a habit"""
        user_uid = require_authenticated_user(request)

        # Ownership verification - returns NotFound if user doesn't own this habit
        habit_result = await habits_service.core.verify_ownership(uid, user_uid)

        if habit_result.is_error:
            logger.warning(f"Habit access denied or not found: {uid} for user {user_uid}")
            return Div(P("Error: Could not find habit", cls="text-red-600"), cls="p-4")

        habit = habit_result.value

        # Get complete Atomic Habits analysis
        analysis = habit.get_atomic_habits_analysis()

        # Transform analysis into pattern format for rendering
        success_patterns = []
        failure_patterns = []

        # Extract success patterns from analysis

        # Pattern 1: Identity-based success
        if analysis["identity"]["is_identity_based"]:
            identity_strength = analysis["identity"]["identity_strength"]
            if identity_strength > 0.5:
                success_patterns.append(
                    {
                        "pattern": f"Identity reinforcement: '{analysis['identity']['reinforces_identity']}'",
                        "confidence": identity_strength,
                        "recommendation": f"Keep reinforcing this identity - {analysis['identity']['votes_to_establishment']} more completions to full establishment",
                    }
                )

        # Pattern 2: Behavioral design completeness
        design_score = analysis["behavioral_design"]["design_completeness"]
        if design_score >= 0.66:  # Has at least 2 of 3 elements
            success_patterns.append(
                {
                    "pattern": f"Strong habit design ({int(design_score * 100)}% complete)",
                    "confidence": design_score,
                    "recommendation": "Clear cue-routine-reward loop is working",
                }
            )

        # Pattern 3: Streak momentum
        if (
            analysis["habit_quality"]["is_on_streak"]
            and analysis["habit_quality"]["current_streak"] > 3
        ):
            streak_confidence = min(0.9, 0.5 + (analysis["habit_quality"]["current_streak"] / 30))
            success_patterns.append(
                {
                    "pattern": f"Momentum building: {analysis['habit_quality']['current_streak']}-day streak",
                    "confidence": streak_confidence,
                    "recommendation": "Momentum matters - maintain the streak!",
                }
            )

        # Pattern 4: Success rate
        if analysis["habit_quality"]["success_rate"] > 0.6:
            success_patterns.append(
                {
                    "pattern": f"High success rate: {int(analysis['habit_quality']['success_rate'] * 100)}%",
                    "confidence": analysis["habit_quality"]["success_rate"],
                    "recommendation": "Current approach is working - keep it up",
                }
            )

        # Pattern 5: System integration
        if analysis["system_contribution"]["part_of_system"]:
            consistency = analysis["system_contribution"]["consistency_score"]
            success_patterns.append(
                {
                    "pattern": f"Part of goal system ({analysis['system_contribution']['supports_goal_count']} goals)",
                    "confidence": consistency,
                    "recommendation": "Systems-based approach is effective",
                }
            )

        # Extract failure patterns from analysis

        # Failure 1: Low success rate
        if analysis["habit_quality"]["success_rate"] < 0.5:
            failure_patterns.append(
                {
                    "pattern": f"Low success rate: {int(analysis['habit_quality']['success_rate'] * 100)}%",
                    "confidence": 1.0 - analysis["habit_quality"]["success_rate"],
                    "recommendation": "Consider making habit easier or more rewarding",
                }
            )

        # Failure 2: Broken streak
        if (
            not analysis["habit_quality"]["is_on_streak"]
            and analysis["habit_quality"]["best_streak"] > 0
        ):
            failure_patterns.append(
                {
                    "pattern": f"Streak broken (previous best: {analysis['habit_quality']['best_streak']} days)",
                    "confidence": 0.75,
                    "recommendation": f"Rebuild streak - you've achieved {analysis['habit_quality']['best_streak']} days before",
                }
            )

        # Failure 3: Incomplete design
        if design_score < 0.66:
            missing_elements = []
            if not analysis["behavioral_design"]["has_cue"]:
                missing_elements.append("cue")
            if not analysis["behavioral_design"]["has_reward"]:
                missing_elements.append("reward")

            if missing_elements:
                failure_patterns.append(
                    {
                        "pattern": f"Incomplete habit design (missing: {', '.join(missing_elements)})",
                        "confidence": 1.0 - design_score,
                        "recommendation": f"Define clear {missing_elements[0]} to strengthen habit loop",
                    }
                )

        # Failure 4: No goal system
        if not analysis["system_contribution"]["part_of_system"]:
            failure_patterns.append(
                {
                    "pattern": "Habit not linked to goals (no systems thinking)",
                    "confidence": 0.70,
                    "recommendation": "Link this habit to a goal to create a system",
                }
            )

        # Build pattern data for rendering
        pattern_data = {
            "name": habit.title,
            "total_completions": analysis["habit_quality"]["total_completions"],
            "success_patterns": success_patterns,
            "failure_patterns": failure_patterns,
        }

        return AtomicHabitsIntelligence.render_pattern_recognition(pattern_data)

    @rt("/goals/{uid}/system-health")
    async def goal_system_health_view(_request, uid: str) -> Any:
        """System health diagnostics for a goal"""
        # Fetch goal from backend
        if not goals_service:
            return Div(P("Goals service not available", cls="text-red-600"), cls="p-4")

        goal_result = await goals_service.get_goal(uid)

        if goal_result.is_error:
            logger.error(f"Failed to get goal {uid}: {goal_result.error}")
            return Div(P("Error: Could not find goal", cls="text-red-600"), cls="p-4")

        goal = goal_result.value
        if goal is None:
            return Div(P("Goal not found", cls="text-red-600"), cls="p-4")

        # Fetch all habits for this goal and build success rate map
        # NOTE: get_goal_habits returns supporting habits; essentiality grouping
        # requires GoalRelationships.fetch() which is not available through the facade.
        all_habit_uids_result = await goals_service.get_goal_habits(goal.uid)
        all_habit_uids: list[str] = (
            all_habit_uids_result.value if all_habit_uids_result.is_ok else []
        )
        habit_success_rates: dict[str, float] = {}

        # Build habit breakdown with details
        habit_breakdown = []

        for habit_uid in all_habit_uids:
            try:
                habit_result = await habits_service.get_habit(habit_uid)
                if habit_result.is_error:
                    logger.warning(f"Failed to fetch habit {habit_uid}: {habit_result.error}")
                    continue

                habit = habit_result.value

                # Store success rate for diagnosis
                habit_success_rates[habit_uid] = habit.success_rate

                # Build habit detail for breakdown
                habit_breakdown.append(
                    {
                        "name": habit.title,
                        "essentiality": "supporting",
                        "consistency": habit.calculate_consistency_score(),
                        "impact": habit.predict_goal_impact(),
                    }
                )
            except Exception as e:
                logger.warning(f"Error processing habit {habit_uid}: {e}")

        # Get system health diagnosis
        diagnosis = goal.diagnose_system_health(habit_success_rates)

        # Build system health data for rendering
        system_health = {
            "goal_title": goal.title,
            "system_strength": diagnosis["system_strength"],
            "diagnosis": diagnosis["diagnosis"],
            "warnings": diagnosis["warnings"],
            "recommendations": diagnosis["recommendations"],
            "habit_breakdown": habit_breakdown,
            "system_exists": diagnosis.get("system_exists", True),
        }

        return AtomicHabitsIntelligence.render_system_health_diagnostics(system_health)

    @rt("/goals/{uid}/velocity")
    async def goal_velocity_view(_request, uid: str) -> Any:
        """Velocity tracking for a goal"""
        # Fetch goal from backend
        if not goals_service:
            return Div(P("Goals service not available", cls="text-red-600"), cls="p-4")

        goal_result = await goals_service.get_goal(uid)

        if goal_result.is_error:
            logger.error(f"Failed to get goal {uid}: {goal_result.error}")
            return Div(P("Error: Could not find goal", cls="text-red-600"), cls="p-4")

        goal = goal_result.value
        if goal is None:
            return Div(P("Goal not found", cls="text-red-600"), cls="p-4")

        # Fetch all habits and build completion counts
        all_habit_uids_result = await goals_service.get_goal_habits(goal.uid)
        all_habit_uids: list[str] = (
            all_habit_uids_result.value if all_habit_uids_result.is_ok else []
        )
        habit_completion_counts: dict[str, int] = {}

        # Build weighted breakdown by essentiality
        weighted_breakdown = {"essential": 0, "critical": 0, "supporting": 0, "optional": 0}

        for habit_uid in all_habit_uids:
            try:
                habit_result = await habits_service.get_habit(habit_uid)
                if habit_result.is_error:
                    logger.warning(f"Failed to fetch habit {habit_uid}: {habit_result.error}")
                    continue

                habit = habit_result.value

                # Store total completions for velocity calculation
                habit_completion_counts[habit_uid] = habit.total_completions

                # All habits returned by get_goal_habits are supporting
                weighted_breakdown["supporting"] += habit.total_completions

            except Exception as e:
                logger.warning(f"Error processing habit {habit_uid}: {e}")

        # Calculate current velocity
        current_velocity = goal.calculate_habit_velocity(habit_completion_counts)

        # Calculate total weighted completions
        total_weighted_completions = sum(weighted_breakdown.values())

        # Generate simplified velocity trend (last 4 weeks estimate)
        # NOTE: This is a simplified version. Full implementation would require
        # historical completion tracking in the database.
        velocity_trend = []

        if current_velocity > 0:
            # Estimate weekly progression assuming linear growth to current velocity
            for i in range(1, 5):
                week_velocity = (current_velocity / 4) * i
                velocity_trend.append({"week": f"Week {i}", "velocity": round(week_velocity, 1)})
        else:
            # No velocity data - all zeros
            velocity_trend.extend([{"week": f"Week {i}", "velocity": 0.0} for i in range(1, 5)])

        # Determine trend
        last_velocity: float = float(velocity_trend[-1]["velocity"]) if velocity_trend else 0.0
        first_velocity: float = float(velocity_trend[0]["velocity"]) if velocity_trend else 0.0
        if len(velocity_trend) > 1 and last_velocity > 0:
            if last_velocity > first_velocity:
                trend = "increasing"
            elif last_velocity < first_velocity:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"

        # Build velocity data for rendering
        velocity_data = {
            "goal_title": goal.title,
            "current_velocity": current_velocity,
            "trend": trend,
            "velocity_trend": velocity_trend,
            "weighted_breakdown": weighted_breakdown,
            "total_weighted_completions": int(total_weighted_completions),
        }

        return AtomicHabitsIntelligence.render_velocity_tracking(velocity_data)

    @rt("/goals/{uid}/impact")
    async def goal_impact_view(_request, uid: str) -> Any:
        """Impact analysis for a goal"""
        # Fetch goal from backend
        if not goals_service:
            return Div(P("Goals service not available", cls="text-red-600"), cls="p-4")

        goal_result = await goals_service.get_goal(uid)

        if goal_result.is_error:
            logger.error(f"Failed to get goal {uid}: {goal_result.error}")
            return Div(P("Error: Could not find goal", cls="text-red-600"), cls="p-4")

        goal = goal_result.value
        if goal is None:
            return Div(P("Goal not found", cls="text-red-600"), cls="p-4")

        # Fetch all habits and build completion counts for velocity
        all_habit_uids_result = await goals_service.get_goal_habits(goal.uid)
        all_habit_uids: list[str] = (
            all_habit_uids_result.value if all_habit_uids_result.is_ok else []
        )
        habit_completion_counts: dict[str, int] = {}
        habit_success_rates: dict[str, float] = {}

        # Build habit impacts list
        habit_impacts = []

        for habit_uid in all_habit_uids:
            try:
                habit_result = await habits_service.get_habit(habit_uid)
                if habit_result.is_error:
                    logger.warning(f"Failed to fetch habit {habit_uid}: {habit_result.error}")
                    continue

                habit = habit_result.value

                # Store for velocity calculation
                habit_completion_counts[habit_uid] = habit.total_completions
                habit_success_rates[habit_uid] = habit.success_rate

                # Get habit impact prediction
                impact_score = habit.predict_goal_impact()

                # Get consistency
                consistency = habit.calculate_consistency_score()

                # Build habit impact detail
                habit_impacts.append(
                    {
                        "name": habit.title,
                        "essentiality": "supporting",
                        "impact_score": impact_score,
                        "consistency": consistency,
                    }
                )

            except Exception as e:
                logger.warning(f"Error processing habit {habit_uid}: {e}")

        # Sort habits by impact score (highest first)
        habit_impacts.sort(key=itemgetter("impact_score"), reverse=True)

        # Calculate achievement probability
        # Formula: 60% system strength + 40% velocity (normalized)
        system_strength = goal.calculate_system_strength(habit_success_rates=habit_success_rates)
        velocity = goal.calculate_habit_velocity(habit_completion_counts)

        # Normalize velocity to 0-1 scale (150 = excellent velocity = 1.0)
        normalized_velocity = min(velocity / 150.0, 1.0)

        # Achievement probability (0-1 scale, displayed as percentage)
        achievement_probability = (system_strength * 0.6) + (normalized_velocity * 0.4)

        # Calculate overall impact (average of all habit impacts)
        if habit_impacts:
            overall_impact = sum(h["impact_score"] for h in habit_impacts) / len(habit_impacts)
        else:
            overall_impact = 0.0

        # Build impact data for rendering
        impact_data = {
            "goal_title": goal.title,
            "achievement_probability": achievement_probability,  # 0-1 scale
            "overall_impact": overall_impact,  # 0-1 scale
            "habits": habit_impacts,
        }

        return AtomicHabitsIntelligence.render_goal_impact_analysis(impact_data)

    # ========================================================================
    # PHASE 3: ACHIEVEMENT BADGE ROUTES
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
    # PHASE 3.3: ADVANCED ANALYTICS ROUTES
    # ========================================================================

    @rt("/habits/analytics")
    async def habits_analytics_dashboard(request) -> Any:
        """
        Advanced analytics dashboard.
        Requires authentication.
        """
        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

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

        return AtomicHabitsAnalytics.render_analytics_dashboard(
            user_uid=user_uid, date_range=(start_date, end_date)
        )

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
    # PHASE 3.4: MOBILE-OPTIMIZED ROUTES
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
            if habit.status == KuStatus.ACTIVE
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
            return P("Habit not found", cls="text-center text-gray-500 py-8")

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
            else P("No habits found for this category", cls="text-center text-gray-500 py-8")
        )

    @rt("/habits/{uid}/details")
    async def habit_details_modal(_request, uid: str) -> Any:
        """Habit details modal fragment"""
        return Card(
            CardBody(
                H2("📊 Habit Details", cls="text-xl font-bold mb-4"),
                P(f"Detailed view for habit {uid} will be implemented here", cls="text-gray-500"),
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
                    P("Habit not found", cls="text-gray-500"),
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
            "name": form_data.get("name", ""),
            "description": form_data.get("description", ""),
            "cue": form_data.get("cue", ""),
            "routine": form_data.get("routine", ""),
            "reward": form_data.get("reward", ""),
            "status": form_data.get("status", "active"),
        }

        # Update via service
        result = await habits_service.update(uid, updates)

        if result.is_error:
            logger.error(f"Failed to update habit: {result.error}")
            return Card(
                CardBody(
                    H2("Error", cls="text-xl font-bold text-red-600 mb-4"),
                    P(f"Failed to save: {result.error}", cls="text-gray-500"),
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
                    P(f"Could not load habit: {result.error}", cls="text-gray-500"),
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
        status = str(getattr(habit, "status", "active")).lower().replace("habitstatus.", "")

        from fasthtml.common import Form, Input, Label, Option, Select, Textarea

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
                            cls="input input-bordered w-full",
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
                            cls="textarea textarea-bordered w-full",
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
                            cls="input input-bordered w-full",
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
                            cls="input input-bordered w-full",
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
                            cls="input input-bordered w-full",
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
                            cls="select select-bordered w-full",
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
    # HABIT DETAIL PAGE (Phase 5)
    # ========================================================================

    @rt("/habits/{uid}")
    async def habit_detail_view(request: Any, uid: str) -> Any:
        """
        Habit detail view with full context and relationships.

        Phase 5: Shows habit details plus lateral relationships visualization.
        """
        user_uid = require_authenticated_user(request)

        # Fetch habit with ownership verification
        result = await habits_service.get_for_user(uid, user_uid)

        if result.is_error:
            logger.error(f"Failed to get habit {uid}: {result.error}")
            return await BasePage(
                content=Card(
                    H2("Habit Not Found", cls="text-xl font-bold text-error mb-4"),
                    P(f"Could not find habit: {uid}", cls="text-base-content/70"),
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
                P(habit.description or "No description provided", cls="text-base-content/70 mb-4"),
                # Status and Frequency badges
                Div(
                    Span(f"Status: {habit.status.value}", cls="badge badge-info mr-2"),
                    Span(
                        f"Frequency: {habit.frequency.value if habit.frequency else 'Not set'}",
                        cls="badge badge-success mr-2",
                    ),
                    Span(f"Streak: {habit.current_streak or 0} days", cls="badge badge-warning"),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-6 mb-4",
            ),
            # Details Card
            Card(
                H2("📋 Habit Details", cls="text-xl font-semibold mb-4"),
                Div(
                    # Why Important
                    (
                        Div(
                            P(
                                "Why Important:",
                                cls="text-sm font-semibold text-base-content/70 mb-1",
                            ),
                            P(habit.why_important or "Not specified", cls="text-base-content mb-3"),
                            cls="mb-4",
                        )
                        if habit.why_important
                        else Div()
                    ),
                    # Cue and Response
                    (
                        Div(
                            P("Cue:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                            P(habit.cue or "Not specified", cls="text-base-content mb-3"),
                            cls="mb-4",
                        )
                        if habit.cue
                        else Div()
                    ),
                    # Created Date
                    Div(
                        P("Created:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                        P(str(habit.created_at)[:10], cls="text-base-content/60 text-sm"),
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
            # Phase 5: Lateral Relationships Section
            EntityRelationshipsSection(
                entity_uid=habit.uid,
                entity_type="habits",
            ),
            cls="container mx-auto p-6 max-w-4xl",
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
