"""
Context-Aware API Routes
========================

JSON routes over ``UserContextOperations``: the context dashboard, analysis and
next action, the two context integrations (goal → tasks, habit completion), and the
context analytics reads. Every route is authenticated and scoped to the caller; the
two integrations are CSRF-protected POSTs whose bodies bind through ``parse_body``.
"""

__version__ = "2.0"

from typing import Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_body
from adapters.inbound.route_factories import parse_bool_query_param
from core.models.goal.goal_request import ContextualGoalTaskGenerationRequest
from core.models.habit.habit import Habit
from core.models.habit.habit_request import ContextualHabitCompletionRequest
from core.models.task.task import Task
from core.ports import UserContextOperations
from core.ports.query_types import (
    AdaptiveLearningPathResult,
    AtRiskHabitsResult,
    ContextDashboard,
    ContextHealthResult,
    ContextSummary,
    FutureContextStateResult,
    NextActionResult,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.context_aware.api")


def create_context_aware_api_routes(
    _app: Any, rt: Any, context_service: UserContextOperations
) -> None:
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
    async def get_context_dashboard_route(request: Request) -> Result[ContextDashboard]:
        """Get unified context dashboard for user."""
        user_uid = require_authenticated_user(request)
        params = dict(request.query_params)

        # Parse boolean and validate time_window
        include_predictions = parse_bool_query_param(params, "include_predictions", default=True)
        time_window_input = params.get("time_window", "7d")

        # Validate time_window
        time_window_result = validate_time_window(time_window_input)
        if time_window_result.is_error:
            return Result.fail(time_window_result)

        return await context_service.get_context_dashboard(
            user_uid=user_uid,
            include_predictions=include_predictions,
            time_window=time_window_result.value,
        )

    @rt("/api/context/analysis")
    @boundary_handler()
    async def get_context_analysis_route(request: Request) -> Result[ContextSummary]:
        """Get AI-powered context analysis (alias for context summary)."""
        user_uid = require_authenticated_user(request)
        params = dict(request.query_params)

        include_insights = parse_bool_query_param(params, "include_insights", default=True)

        # Use get_context_summary for analysis (provides insights and metrics)
        return await context_service.get_context_summary(
            user_uid=user_uid,
            include_insights=include_insights,
        )

    @rt("/api/context/next-action")
    @boundary_handler()
    async def get_next_action_route(request: Request) -> Result[NextActionResult]:
        """Get AI-recommended next action based on context."""
        user_uid = require_authenticated_user(request)
        return await context_service.get_next_action(user_uid)

    # ========================================================================
    # CONTEXT INTEGRATION OPERATIONS
    # ========================================================================

    @rt("/api/context/goal/tasks", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=201)
    async def create_tasks_from_goal_context_route(
        request: Request, goal_uid: str
    ) -> Result[list[Task]]:
        """
        Create contextually relevant tasks from goal.

        Args:
            request: FastHTML request object (body: ``ContextualGoalTaskGenerationRequest``,
                JSON or form-encoded; a rejected field is a 400)
            goal_uid: Goal UID from query param

        Returns:
            Result containing list of created/template tasks
        """
        user_uid = require_authenticated_user(request)
        parsed = await parse_body(request, ContextualGoalTaskGenerationRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        body = parsed.value
        return await context_service.create_tasks_from_goal_context(
            goal_uid=goal_uid,
            user_uid=user_uid,
            context_preferences=body.context_preferences,
            auto_create=body.auto_create,
        )

    @rt("/api/context/habit/complete", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=200)
    async def complete_habit_with_context_route(request: Request, habit_uid: str) -> Result[Habit]:
        """
        Complete habit with context tracking.

        Args:
            request: FastHTML request object (body: ``ContextualHabitCompletionRequest``,
                JSON or form-encoded; a rejected field is a 400)
            habit_uid: Habit UID from query param

        Returns:
            Result containing completed habit
        """
        user_uid = require_authenticated_user(request)
        parsed = await parse_body(request, ContextualHabitCompletionRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        body = parsed.value
        return await context_service.complete_habit_with_context(
            habit_uid=habit_uid,
            user_uid=user_uid,
            completion_quality=body.quality,
            environmental_factors=body.environmental_factors,
        )

    # ========================================================================
    # CONTEXT ANALYTICS
    # ========================================================================

    @rt("/api/context/habits/at-risk")
    @boundary_handler()
    async def get_at_risk_habits_route(request: Request) -> Result[AtRiskHabitsResult]:
        """Get habits at risk based on context analysis."""
        user_uid = require_authenticated_user(request)
        return await context_service.get_at_risk_habits(user_uid)

    @rt("/api/context/learning/adaptive-path")
    @boundary_handler()
    async def get_adaptive_learning_path_route(
        request: Request,
    ) -> Result[AdaptiveLearningPathResult]:
        """Get adaptive learning path based on context."""
        user_uid = require_authenticated_user(request)
        return await context_service.get_adaptive_learning_path(user_uid)

    @rt("/api/context/prediction/future-state")
    @boundary_handler()
    async def predict_future_context_state_route(
        request: Request,
    ) -> Result[FutureContextStateResult]:
        """Predict future context state based on current patterns."""
        user_uid = require_authenticated_user(request)
        return await context_service.predict_future_context_state(user_uid)

    @rt("/api/context/health")
    @boundary_handler()
    async def get_context_system_health_route(request: Request) -> Result[ContextHealthResult]:
        """Get overall context system health metrics."""
        user_uid = require_authenticated_user(request)
        return await context_service.get_context_health(user_uid)

    logger.info("Context-Aware API routes registered (service-based architecture)")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


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
    "validate_time_window",
]
