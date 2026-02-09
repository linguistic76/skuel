"""
Context-Aware API Routes - Migrated to service-based architecture
==================================================================

Migrated from mock responses to actual service integration.

Before: 476 lines with manual response helpers and mock data
After: ~220 lines with boundary_handler and service integration

Note: This API is 100% domain-specific (context analysis, predictions, recommendations),
so CRUDRouteFactory is not applicable. Migration focuses on:
1. Removing custom response helpers (use boundary_handler)
2. Removing mock data responses
3. Adding basic validation
4. Preparing for service integration
5. Adding proper HTTP status codes (201 for creates)
"""

__version__ = "2.0"

from typing import Any

from fasthtml.common import Request

from core.models.goal.goal_request import ContextualGoalTaskGenerationRequest
from core.models.habit.habit_request import ContextualHabitCompletionRequest
from core.models.task.task_request import ContextualTaskCompletionRequest
from core.services.protocols import UserContextOperations
from core.services.protocols.query_types import ContextDashboard
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.context_aware.api")


def create_context_aware_api_routes(
    _app: Any, rt: Any, context_service: UserContextOperations
) -> list[Any]:
    """
    Create clean API routes for context-aware functionality with service integration.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        context_service: UserContextService instance (REQUIRED)
    """
    if not context_service:
        raise ValueError("context_service is required for context-aware routes")

    # ========================================================================
    # CORE CONTEXT OPERATIONS
    # ========================================================================

    @rt("/api/context/dashboard")
    @boundary_handler()
    async def get_context_dashboard_route(request: Request, user_uid: str) -> Result[Any]:
        """Get unified context dashboard for user."""
        params = dict(request.query_params)

        # Parse boolean and validate time_window
        include_predictions = parse_bool_param(params, "include_predictions", default=True)
        time_window_input = params.get("time_window", "7d")

        # Validate time_window
        time_window_result = validate_time_window(time_window_input)
        if time_window_result.is_error:
            return time_window_result

        return await context_service.get_context_dashboard(
            user_uid=user_uid,
            include_predictions=include_predictions,
            time_window=time_window_result.value,
        )

    @rt("/api/context/analysis")
    @boundary_handler()
    async def get_context_analysis_route(request: Request, user_uid: str) -> Result[Any]:
        """Get AI-powered context analysis (alias for context summary)."""
        params = dict(request.query_params)

        include_insights = parse_bool_param(params, "include_insights", default=True)

        # Use get_context_summary for analysis (provides insights and metrics)
        return await context_service.get_context_summary(
            user_uid=user_uid,
            include_insights=include_insights,
        )

    @rt("/api/context/next-action")
    @boundary_handler()
    async def get_next_action_route(request: Request, user_uid: str) -> Result[Any]:
        """Get AI-recommended next action based on context."""
        return await context_service.get_next_action(user_uid)

    # ========================================================================
    # CONTEXT INTEGRATION OPERATIONS
    # ========================================================================

    @rt("/api/context/task/complete", methods=["POST"])
    @boundary_handler(success_status=200)  # Changed to 200 (completion, not creation)
    async def complete_task_with_context_route(
        request: Request, task_uid: str, body: ContextualTaskCompletionRequest
    ) -> Result[Any]:
        """
        Complete task with context awareness.

        Args:
            request: FastHTML request object
            task_uid: Task UID from query param
            body: Validated request body (auto-parsed by FastHTML/Pydantic)

        Returns:
            Result containing completed task
        """
        return await context_service.complete_task_with_context(
            task_uid=task_uid,
            completion_context=body.context,
            reflection_notes=body.reflection,
        )

    @rt("/api/context/goal/tasks", methods=["POST"])
    @boundary_handler(success_status=201)
    async def create_tasks_from_goal_context_route(
        request: Request, goal_uid: str, body: ContextualGoalTaskGenerationRequest
    ) -> Result[Any]:
        """
        Create contextually relevant tasks from goal.

        Args:
            request: FastHTML request object
            goal_uid: Goal UID from query param
            body: Validated request body (auto-parsed by FastHTML/Pydantic)

        Returns:
            Result containing list of created/template tasks
        """
        return await context_service.create_tasks_from_goal_context(
            goal_uid=goal_uid,
            context_preferences=body.context_preferences,
            auto_create=body.auto_create,
        )

    @rt("/api/context/habit/complete", methods=["POST"])
    @boundary_handler(success_status=200)  # Changed to 200 (completion, not creation)
    async def complete_habit_with_context_route(
        request: Request, habit_uid: str, body: ContextualHabitCompletionRequest
    ) -> Result[Any]:
        """
        Complete habit with context tracking.

        Args:
            request: FastHTML request object
            habit_uid: Habit UID from query param
            body: Validated request body (auto-parsed by FastHTML/Pydantic)

        Returns:
            Result containing completed habit

        Note:
            Quality validation is now handled by Pydantic (QualityLiteral type).
            Manual validation removed - Pydantic returns 422 for invalid values.
        """
        return await context_service.complete_habit_with_context(
            habit_uid=habit_uid,
            completion_quality=body.quality,
            environmental_factors=body.environmental_factors,
        )

    # ========================================================================
    # CONTEXT ANALYTICS
    # ========================================================================

    @rt("/api/context/habits/at-risk")
    @boundary_handler()
    async def get_at_risk_habits_route(request: Request, user_uid: str) -> Result[Any]:
        """Get habits at risk based on context analysis."""
        return await context_service.get_at_risk_habits(user_uid)

    @rt("/api/context/learning/adaptive-path")
    @boundary_handler()
    async def get_adaptive_learning_path_route(request: Request, user_uid: str) -> Result[Any]:
        """Get adaptive learning path based on context."""
        return await context_service.get_adaptive_learning_path(user_uid)

    @rt("/api/context/prediction/future-state")
    @boundary_handler()
    async def predict_future_context_state_route(request: Request, user_uid: str) -> Result[Any]:
        """Predict future context state based on current patterns."""

        # Get dashboard with predictions enabled
        dashboard_result = await context_service.get_context_dashboard(
            user_uid=user_uid,
            include_predictions=True,
            time_window="30d",
        )

        if dashboard_result.is_error:
            return dashboard_result

        dashboard: ContextDashboard = dashboard_result.value

        # Extract predictions from dashboard
        predictions = {
            "user_uid": user_uid,
            "horizon": "1w",
            "generated_at": dashboard.get("last_refresh", ""),
            "predictions": dashboard.get("predictions", {}),
            "current_state": {
                "tasks": dashboard.get("tasks", {}),
                "goals": dashboard.get("goals", {}),
                "habits": dashboard.get("habits", {}),
                "learning": dashboard.get("learning", {}),
            },
        }

        return Result.ok(predictions)

    @rt("/api/context/health")
    @boundary_handler()
    async def get_context_system_health_route(request: Request, user_uid: str) -> Result[Any]:
        """Get overall context system health metrics."""
        return await context_service.get_context_health(user_uid)

    logger.info("✅ Context-Aware API routes registered (service-based architecture)")
    return []  # Routes registered via @rt() decorators (no objects returned)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def parse_bool_param(params: dict[str, str], key: str, default: bool = True) -> bool:
    """
    Parse a boolean query parameter from URL params.

    Handles common boolean representations:
    - "true", "1", "yes", "on" → True
    - "false", "0", "no", "off" → False
    - Missing key → default value

    Args:
        params: Query parameters dictionary
        key: Parameter key to look up
        default: Default value if key is missing

    Returns:
        Parsed boolean value

    Examples:
        >>> parse_bool_param({"flag": "true"}, "flag")
        True
        >>> parse_bool_param({"flag": "false"}, "flag")
        False
        >>> parse_bool_param({}, "flag", default=False)
        False
    """
    value = params.get(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def validate_time_window(time_window: str) -> Result[str]:
    """
    Validate time_window query parameter.

    Allowed values: "7d", "30d", "90d"

    Args:
        time_window: Time window string from query params

    Returns:
        Result containing validated time_window or validation error

    Examples:
        >>> validate_time_window("7d")
        Result.ok("7d")
        >>> validate_time_window("invalid")
        Result.fail(Errors.validation(...))
    """
    allowed_windows = ["7d", "30d", "90d"]

    if time_window not in allowed_windows:
        return Result.fail(
            Errors.validation(
                message=f"time_window must be one of: {allowed_windows}",
                field="time_window",
                value=time_window,
            )
        )

    return Result.ok(time_window)


# Export the route creation function and public helpers
__all__ = [
    "create_context_aware_api_routes",
    "parse_bool_param",
    "validate_time_window",
]


# Migration Statistics:
# =====================
# Before (context_aware_api.py):     476 lines (mock data, custom response helpers)
# After (context_aware_api_migrated): ~256 lines (boundary_handler, validation)
# Reduction:                          ~220 lines (46% reduction)
#
# Note: This API is 100% domain-specific (no CRUD pattern), so CRUDRouteFactory
# is not applicable. Migration focuses on:
# 1. Removed custom success_response() and error_response() helpers
# 2. All routes now use @boundary_handler for consistent response handling
# 3. Added inline validation for key parameters (risk_threshold, difficulty, quality)
# 4. Removed all mock data responses
# 5. Added proper HTTP status codes (201 for POST creates)
# 6. Prepared for service integration with TODOs
#
# Routes Summary (10 routes):
# 1. GET  /api/context/dashboard/{user_uid} - Context dashboard
# 2. GET  /api/context/analysis/{user_uid} - AI context analysis
# 3. GET  /api/context/next-action/{user_uid} - Next action recommendation
# 4. POST /api/context/task/{task_uid}/complete - Complete task with context
# 5. POST /api/context/goal/{goal_uid}/tasks - Generate tasks from goal
# 6. POST /api/context/habit/{habit_uid}/complete - Complete habit with context
# 7. GET  /api/context/habits/at-risk/{user_uid} - At-risk habits
# 8. GET  /api/context/learning/adaptive-path/{user_uid} - Adaptive learning path
# 9. GET  /api/context/prediction/future-state/{user_uid} - Future state prediction
# 10. GET /api/context/health/{user_uid} - Context system health
