"""
Goals UI Routes - Three-View Standalone Interface
=================================================

Three-view goal management UI with List, Create, and Calendar views.
Uses standalone layout (no sidebar) matching Tasks domain pattern.

Routes:
- GET /goals - Main dashboard with three views (standalone, no drawer)
- GET /goals/view/list - HTMX fragment for list view
- GET /goals/view/create - HTMX fragment for create view
- GET /goals/view/calendar - HTMX fragment for calendar view
- GET /goals/list-fragment - HTMX filtered list (for filter updates)
- POST /goals/quick-add - Create goal via form
"""

__version__ = "2.0"

import contextlib
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

from fasthtml.common import H1, H2, H3, Div, Form, Option, P, Script, Span
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.route_factories import QuickAddConfig, QuickAddRouteFactory
from adapters.inbound.ui_helpers import CalendarParams, parse_calendar_params, render_safe_error_response
from core.models.enums import Priority
from core.models.goal.goal_request import GoalCreateRequest
from core.ports.query_types import ActivityFilterSpec
from core.services.goals_service import GoalsService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import (
    get_created_at_attr,
    get_current_value,
    make_priority_string_getter,
)
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.feedback import Progress
from ui.forms import Input, Label, Select
from ui.layout import Size
from ui.goals.layout import create_goals_page
from ui.goals.views import GoalsViewComponents
from ui.habits.atomic_components import AtomicHabitsComponents
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.entity_dashboard import SharedUIComponents
from ui.patterns.error_banner import render_error_banner
from ui.patterns.form_generator import FormGenerator
from ui.patterns.relationships import EntityRelationshipsSection
from ui.tokens import Container, Spacing

logger = get_logger("skuel.routes.goals.ui")


# RouteDecorator and Request imported from adapters.inbound.fasthtml_types

# ============================================================================
# UI COMPONENT LIBRARY - Reusable goal components
# ============================================================================


class GoalUIComponents:
    """Centralized goal UI components - no more inline composition"""

    @staticmethod
    def render_goals_content(goals=None, stats=None, categories=None) -> Any:
        """
        Goals dashboard content (without page wrapper).

        Used by create_profile_page() for Profile Hub integration.
        """
        goals = goals or []
        stats = stats or {}
        categories = categories or ["career", "health", "learning", "personal", "financial"]

        # Transform stats to shared format
        stats_formatted = {
            "total": {
                "label": "Total Goals",
                "value": stats.get("total_goals", 0),
                "color": "blue",
            },
            "active": {
                "label": "Active Goals",
                "value": stats.get("active_goals", 0),
                "color": "green",
            },
            "completed": {
                "label": "Completed",
                "value": stats.get("completed_goals", 0),
                "color": "purple",
            },
            "success_rate": {
                "label": "Success Rate",
                "value": f"{stats.get('completion_rate', 0)}%",
                "color": "orange",
            },
        }

        # Define quick actions
        quick_actions = [
            {
                "label": "New Goal",
                "hx_get": "/goals/view/create",
                "hx_target": "#modal",
                "class": "btn-primary",
            },
        ]

        # Render content
        return Div(
            H1("Goals Dashboard", cls="text-3xl font-bold mb-6"),
            SharedUIComponents.render_stats_cards(stats_formatted),
            SharedUIComponents.render_quick_actions(quick_actions),
            SharedUIComponents.render_category_filter(categories, "/goals/filter"),
            Div(
                *[GoalUIComponents.render_goal_card(goal) for goal in goals],
                cls="space-y-3",
                id="goals-list",
            )
            if goals
            else P(
                "No goals yet. Create one to get started!",
                cls="text-base-content/60 text-center py-8",
            ),
            Div(id="modal"),  # Modal container for HTMX
        )

    # NOTE: render_goal_stats(), render_action_buttons(), render_active_goals(),
    # and render_all_goals() have been REMOVED.
    # These are now handled by SharedUIComponents.render_entity_dashboard().
    # Removed ~118 lines of duplicate code.

    @staticmethod
    def render_goal_card(goal, show_progress_button=False) -> Any:
        """
        Individual goal card component.

        Handles both dict and dataclass goal instances.
        """
        # Extract data from either dict or dataclass
        if isinstance(goal, dict):
            uid = goal.get("uid", "")
            title = goal.get("title", "Untitled Goal")
            description = goal.get("description", "")
            category = goal.get("category", "general")
            priority = goal.get("priority", "medium")
            status = goal.get("status", "active")
            progress = goal.get("progress", 0)
            target_date = goal.get("target_date", "")
        else:
            uid = goal.uid
            title = goal.title
            description = getattr(goal, "description", "")
            category = getattr(goal, "category", "general")
            priority = getattr(goal, "priority", "medium")
            status = goal.status
            progress = getattr(goal, "current_value", 0)
            target_date = getattr(goal, "target_date", "")

        # Determine border color based on status
        border_color = "border-blue-500" if str(status) == "active" else "border-base-300"

        # Build card content
        card_content = [
            # Title and status
            Div(
                H3(title, cls="text-lg font-semibold"),
                Span(str(status).title(), cls="badge badge-primary"),
                cls="flex justify-between items-start mb-2",
            ),
            # Description
            P(description, cls="text-sm text-base-content/70 mb-3") if description else "",
            # Progress bar
            Div(
                P(f"Progress: {progress}%", cls="text-sm text-base-content/70 mb-1"),
                Div(
                    Div(
                        cls="h-2 bg-primary rounded-full transition-all",
                        style=f"width: {progress}%",
                    ),
                    cls="w-full bg-base-300 rounded-full h-2",
                ),
                cls="mb-3",
            )
            if progress > 0
            else "",
            # Metadata badges
            Div(
                Span(category.title(), cls="badge badge-outline badge-sm") if category else "",
                Span(priority.title(), cls="badge badge-ghost badge-sm") if priority else "",
                Span(f"📅 {target_date}", cls="text-xs text-base-content/60")
                if target_date
                else "",
                cls="flex gap-2 items-center mb-3",
            ),
        ]

        # MVP: Add system strength meter if goal has habit system
        # Check for system strength data
        system_strength = (
            goal.get("system_strength")
            if isinstance(goal, dict)
            else getattr(goal, "system_strength", None)
        )
        if system_strength is not None and system_strength > 0:
            habit_breakdown = (
                goal.get("habit_breakdown")
                if isinstance(goal, dict)
                else getattr(goal, "habit_breakdown", None)
            )
            diagnosis = (
                goal.get("diagnosis", "System configured")
                if isinstance(goal, dict)
                else getattr(goal, "diagnosis", "System configured")
            )

            card_content.append(
                AtomicHabitsComponents.render_system_strength_meter(
                    goal_title="",  # Title already shown above
                    system_strength=system_strength,
                    diagnosis=diagnosis,
                    habit_breakdown=habit_breakdown,
                    show_breakdown=False,  # Compact view for card
                )
            )

        # Action buttons
        buttons = []
        if show_progress_button and str(status) == "active":
            buttons.append(
                Button(
                    "📈 Update Progress",
                    variant=ButtonT.success,
                    size=Size.sm,
                    hx_get=f"/goals/{uid}/progress-form",
                    hx_target="#modal",
                )
            )

        buttons.extend(
            [
                Button(
                    "👁️ View",
                    variant=ButtonT.outline,
                    size=Size.sm,
                    hx_get=f"/goals/{uid}/details",
                    hx_target="#modal",
                ),
                Button(
                    "📊 Gantt",
                    variant=ButtonT.secondary,
                    size=Size.sm,
                    hx_get=f"/goals/{uid}/gantt",
                    hx_target="body",
                    title="View Gantt Chart",
                ),
                Button(
                    "🏥 Health",
                    variant=ButtonT.info,
                    size=Size.sm,
                    hx_get=f"/goals/{uid}/system-health",
                    hx_target="#modal",
                    title="System Health Diagnostics (Phase 2)",
                ),
                Button(
                    "🚀 Velocity",
                    variant=ButtonT.success,
                    size=Size.sm,
                    hx_get=f"/goals/{uid}/velocity",
                    hx_target="#modal",
                    title="Habit Velocity Tracking (Phase 2)",
                ),
                Button(
                    "🎯 Impact",
                    variant=ButtonT.warning,
                    size=Size.sm,
                    hx_get=f"/goals/{uid}/impact",
                    hx_target="#modal",
                    title="Goal Impact Analysis (Phase 2)",
                ),
                Button(
                    "✏️ Edit",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    hx_get=f"/goals/{uid}/edit",
                    hx_target="#modal",
                ),
            ]
        )

        # Add buttons to card content
        if buttons:
            card_content.append(Div(*buttons, cls="flex gap-2 mt-3"))

        # Return complete card
        return Card(*card_content, id=f"goal-{uid}", cls=f"border-l-4 {border_color} p-4")

    @staticmethod
    def render_create_goal_form() -> Any:
        """
        Create goal form component with relationship context capture.

        Adds guidance manifestations and derivation reasoning
        to make entity connections comprehensible.

        Uses FormGenerator for dynamic form generation from GoalCreateRequest.
        """
        # Use FormGenerator for type-safe, dynamic form generation
        form_gen = FormGenerator()

        # Custom field configurations with semantic grouping
        field_configs = {
            "title": {
                "placeholder": "e.g., Establish daily meditation practice",
                "label": "Goal Title",
                "section": "basic",
                "section_title": "📋 Basic Information",
            },
            "description": {
                "placeholder": "Detailed description of this goal",
                "label": "Description",
                "section": "basic",
            },
            "why_important": {
                "placeholder": "Personal significance and motivation",
                "label": "Why is this important?",
                "section": "basic",
            },
            "choice_reasoning": {
                "placeholder": "e.g., Chose to prioritize mental health over constant productivity",
                "label": "What choice led you to create this goal?",
                "section": "connections",
                "section_title": "🔗 Connection Reasoning",
                "section_description": "Help yourself understand WHY and HOW this goal connects to your values",
                "help_text": "💡 Optional: Explain the decision that created this goal",
            },
            "choice_confidence": {
                "placeholder": "80",
                "label": "How confident are you in this choice? (0-100%)",
                "section": "connections",
            },
            "principle_guidance": {
                "placeholder": "e.g., Following 'small steps > big plans' by starting with just 2 minutes",
                "label": "How do your principles guide this goal?",
                "section": "connections",
                "help_text": "💡 Optional: Describe how your values shape this goal",
            },
        }

        # Generate form sections
        basic_section = Div(
            H3("📋 Basic Information", cls="text-lg font-semibold mb-3 text-base-content/70"),
            *[
                form_gen._generate_field(
                    field_name,
                    GoalCreateRequest.model_fields[field_name],
                    GoalCreateRequest.__annotations__[field_name],
                )
                for field_name, config in field_configs.items()
                if config.get("section") == "basic"
            ],
            cls="mb-6 pb-6 border-b border-base-200",
        )

        connections_section = Div(
            H3("🔗 Connection Reasoning", cls="text-lg font-semibold mb-2 text-base-content/70"),
            P(
                "Help yourself understand WHY and HOW this goal connects to your values",
                cls="text-sm text-base-content/60 mb-3",
            ),
            *[
                Div(
                    form_gen._generate_field(
                        field_name,
                        GoalCreateRequest.model_fields[field_name],
                        GoalCreateRequest.__annotations__[field_name],
                    ),
                    P(config.get("help_text", ""), cls="text-xs text-base-content/50 mt-1")
                    if config.get("help_text")
                    else None,
                    cls="mb-3",
                )
                for field_name, config in field_configs.items()
                if config.get("section") == "connections"
            ],
            cls="mb-6 pb-6 border-b border-base-200",
        )

        return Card(
            H2("🎯 Create New Goal", cls="text-xl font-bold mb-4"),
            Form(
                basic_section,
                connections_section,
                # Classification Section
                Div(
                    H3("🏷️ Classification", cls="text-lg font-semibold mb-3 text-base-content/70"),
                    Div(
                        Label("Priority", htmlfor="priority", cls="block text-sm font-medium mb-1"),
                        Select(
                            Option("Low", value="low"),
                            Option("Medium", value="medium", selected=True),
                            Option("High", value="high"),
                            Option("Critical", value="critical"),
                            name="priority",
                            id="priority",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-3",
                    ),
                    Div(
                        Label(
                            "Target Date",
                            htmlfor="target_date",
                            cls="block text-sm font-medium mb-1",
                        ),
                        Input(
                            type="date",
                            name="target_date",
                            id="target_date",
                            cls="input input-bordered w-full",
                        ),
                        cls="mb-3",
                    ),
                    cls="mb-6",
                ),
                # Submit Button
                Div(
                    Button("Create Goal 🎯", type="submit", variant=ButtonT.primary, cls="w-full"),
                    cls="mt-6",
                ),
                hx_post="/api/goals",
                hx_target="#goals-container",
                hx_swap="outerHTML",
                cls="space-y-4",
            ),
            cls="p-6 max-w-2xl mx-auto",
        )

    @staticmethod
    def render_goal_analytics_dashboard() -> Any:
        """Goal analytics dashboard component"""
        return Div(
            H1("📊 Goal Analytics", cls="text-2xl font-bold mb-6"),
            # Progress overview
            Card(
                H3("📈 Progress Overview", cls="text-lg font-semibold mb-4"),
                P("Goal progress charts will be loaded here", cls="text-base-content/60"),
                cls="p-6 mb-6",
            ),
            # Achievement patterns
            Card(
                H3("🏆 Achievement Patterns", cls="text-lg font-semibold mb-4"),
                P("Success patterns and trends analysis", cls="text-base-content/60"),
                cls="p-6 mb-6",
            ),
            # Goal insights
            Card(
                H3("🧠 Goal Insights", cls="text-lg font-semibold mb-4"),
                P("AI-powered insights from your goal patterns", cls="text-base-content/60"),
                cls="p-6",
            ),
            cls="container mx-auto p-6",
        )

    @staticmethod
    def render_goal_progress_view() -> Any:
        """Goal progress view component"""
        return Div(
            H1("📈 Goal Progress", cls="text-2xl font-bold mb-6"),
            # Progress tracking
            Card(
                H3("📊 Progress Tracking", cls="text-lg font-semibold mb-4"),
                P("Detailed progress tracking charts", cls="text-base-content/60"),
                cls="p-6 mb-6",
            ),
            # Milestone tracking
            Card(
                H3("🎯 Milestone Tracking", cls="text-lg font-semibold mb-4"),
                P("Track your goal milestones and achievements", cls="text-base-content/60"),
                cls="p-6",
            ),
            cls="container mx-auto p-6",
        )


def get_status_color(status) -> Any:
    """Get color class for goal status"""
    colors = {
        "active": "success",
        "paused": "warning",
        "completed": "success",
        "archived": "info",
        "cancelled": "error",
    }
    return colors.get(status, "ghost")


def get_priority_color(priority) -> Any:
    """Get color class for goal priority"""
    colors = {"low": "info", "medium": "warning", "high": "error", "critical": "error"}
    return colors.get(priority, "ghost")


# ============================================================================
# CLEAN UI ROUTES - Component-based rendering only
# ============================================================================


def create_goals_ui_routes(_app, rt, goals_service: GoalsService, services: Any = None):
    """
    Create three-view goal UI routes (standalone, no drawer).

    Views:
    - List: Sortable, filterable goal list with progress
    - Create: Full goal creation form
    - Calendar: Month/Week/Day views showing goal timelines

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        goals_service: Goals service instance
        services: Full services container (unused, kept for API compatibility)
    """

    logger.info("Registering three-view goal routes (standalone)")

    # ========================================================================
    # QUERY PARAM TYPES
    # ========================================================================

    @dataclass
    class Filters:
        """Typed filters for goal list queries."""

        status: str
        sort_by: str

    # ========================================================================
    # HELPER FUNCTIONS
    # ========================================================================

    def parse_filters(request) -> Filters:
        """Extract filter parameters from request query params."""
        return Filters(
            status=request.query_params.get("filter_status", "active"),
            sort_by=request.query_params.get("sort_by", "target_date"),
        )

    # ========================================================================
    # DATA FETCHING HELPERS
    # ========================================================================

    async def get_all_goals(user_uid: str) -> Result[list[Any]]:
        """Get all goals for user."""
        try:
            result = await goals_service.get_user_goals(user_uid)
            if result.is_error:
                logger.warning(f"Failed to fetch goals: {result.error}")
                return result  # Propagate the error
            return Result.ok(result.value or [])
        except Exception as e:
            logger.error(
                "Error fetching all goals",
                extra={
                    "user_uid": user_uid,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to fetch goals: {e}"))

    def get_status_str(goal) -> str:
        """Extract status as lowercase string, handling both enum and string."""
        status = getattr(goal, "status", "active")
        if isinstance(status, Enum):
            return str(status.value).lower()
        return str(status).lower()

    def get_priority_str(goal) -> str:
        """Extract priority as lowercase string, handling both enum and string."""
        priority = getattr(goal, "priority", "medium")
        if isinstance(priority, Enum):
            return str(priority.value).lower()
        return str(priority).lower()

    def get_target_date(goal) -> date:
        """Extract target_date as date object, handling both date and string."""
        target = getattr(goal, "target_date", None)
        if target is None:
            return date.max
        if isinstance(target, date):
            return target
        if isinstance(target, str):
            try:
                return date.fromisoformat(target)
            except ValueError:
                return date.max
        return date.max

    # ========================================================================
    # PURE COMPUTATION HELPERS (Testable without mocks)

    def validate_goal_form_data(form_data: dict[str, Any]) -> Result[None]:
        """
        Validate goal form data early.

        Pure function: returns clear error messages for UI.

        Args:
            form_data: Raw form data from request

        Returns:
            Result.ok(None) if valid, Errors.validation() with user-friendly message if invalid
        """
        # Required fields
        title = form_data.get("title", "").strip()
        if not title:
            return Result.fail(Errors.validation("Goal title is required"))

        if len(title) > 200:
            return Result.fail(Errors.validation("Goal title must be 200 characters or less"))

        # Date validation
        target_date_str = form_data.get("target_date", "")
        if target_date_str:
            try:
                target_date = date.fromisoformat(target_date_str)
                if target_date < date.today():
                    return Result.fail(Errors.validation("Target date must be in the future"))
            except ValueError:
                return Result.fail(Errors.validation("Invalid date format"))

        return Result.ok(None)

    # ========================================================================

    def compute_goal_stats(goals: list[Any]) -> dict[str, int]:
        """Calculate goal statistics.

        Pure function: testable without database or async.

        Args:
            goals: List of goal entities

        Returns:
            Stats dict with counts
        """
        return {
            "total": len(goals),
            "active": sum(1 for g in goals if get_status_str(g) == "active"),
            "completed": sum(1 for g in goals if get_status_str(g) == "completed"),
        }

    def apply_goal_filters(
        goals: list[Any],
        status_filter: str = "active",
    ) -> list[Any]:
        """Apply filter criteria to goal list.

        Pure function: testable without database or async.

        Args:
            goals: List of goal entities
            status_filter: Status filter (active, completed, paused, all)

        Returns:
            Filtered list of goals
        """
        # Filter by status
        if status_filter == "active":
            return [g for g in goals if get_status_str(g) == "active"]
        elif status_filter == "completed":
            return [g for g in goals if get_status_str(g) == "completed"]
        elif status_filter == "paused":
            return [g for g in goals if get_status_str(g) == "paused"]
        # "all" - no filtering
        return goals

    def apply_goal_sort(goals: list[Any], sort_by: str = "target_date") -> list[Any]:
        """Sort goals by specified field.

        Pure function: testable without database or async.

        Args:
            goals: List of goal entities
            sort_by: Sort field (target_date, priority, progress, created_at)

        Returns:
            Sorted list of goals
        """
        if sort_by == "target_date":
            return sorted(goals, key=get_target_date)
        elif sort_by == "priority":
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            sort_key = make_priority_string_getter(priority_order, get_priority_str)
            return sorted(goals, key=sort_key)
        elif sort_by == "progress":
            return sorted(goals, key=get_current_value, reverse=True)
        elif sort_by == "created_at":
            return sorted(goals, key=get_created_at_attr, reverse=True)
        else:
            # Default: target_date
            return sorted(goals, key=get_target_date)

    async def get_filtered_goals(
        user_uid: str,
        status_filter: str = "active",
        sort_by: str = "target_date",
    ) -> Result[tuple[list[Any], dict[str, int]]]:
        """Get filtered and sorted goals for user.

        Orchestrates: fetch (I/O) → stats → filter → sort.
        Pure computation delegated to testable helper functions.
        """
        try:
            # I/O: Fetch all goals
            goals_result = await get_all_goals(user_uid)
            if goals_result.is_error:
                return Result.fail(goals_result)

            goals = goals_result.value

            # Computation: Calculate stats BEFORE filtering
            stats = compute_goal_stats(goals)

            # Computation: Apply filters
            filtered_goals = apply_goal_filters(goals, status_filter)

            # Computation: Apply sort
            sorted_goals = apply_goal_sort(filtered_goals, sort_by)

            return Result.ok((sorted_goals, stats))
        except Exception as e:
            logger.error(
                "Error filtering goals",
                extra={
                    "user_uid": user_uid,
                    "status_filter": status_filter,
                    "sort_by": sort_by,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            return Result.fail(Errors.system(f"Failed to filter goals: {e}"))

    async def get_categories() -> Result[list[str]]:
        """Get unique goal categories (valid Domain enum values)."""
        return Result.ok(
            [
                "business",
                "health",
                "education",
                "personal",
                "tech",
                "creative",
                "social",
                "research",
            ]
        )

    # ========================================================================
    # MAIN DASHBOARD (Standalone Three-View)
    # ========================================================================

    @rt("/goals")
    async def goals_dashboard(request) -> Any:
        """Main goals dashboard with three views (standalone, no drawer)."""
        user_uid = require_authenticated_user(request)

        # Get view parameter (default to list)
        view = request.query_params.get("view", "list")

        # Parse using helpers
        filters = parse_filters(request)
        calendar_params = parse_calendar_params(request)

        # Get data with Result[T]
        filtered_result = await get_filtered_goals(user_uid, filters.status, filters.sort_by)
        categories_result = await get_categories()

        # CHECK FOR ERRORS
        if filtered_result.is_error:
            error_content = Div(
                GoalsViewComponents.render_view_tabs(active_view=view),
                render_error_banner("Failed to load goals"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )
            return await create_goals_page(error_content, request=request)

        if categories_result.is_error:
            error_content = Div(
                GoalsViewComponents.render_view_tabs(active_view=view),
                render_error_banner("Failed to load categories"),
                cls=f"{Spacing.PAGE} {Container.WIDE}",
            )
            return await create_goals_page(error_content, request=request)

        # Extract values
        goals, stats = filtered_result.value
        categories = categories_result.value

        # Render the appropriate view content
        if view == "create":
            view_content = GoalsViewComponents.render_create_view(
                categories=categories,
            )
        elif view == "calendar":
            all_goals_result = await get_all_goals(user_uid)

            # Check for errors
            if all_goals_result.is_error:
                view_content = render_error_banner(
                    f"Failed to load calendar: {all_goals_result.error}"
                )
            else:
                view_content = GoalsViewComponents.render_calendar_view(
                    goals=all_goals_result.value,
                    current_date=calendar_params.current_date,
                    calendar_view=calendar_params.calendar_view,
                )
        else:  # list (default)
            view_content = GoalsViewComponents.render_list_view(
                goals=goals,
                filters={
                    "status": filters.status,
                    "sort_by": filters.sort_by,
                },
                stats=stats,
                categories=categories,
            )

        # Build page with tabs + view content
        page_content = Div(
            GoalsViewComponents.render_view_tabs(active_view=view),
            Div(view_content, id="view-content", role="tabpanel"),
            cls=f"{Spacing.PAGE} {Container.WIDE}",
        )

        return await create_goals_page(page_content, request=request)

    # ========================================================================
    # HTMX VIEW FRAGMENTS
    # ========================================================================

    @rt("/goals/view/list")
    async def goals_view_list(request) -> Any:
        """HTMX fragment for list view."""
        user_uid = require_authenticated_user(request)
        filters = parse_filters(request)

        filtered_result = await get_filtered_goals(user_uid, filters.status, filters.sort_by)
        categories_result = await get_categories()

        # Handle errors (return banner directly for HTMX swap)
        if filtered_result.is_error:
            return render_error_banner("Failed to load goals")

        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        goals, stats = filtered_result.value
        categories = categories_result.value

        filters_dict: ActivityFilterSpec = {"status": filters.status, "sort_by": filters.sort_by}
        return GoalsViewComponents.render_list_view(
            goals=goals,
            filters=filters_dict,
            stats=stats,
            categories=categories,
        )

    @rt("/goals/view/create")
    async def goals_view_create(request) -> Any:
        """HTMX fragment for create view."""
        require_authenticated_user(request)
        categories_result = await get_categories()

        # Handle errors
        if categories_result.is_error:
            return render_error_banner("Failed to load categories")

        return GoalsViewComponents.render_create_view(
            categories=categories_result.value,
        )

    @rt("/goals/view/calendar")
    async def goals_view_calendar(request) -> Any:
        """HTMX fragment for calendar view."""
        user_uid = require_authenticated_user(request)
        calendar_params = parse_calendar_params(request)

        goals_result = await get_all_goals(user_uid)

        # Handle errors
        if goals_result.is_error:
            return render_error_banner("Failed to load calendar")

        return GoalsViewComponents.render_calendar_view(
            goals=goals_result.value,
            current_date=calendar_params.current_date,
            calendar_view=calendar_params.calendar_view,
        )

    # ========================================================================
    # LIST FRAGMENT (for filter updates)
    # ========================================================================

    @rt("/goals/list-fragment")
    async def goals_list_fragment(request) -> Any:
        """Return filtered goal list for HTMX updates."""
        user_uid = require_authenticated_user(request)
        filters = parse_filters(request)

        filtered_result = await get_filtered_goals(user_uid, filters.status, filters.sort_by)

        # Handle errors
        if filtered_result.is_error:
            return render_error_banner("Failed to load goals")

        goals, _stats = filtered_result.value

        # Return just the goal items
        goal_items = [GoalsViewComponents._render_goal_item(goal, user_uid) for goal in goals]

        return Div(
            *goal_items
            if goal_items
            else [P("No goals found.", cls="text-base-content/60 text-center py-8")],
            id="goal-list",
            cls="space-y-3",
        )

    # ========================================================================
    # QUICK ADD (via QuickAddRouteFactory)
    # ========================================================================

    async def create_goal_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Any]:
        """
        Domain-specific goal creation logic.

        Handles form parsing, request building, and service call.
        """
        # Extract form data
        title = form_data.get("title", "").strip()
        description = form_data.get("description", "").strip() or None
        why_important = form_data.get("why_important", "").strip() or None
        domain = form_data.get("domain", "personal")
        timeframe = form_data.get("timeframe", "quarterly")
        priority_str = form_data.get("priority", "medium")
        target_date_str = form_data.get("target_date", "")
        target_value_str = form_data.get("target_value", "")

        # Parse priority
        try:
            priority = Priority(priority_str)
        except ValueError:
            priority = Priority.MEDIUM

        # Parse target date
        target_date = None
        if target_date_str:
            with contextlib.suppress(ValueError):
                target_date = date.fromisoformat(target_date_str)

        # Parse target value
        target_value = None
        if target_value_str:
            with contextlib.suppress(ValueError):
                target_value = float(target_value_str)

        # Build request and call service
        create_request = GoalCreateRequest(
            title=title,
            description=description,
            why_important=why_important,
            domain=domain,
            timeframe=timeframe,
            priority=priority,
            target_date=target_date,
            target_value=target_value,
        )

        return await goals_service.create_goal(create_request, user_uid)

    async def render_goal_success_view(_user_uid: str) -> Any:
        """Redirect to list view after successful goal creation."""
        return Response(
            status_code=200,
            headers={"HX-Redirect": "/goals?view=list"},
        )

    async def render_goal_add_another_view(user_uid: str) -> Any:
        """Render create view for add-another flow."""
        categories = await get_categories()
        return GoalsViewComponents.render_create_view(categories=categories)

    # Register quick-add route via factory
    goals_quick_add_config = QuickAddConfig(
        domain_name="goals",
        required_field="title",
        create_entity=create_goal_from_form,
        render_success_view=render_goal_success_view,
        render_add_another_view=render_goal_add_another_view,
    )
    QuickAddRouteFactory.register_route(rt, goals_quick_add_config)

    @rt("/goals/{uid}")
    async def goal_detail_view(request, uid: str) -> Any:
        """
        Goal detail view with relationship context display.

        Shows WHY the goal exists and HOW principles guide it.
        """
        user_uid = require_authenticated_user(request)

        # Fetch goal with ownership verification
        result = await goals_service.get_for_user(uid, user_uid)

        if result.is_error or result.value is None:
            logger.error(
                f"Failed to get goal {uid}: {result.error if result.is_error else 'Not found'}"
            )
            return await BasePage(
                content=Card(
                    H2("Goal Not Found", cls="text-xl font-bold text-error mb-4"),
                    P(f"Could not find goal: {uid}", cls="text-base-content/70"),
                    Button(
                        "← Back to Goals",
                        **{"hx-get": "/goals", "hx-target": "body"},
                        variant=ButtonT.primary,
                        cls="mt-4",
                    ),
                    cls="p-6",
                ),
                title="Goal Not Found",
                page_type=PageType.STANDARD,
                request=request,
                active_page="goals",
            )

        goal = result.value

        # Get explanation (calls explain_existence() method)
        explanation = (
            goal.explain_existence() if callable(getattr(goal, "explain_existence", None)) else None
        )

        # Get guidances and derivation
        guidances = getattr(goal, "guidances", []) or []
        derivation = getattr(goal, "derivation", None)

        # Build detail content inline
        content = Div(
            # Header with title
            Card(
                Div(
                    H1(f"🎯 {goal.title}", cls="text-2xl font-bold mb-2"),
                    P(
                        goal.description or "No description provided",
                        cls="text-base-content/70 mb-4",
                    ),
                    # Status and Priority badges
                    Div(
                        Span(f"Status: {goal.status.value}", cls="badge badge-info mr-2"),
                        Span(f"Priority: {goal.priority or 'Not set'}", cls="badge badge-warning"),
                        cls="flex gap-2",
                    ),
                    cls="mb-6",
                ),
                cls="p-6 mb-4",
            ),
            # Explanation Section
            Card(
                H2(
                    "💡 Why This Goal Exists", cls="text-xl font-semibold mb-4 text-base-content/70"
                ),
                # Main explanation
                Div(
                    P(
                        explanation
                        or (
                            goal.explain_existence()
                            if callable(getattr(goal, "explain_existence", None))
                            else "No explanation available"
                        ),
                        cls="text-lg text-base-content italic mb-4 p-4 bg-blue-50 border-l-4 border-blue-500 rounded",
                    ),
                    cls="mb-6",
                ),
                # Derivation (WHY a choice created this)
                (
                    Div(
                        H3(
                            "🎯 The Choice That Created This",
                            cls="text-lg font-medium mb-2 text-base-content/70",
                        ),
                        Div(
                            P("Reasoning:", cls="text-sm font-semibold text-base-content/60 mb-1"),
                            P(derivation.reasoning, cls="text-base-content/70 mb-2"),
                            P("Confidence:", cls="text-sm font-semibold text-base-content/60 mb-1"),
                            Div(
                                Progress(
                                    value=int(derivation.confidence * 100),
                                    max="100",
                                    cls="progress progress-primary w-full",
                                ),
                                Span(
                                    f"{int(derivation.confidence * 100)}% - {derivation.get_confidence_label()}",
                                    cls="text-sm text-base-content/70 mt-1",
                                ),
                                cls="mb-2",
                            ),
                            cls="p-4 bg-green-50 border-l-4 border-green-500 rounded",
                        ),
                        cls="mb-6",
                    )
                    if derivation
                    else Div()
                ),
                # Guidances (HOW principles guide)
                Div(
                    H3(
                        "🧭 How Principles Guide This Goal",
                        cls="text-lg font-medium mb-2 text-base-content/70",
                    ),
                    Div(
                        *[
                            Div(
                                Div(
                                    Span("💎 ", cls="text-xl"),
                                    Span(g.manifestation, cls="text-base-content/70 font-medium"),
                                    cls="mb-2",
                                ),
                                Div(
                                    Span(
                                        f"Strength: {g.get_strength_label()}",
                                        cls=f"badge {'badge-success' if g.is_strong_guidance() else 'badge-warning'}",
                                    ),
                                    Progress(
                                        value=int(g.strength * 100),
                                        max="100",
                                        cls="progress progress-primary w-full mt-1",
                                    ),
                                    cls="mb-2",
                                ),
                                cls="p-3 bg-purple-50 border-l-4 border-purple-500 rounded mb-3",
                            )
                            for g in guidances
                        ],
                        cls="space-y-2",
                    )
                    if guidances
                    else P("No principle guidances defined yet", cls="text-base-content/60 italic"),
                    cls="mb-4",
                ),
                cls="p-6 mb-4",
            ),
            # Goal Details Section
            Card(
                H2("📋 Goal Details", cls="text-xl font-semibold mb-4 text-base-content/70"),
                Div(
                    # Why Important
                    (
                        Div(
                            P(
                                "Why Important:",
                                cls="text-sm font-semibold text-base-content/70 mb-1",
                            ),
                            P(goal.why_important, cls="text-base-content mb-3"),
                            cls="mb-4",
                        )
                        if getattr(goal, "why_important", None)
                        else Div()
                    ),
                    # Target Date
                    (
                        Div(
                            P(
                                "Target Date:",
                                cls="text-sm font-semibold text-base-content/70 mb-1",
                            ),
                            P(str(goal.target_date), cls="text-base-content mb-3"),
                            cls="mb-4",
                        )
                        if getattr(goal, "target_date", None)
                        else Div()
                    ),
                    # Progress
                    (
                        Div(
                            P("Progress:", cls="text-sm font-semibold text-base-content/70 mb-1"),
                            Progress(
                                value=int(getattr(goal, "progress_percentage", 0)),
                                max="100",
                                cls="progress progress-success w-full",
                            ),
                            Span(
                                f"{int(getattr(goal, 'progress_percentage', 0))}%",
                                cls="text-sm text-base-content/60 mt-1",
                            ),
                            cls="mb-4",
                        )
                        if getattr(goal, "progress_percentage", None) is not None
                        else Div()
                    ),
                    cls="space-y-2",
                ),
                cls="p-6 mb-4",
            ),
            # Actions Card
            Card(
                Div(
                    Button(
                        "← Back to Goals",
                        **{"hx-get": "/goals", "hx-target": "body"},
                        variant=ButtonT.ghost,
                        cls="mr-2",
                    ),
                    Button(
                        "✏️ Edit Goal",
                        **{"hx-get": f"/goals/{goal.uid}/edit", "hx-target": "#modal"},
                        variant=ButtonT.primary,
                    ),
                    cls="flex gap-2 flex-wrap",
                ),
                cls="p-4 mb-4",
            ),
            # Lateral Relationships Section
            EntityRelationshipsSection(
                entity_uid=goal.uid,
                entity_type="goals",
            ),
            cls=f"{Container.STANDARD} {Spacing.PAGE}",
        )

        return await BasePage(
            content=content,
            title=goal.title,
            page_type=PageType.STANDARD,
            request=request,
            active_page="goals",
        )

    @rt("/goals/{uid}/details")
    async def goal_details_modal(_request, uid: str) -> Any:
        """Goal details modal fragment (legacy route, redirects to full view)"""
        return Div(hx_get=f"/goals/{uid}", hx_target="body", hx_trigger="load")

    @rt("/goals/{uid}/edit")
    async def goal_edit_form(_request, uid: str) -> Any:
        """Edit goal form fragment"""
        return Card(
            H2("✏️ Edit Goal", cls="text-xl font-bold mb-4"),
            P(f"Edit form for goal {uid} will be implemented here", cls="text-base-content/60"),
            cls="p-6",
        )

    @rt("/goals/{uid}/progress-form")
    async def goal_progress_form(_request, uid: str) -> Any:
        """Progress update form fragment"""
        return Card(
            H2("📈 Update Progress", cls="text-xl font-bold mb-4"),
            P(
                f"Progress update form for goal {uid} will be implemented here",
                cls="text-base-content/60",
            ),
            cls="p-6",
        )

    @rt("/goals/{uid}/hierarchy")
    async def goal_hierarchy_view(request, uid: str) -> Any:
        """
        Hierarchy tree view for a goal and its subgoals.

        Displays expandable tree with drag-drop, keyboard nav, multi-select.
        """
        user_uid = require_authenticated_user(request)

        # Verify goal exists and user owns it
        result = await goals_service.get_for_user(uid, user_uid)
        if result.is_error or result.value is None:
            return await BasePage(
                content=Card(
                    H3("Goal Not Found", cls="text-lg font-bold text-error"),
                    P(f"Could not find goal: {uid}"),
                    cls="p-6",
                ),
                title="Goal Not Found",
                page_type=PageType.STANDARD,
                request=request,
            )

        goal = result.value

        # Render hierarchy view
        content = GoalsViewComponents.render_hierarchy_view(
            root_uid=uid,
            root_goal=goal,
        )

        return await BasePage(
            content=content,
            title=f"{goal.title} - Hierarchy",
            page_type=PageType.STANDARD,
            request=request,
        )

    @rt("/goals/{uid}/gantt")
    async def goal_gantt_view(request, uid: str) -> Any:
        """
        Gantt chart view for a goal with its related tasks.

        Displays the goal timeline with dependent tasks using Frappe Gantt.
        """
        from ui.goals.visualization import (
            create_gantt_view,
            gantt_scripts,
        )

        user_uid = require_authenticated_user(request)

        # Verify goal exists and user owns it
        if goals_service:
            result = await goals_service.get_for_user(uid, user_uid)
            if result.is_error:
                return Card(
                    H3("Goal Not Found", cls="text-lg font-bold text-error"),
                    P(f"Could not find goal: {uid}"),
                    cls="p-6",
                )
            goal = result.value
            if goal is None:
                return Card(
                    H3("Goal Not Found", cls="text-lg font-bold text-error"),
                    P(f"Could not find goal: {uid}"),
                    cls="p-6",
                )
            title = f"Timeline: {goal.title}"
        else:
            title = f"Timeline: Goal {uid}"

        # Build page with Gantt component
        return Div(
            # Include Frappe Gantt scripts
            *gantt_scripts(),
            # Header
            Div(
                H2(title, cls="text-xl font-bold"),
                Button(
                    "← Back to Goal",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    hx_get=f"/goals/{uid}",
                    hx_target="body",
                ),
                cls="flex justify-between items-center mb-4",
            ),
            # Gantt chart
            create_gantt_view(
                data_url=f"/api/visualizations/gantt/goal/{uid}",
                title=None,  # Already have title above
                height="h-[60vh]",
                include_scripts=False,  # Already included above
            ),
            # Alpine.js components
            Script(src="/static/js/skuel.js"),
            cls="p-6",
        )

    # ========================================================================
    # JAVASCRIPT INTEGRATION
    # ========================================================================

    @rt("/static/js/goals.js")
    async def goals_javascript(_request) -> Any:
        """Serve goals-specific JavaScript"""
        js_content = """
        // Goals UI JavaScript - no more inline scripts in routes!

        function closeModal() {
            document.getElementById('modal').innerHTML = '';
        }

        function updateGoalProgress(goalUid, progress) {
            htmx.ajax('POST', `/api/goals/${goalUid}/progress`, {
                values: { progress: progress }
                target: '#goals-container'
            });
        }

        function refreshGoals() {
            htmx.trigger('#goals-container', 'refresh');
        }

        // HTMX event handlers
        document.addEventListener('htmx:afterSwap', function(evt) {
            if (evt.detail.target.id === 'goals-list') {
                console.log('Goals list updated');
            }
        });

        console.log('Goals UI JavaScript loaded');
        """

        return Response(js_content, media_type="application/javascript")

    return []  # Routes registered via @rt() decorators (no objects returned)


# Export the route creation function
__all__ = ["create_goals_ui_routes"]
