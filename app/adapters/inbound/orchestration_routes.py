"""
Orchestration Routes - Cross-Domain Orchestration Services
==========================================================

Wires orchestration API routes using DomainRouteConfig (Multi-Factory variant).

Primary service: goal_task_generator (Goal→Task generation)
Extension factories:
- create_habit_event_routes: Habit→Event scheduling (2 endpoints)
- create_goals_intelligence_routes: Predictive goal analytics (3 endpoints)
- create_principle_alignment_routes: Principle alignment & motivational intel (5 endpoints)

Routes:
- POST /goals/generate-tasks - Generate tasks from a goal
- GET  /goals/task-templates - Get task templates for a goal
- POST /habits/schedule-events - Schedule events from a habit
- GET  /habits/event-templates - Get event templates for a habit
- GET  /goals/predict-success - Predict goal success probability
- GET  /goals/habit-impact - Analyze habit impact on goals
- GET  /goals/risk-assessment - Assess goal risk factors
- GET  /principles/list - List user's principles
- GET  /principles/goal-alignment - Goal-principle alignment
- GET  /principles/habit-alignment - Habit-principle alignment
- GET  /principles/motivational-profile - User motivational profile
- GET  /principles/suggest-actions - Principle-aligned action suggestions
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import JSONResponse, Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from core.services.user import UserContext
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import GoalTaskGeneratorOperations, HabitEventSchedulerOperations

logger = get_logger("skuel.routes.orchestration")


# ---------------------------------------------------------------------------
# Goal → Task Generation (primary service)
# ---------------------------------------------------------------------------


def create_goal_task_routes(
    _app: Any, rt: Any, goal_task_generator: "GoalTaskGeneratorOperations"
) -> list[Any]:
    """Register Goal→Task generation endpoints."""

    @rt("/goals/generate-tasks")
    @boundary_handler()
    async def generate_tasks(request: Request, uid: str, auto_create: bool = False) -> JSONResponse:
        """
        Generate tasks for a goal based on milestones, knowledge requirements, and habits.
        Requires authentication.

        Query params:
            uid: Goal UID
            auto_create: If True, create tasks; if False, return templates only
        """
        user_uid = require_authenticated_user(request)
        user_context = UserContext(user_uid=user_uid)

        return await goal_task_generator.generate_tasks_for_goal(
            goal_uid=uid, user_context=user_context, auto_create=auto_create
        )

    @rt("/goals/task-templates")
    @boundary_handler()
    async def task_templates(request: Request, uid: str) -> JSONResponse:
        """
        Get task templates for a goal without creating them.
        Requires authentication.

        Query params:
            uid: Goal UID
        """
        user_uid = require_authenticated_user(request)
        user_context = UserContext(user_uid=user_uid)

        return await goal_task_generator.generate_tasks_for_goal(
            goal_uid=uid,
            user_context=user_context,
            auto_create=False,  # Templates only
        )

    return [generate_tasks, task_templates]


# ---------------------------------------------------------------------------
# Habit → Event Scheduling (extension)
# ---------------------------------------------------------------------------


def create_habit_event_routes(
    _app: Any, rt: Any, habit_event_scheduler: "HabitEventSchedulerOperations"
) -> list[Any]:
    """Register Habit→Event scheduling endpoints."""

    @rt("/habits/schedule-events")
    @boundary_handler()
    async def schedule_events(
        request: Request, uid: str, auto_create: bool = False, days_ahead: int = 7
    ) -> JSONResponse:
        """
        Schedule recurring events for a habit.
        Requires authentication.

        Query params:
            uid: Habit UID
            auto_create: If True, create events; if False, return templates only
            days_ahead: How many days to schedule ahead (default: 7)
        """
        user_uid = require_authenticated_user(request)
        user_context = UserContext(user_uid=user_uid)

        return await habit_event_scheduler.schedule_events_for_habit(
            habit_uid=uid, user_context=user_context, auto_create=auto_create, days_ahead=days_ahead
        )

    @rt("/habits/event-templates")
    @boundary_handler()
    async def event_templates(request: Request, uid: str) -> JSONResponse:
        """
        Get event templates for a habit without creating them.
        Requires authentication.

        Query params:
            uid: Habit UID
        """
        user_uid = require_authenticated_user(request)
        user_context = UserContext(user_uid=user_uid)

        return await habit_event_scheduler.schedule_events_for_habit(
            habit_uid=uid,
            user_context=user_context,
            auto_create=False,  # Templates only
        )

    return [schedule_events, event_templates]


# ---------------------------------------------------------------------------
# Goals Intelligence - Predictive Analytics (extension)
# ---------------------------------------------------------------------------


def create_goals_intelligence_routes(
    _app: Any, rt: Any, goals_intelligence: Any, habits: Any
) -> list[Any]:
    """Register predictive goal analytics endpoints."""

    @rt("/goals/predict-success")
    @boundary_handler()
    async def predict_success(uid: str, lookback_days: int = 30) -> JSONResponse:
        """
        Predict goal success probability using habit data and historical patterns.

        Query params:
            uid: Goal UID
            lookback_days: Days of historical data to analyze (default: 30)
        """
        return await goals_intelligence.predict_goal_success(
            goal_uid=uid,
            lookback_days=lookback_days,
            habits_service=habits,
        )

    @rt("/goals/habit-impact")
    @boundary_handler()
    async def habit_impact(uid: str) -> JSONResponse:
        """
        Analyze which habits have the most impact on goal success.

        Query params:
            uid: Goal UID
        """
        return await goals_intelligence.analyze_habit_impact(
            goal_uid=uid,
            habits_service=habits,
        )

    @rt("/goals/risk-assessment")
    @boundary_handler()
    async def risk_assessment(uid: str) -> JSONResponse:
        """
        Assess risk factors for goal achievement.

        Query params:
            uid: Goal UID
        """
        prediction_result = await goals_intelligence.predict_goal_success(
            goal_uid=uid,
            habits_service=habits,
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

    return [predict_success, habit_impact, risk_assessment]


# ---------------------------------------------------------------------------
# Principle Alignment - Motivational Intelligence (extension)
# ---------------------------------------------------------------------------


def create_principle_alignment_routes(_app: Any, rt: Any, principles: Any) -> list[Any]:
    """Register principle alignment and motivational intelligence endpoints."""

    @rt("/principles/list")
    @boundary_handler()
    async def list_principles(request: Request) -> JSONResponse:
        """Get all principles for the authenticated user."""
        user_uid = require_authenticated_user(request)
        return await principles.get_user_principles(user_uid=user_uid)

    @rt("/principles/goal-alignment")
    @boundary_handler()
    async def goal_alignment(request: Request, goal_uid: str) -> JSONResponse:
        """
        Assess how well a goal aligns with the authenticated user's principles.

        Args:
            goal_uid: Goal UID
        """
        user_uid = require_authenticated_user(request)
        return await principles.assess_goal_alignment(goal_uid=goal_uid, user_uid=user_uid)

    @rt("/principles/habit-alignment")
    @boundary_handler()
    async def habit_alignment(request: Request, habit_uid: str) -> JSONResponse:
        """
        Assess how well a habit aligns with the authenticated user's principles.

        Args:
            habit_uid: Habit UID
        """
        user_uid = require_authenticated_user(request)
        return await principles.assess_habit_alignment(habit_uid=habit_uid, user_uid=user_uid)

    @rt("/principles/motivational-profile")
    @boundary_handler()
    async def motivational_profile(request: Request) -> JSONResponse:
        """
        Get comprehensive motivational profile for the authenticated user.
        Includes principle hierarchy, value patterns, and alignment insights.
        """
        user_uid = require_authenticated_user(request)
        return await principles.get_motivational_profile(user_uid=user_uid)

    @rt("/principles/suggest-actions")
    @boundary_handler()
    async def suggest_actions(request: Request, context: str = "general") -> JSONResponse:
        """
        Suggest actions that align with the authenticated user's principles.

        Args:
            context: Context for suggestions (e.g., "goal", "habit", "general")
        """
        user_uid = require_authenticated_user(request)

        return Result.ok(
            {
                "user_uid": user_uid,
                "context": context,
                "suggestions": [],
                "message": "Principle-aligned action suggestions - implementation pending",
            }
        )

    return [list_principles, goal_alignment, habit_alignment, motivational_profile, suggest_actions]


# ---------------------------------------------------------------------------
# DomainRouteConfig + Multi-Factory wiring
# ---------------------------------------------------------------------------

ORCHESTRATION_CONFIG = DomainRouteConfig(
    domain_name="orchestration",
    primary_service_attr="goal_task_generator",
    api_factory=create_goal_task_routes,
)


def create_orchestration_routes(app: Any, rt: Any, services: Any, _sync_service=None) -> list[Any]:
    """
    Wire orchestration API routes using DomainRouteConfig (Multi-Factory variant).

    Primary: goal_task_generator routes via DomainRouteConfig.
    Extensions: habit_event, goals_intelligence, principle_alignment factories
    appended conditionally after primary registration.

    See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
    """
    routes = register_domain_routes(app, rt, services, ORCHESTRATION_CONFIG)

    if services and services.habit_event_scheduler:
        routes.extend(create_habit_event_routes(app, rt, services.habit_event_scheduler))

    if services and services.goals_intelligence:
        routes.extend(
            create_goals_intelligence_routes(app, rt, services.goals_intelligence, services.habits)
        )

    if services and services.principles:
        routes.extend(create_principle_alignment_routes(app, rt, services.principles))

    return routes


__all__ = ["create_orchestration_routes"]
