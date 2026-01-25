"""
Orchestration API Routes - Phase 1 Essential Services (FastHTML-Aligned)
=========================================================================

API endpoints for cross-domain orchestration services following FastHTML best practices:
- GoalTaskGenerator: Auto-generate tasks from goals
- HabitEventScheduler: Auto-schedule events from habits
- GoalsIntelligenceService: Predictive goal success analytics (merged from GoalAnalyticsService)
- PrincipleAlignmentService: Motivational intelligence

FastHTML Conventions Applied:
- Query parameters over path parameters
- Function names define routes
- Type hints for automatic parameter extraction
- POST for all mutations

These services fill critical gaps in the architecture by bridging
domain entities and providing AI/ML insights.
"""

__version__ = "1.0"

from fasthtml.common import JSONResponse, Request

from core.auth import require_authenticated_user
from core.services.user import UserContext
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def create_orchestration_routes(_app, rt, services):
    """
    Create and register orchestration API routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with orchestration services
    """

    # ========================================================================
    # GOAL → TASK GENERATION
    # ========================================================================

    @rt("/goals/generate-tasks")
    @boundary_handler()
    async def generate_tasks(request: Request, uid: str, auto_create: bool = False) -> JSONResponse:
        """
        Generate tasks for a goal based on milestones, knowledge requirements, and habits.
        Requires authentication.

        FastHTML Convention: Query parameters with type hints
        Query params:
            uid: Goal UID
            auto_create: If True, create tasks; if False, return templates only

        Returns:
            List of generated or template tasks
        """
        if not services.goal_task_generator:
            return Result.fail(
                Errors.system("GoalTaskGenerator not available", service="GoalTaskGenerator")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)
        user_context = UserContext(user_uid=user_uid)

        return await services.goal_task_generator.generate_tasks_for_goal(
            goal_uid=uid, user_context=user_context, auto_create=auto_create
        )

    @rt("/goals/task-templates")
    @boundary_handler()
    async def task_templates(request: Request, uid: str) -> JSONResponse:
        """
        Get task templates for a goal without creating them.
        Requires authentication.

        FastHTML Convention: Function name = route, query param for ID
        """
        if not services.goal_task_generator:
            return Result.fail(
                Errors.system("GoalTaskGenerator not available", service="GoalTaskGenerator")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)
        user_context = UserContext(user_uid=user_uid)

        return await services.goal_task_generator.generate_tasks_for_goal(
            goal_uid=uid,
            user_context=user_context,
            auto_create=False,  # Templates only
        )

    # ========================================================================
    # HABIT → EVENT SCHEDULING
    # ========================================================================

    @rt("/habits/schedule-events")
    @boundary_handler()
    async def schedule_events(
        request: Request, uid: str, auto_create: bool = False, days_ahead: int = 7
    ) -> JSONResponse:
        """
        Schedule recurring events for a habit.
        Requires authentication.

        FastHTML Convention: All parameters from query string
        Query params:
            uid: Habit UID
            auto_create: If True, create events; if False, return templates only
            days_ahead: How many days to schedule ahead (default: 7)

        Returns:
            List of scheduled or template events
        """
        if not services.habit_event_scheduler:
            return Result.fail(
                Errors.system("HabitEventScheduler not available", service="HabitEventScheduler")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)
        user_context = UserContext(user_uid=user_uid)

        return await services.habit_event_scheduler.schedule_events_for_habit(
            habit_uid=uid, user_context=user_context, auto_create=auto_create, days_ahead=days_ahead
        )

    @rt("/habits/event-templates")
    @boundary_handler()
    async def event_templates(request: Request, uid: str) -> JSONResponse:
        """
        Get event templates for a habit without creating them.
        Requires authentication.

        FastHTML Convention: Simple function name, query param for ID
        """
        if not services.habit_event_scheduler:
            return Result.fail(
                Errors.system("HabitEventScheduler not available", service="HabitEventScheduler")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)
        user_context = UserContext(user_uid=user_uid)

        return await services.habit_event_scheduler.schedule_events_for_habit(
            habit_uid=uid,
            user_context=user_context,
            auto_create=False,  # Templates only
        )

    # ========================================================================
    # GOAL ANALYTICS - Predictive Success
    # ========================================================================

    @rt("/goals/predict-success")
    @boundary_handler()
    async def predict_success(uid: str, lookback_days: int = 30) -> JSONResponse:
        """
        Predict goal success probability using habit data and historical patterns.

        FastHTML Convention: Query parameters with type hints
        Query params:
            uid: Goal UID
            lookback_days: Days of historical data to analyze (default: 30)

        Returns:
            GoalPrediction with success probability, risk factors, and recommendations
        """
        if not services.goals_intelligence:
            return Result.fail(
                Errors.system(
                    "GoalsIntelligenceService not available", service="GoalsIntelligenceService"
                )
            )

        return await services.goals_intelligence.predict_goal_success(
            goal_uid=uid,
            lookback_days=lookback_days,
            habits_service=services.habits,  # Pass habits service for full analysis
        )

    @rt("/goals/habit-impact")
    @boundary_handler()
    async def habit_impact(uid: str) -> JSONResponse:
        """
        Analyze which habits have the most impact on goal success.

        FastHTML Convention: Query parameter with type hint
        Query params:
            uid: Goal UID

        Returns:
            List of HabitImpactAnalysis showing criticality and consistency gaps
        """
        if not services.goals_intelligence:
            return Result.fail(
                Errors.system(
                    "GoalsIntelligenceService not available", service="GoalsIntelligenceService"
                )
            )

        return await services.goals_intelligence.analyze_habit_impact(
            goal_uid=uid,
            habits_service=services.habits,  # Pass habits service for analysis
        )

    @rt("/goals/risk-assessment")
    @boundary_handler()
    async def risk_assessment(uid: str) -> JSONResponse:
        """
        Assess risk factors for goal achievement.

        FastHTML Convention: Query parameter with type hint
        Query params:
            uid: Goal UID

        Returns:
            Risk assessment with identified blockers and mitigation strategies
        """
        if not services.goals_intelligence:
            return Result.fail(
                Errors.system(
                    "GoalsIntelligenceService not available", service="GoalsIntelligenceService"
                )
            )

        # Get prediction which includes risk factors
        prediction_result = await services.goals_intelligence.predict_goal_success(
            goal_uid=uid,
            habits_service=services.habits,  # Pass habits service for full analysis
        )

        if prediction_result.is_error:
            return prediction_result

        prediction = prediction_result.value

        return Result.ok(
            {
                "goal_uid": uid,
                "risk_level": "high"
                if prediction.success_probability < 0.5
                else "medium"
                if prediction.success_probability < 0.75
                else "low",
                "risk_factors": prediction.risk_factors,
                "recommended_actions": prediction.recommended_actions,
                "trend": prediction.trend,
            }
        )

    # ========================================================================
    # PRINCIPLE ALIGNMENT - Motivational Intelligence
    # ========================================================================

    @rt("/principles/list")
    @boundary_handler()
    async def list_principles(request: Request) -> JSONResponse:
        """
        Get all principles for the authenticated user.
        Requires authentication.

        Returns:
            List of user's principles
        """
        if not services.principles:
            return Result.fail(
                Errors.system("PrinciplesService not available", service="PrinciplesService")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        return await services.principles.get_user_principles(user_uid=user_uid)

    @rt("/principles/goal-alignment")
    @boundary_handler()
    async def goal_alignment(request: Request, goal_uid: str) -> JSONResponse:
        """
        Assess how well a goal aligns with the authenticated user's principles.
        Requires authentication.

        Args:
            goal_uid: Goal UID

        Returns:
            Alignment score and detailed analysis
        """
        if not services.principles:
            return Result.fail(
                Errors.system("PrinciplesService not available", service="PrinciplesService")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        return await services.principles.assess_goal_alignment(goal_uid=goal_uid, user_uid=user_uid)

    @rt("/principles/habit-alignment")
    @boundary_handler()
    async def habit_alignment(request: Request, habit_uid: str) -> JSONResponse:
        """
        Assess how well a habit aligns with the authenticated user's principles.
        Requires authentication.

        Args:
            habit_uid: Habit UID

        Returns:
            Alignment score and detailed analysis
        """
        if not services.principles:
            return Result.fail(
                Errors.system("PrinciplesService not available", service="PrinciplesService")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        return await services.principles.assess_habit_alignment(
            habit_uid=habit_uid, user_uid=user_uid
        )

    @rt("/principles/motivational-profile")
    @boundary_handler()
    async def motivational_profile(request: Request) -> JSONResponse:
        """
        Get comprehensive motivational profile for the authenticated user.
        Requires authentication.

        Includes principle hierarchy, value patterns, and alignment insights.

        Returns:
            Comprehensive motivational profile
        """
        if not services.principles:
            return Result.fail(
                Errors.system("PrinciplesService not available", service="PrinciplesService")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        return await services.principles.get_motivational_profile(user_uid=user_uid)

    @rt("/principles/suggest-actions")
    @boundary_handler()
    async def suggest_actions(request: Request, context: str = "general") -> JSONResponse:
        """
        Suggest actions that align with the authenticated user's principles.
        Requires authentication.

        Args:
            context: Context for suggestions (e.g., "goal", "habit", "general")

        Returns:
            List of principle-aligned action suggestions
        """
        if not services.principles:
            return Result.fail(
                Errors.system("PrinciplesService not available", service="PrinciplesService")
            )

        # Get authenticated user from session (raises 401 if not authenticated)
        user_uid = require_authenticated_user(request)

        # This would use the suggest_principle_aligned_actions method
        # For now, return a placeholder
        return Result.ok(
            {
                "user_uid": user_uid,
                "context": context,
                "suggestions": [],
                "message": "Principle-aligned action suggestions - implementation pending",
            }
        )

    logger.info("✅ Orchestration API routes registered (FastHTML-aligned)")
