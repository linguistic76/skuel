"""
Orchestration Routes - Cross-Domain Orchestration Services
==========================================================

Wires orchestration API routes using DomainRouteConfig (Multi-Factory variant).

Primary service: goal_task_generator (Goal→Task generation)
Extension factories:
- create_goal_task_bulk_routes: Goal→Task generation across the user's goals (2 endpoints)
- create_habit_event_routes: Habit→Event scheduling (2 endpoints)
- create_goals_intelligence_routes: Predictive goal analytics (3 endpoints)
- create_principle_alignment_routes: Principle alignment & motivational intel (5 endpoints)

Every route requires a session. A route that takes a goal or habit uid verifies
that the caller owns it before the service behind it reads it — another user's
uid is answered as a uid that names nothing (ADR-085 § 1, route-mediated
``verify_ownership``). The three routes that write are POST behind the CSRF check.

Routes:
- POST /goals/generate-tasks - Generate tasks from a goal
- GET  /goals/task-templates - Get task templates for a goal
- POST /goals/generate-tasks-all - Generate tasks for all active goals
- GET  /goals/critical-tasks - Next critical tasks across all active goals
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

See: /docs/patterns/OWNERSHIP_VERIFICATION.md
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.route_factories.route_helpers import (
    parse_bool_query_param,
    parse_int_query_param,
    verify_entity_ownership,
)
from core.models.event.event_dto import EventDTO
from core.models.principle.principle import Principle
from core.models.task.task_dto import TaskDTO
from core.ports.query_types import GoalRiskAssessment
from core.services.goals.goals_intelligence_service import GoalPrediction, HabitImpactAnalysis
from core.services.principles.principles_alignment_service import (
    AlignmentAssessment,
    MotivationalProfile,
)
from core.services.user import UserContext
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import GoalTaskGeneratorOperations, HabitEventSchedulerOperations
    from core.ports.service_protocols import OwnershipVerifier
    from core.services.goals.goals_intelligence_service import GoalsIntelligenceService
    from core.services.principles_service import PrinciplesService
    from core.services.user_service import UserService

# The most days one scheduling request may reach ahead: a daily habit writes one
# event per day, so this is the ceiling on what a single request creates.
_MAX_SCHEDULE_DAYS_AHEAD = 90


def _require_verifier(verifier: OwnershipVerifier | None, routes: str) -> OwnershipVerifier:
    """The service that owner-verifies ``routes``' uid — registration fails without one."""
    if verifier is None:
        raise ValueError(
            f"{routes} routes take a uid and cannot be registered without the "
            "service that verifies its owner"
        )
    return verifier


# ---------------------------------------------------------------------------
# Goal → Task Generation (primary service)
# ---------------------------------------------------------------------------


def create_goal_task_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    goal_task_generator: GoalTaskGeneratorOperations,
    goals: OwnershipVerifier | None,
) -> None:
    """Register Goal→Task generation endpoints."""
    goals = _require_verifier(goals, "Goal→Task")

    @rt("/goals/generate-tasks", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def generate_tasks(request: Request, uid: str) -> Result[list[TaskDTO]]:
        """
        Generate tasks for a goal based on milestones, knowledge requirements, and habits.
        Requires authentication; the goal is the caller's own.

        Query params:
            uid: Goal UID
            auto_create: If true, create tasks; otherwise return templates only
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(goals, uid, user_uid, "goal")
        if ownership_error:
            return ownership_error
        auto_create = parse_bool_query_param(request.query_params, "auto_create")

        return await goal_task_generator.generate_tasks_for_goal(
            goal_uid=uid, user_context=UserContext(user_uid=user_uid), auto_create=auto_create
        )

    @rt("/goals/task-templates", methods=["GET"])
    @boundary_handler()
    async def task_templates(request: Request, uid: str) -> Result[list[TaskDTO]]:
        """
        Get task templates for a goal without creating them.
        Requires authentication; the goal is the caller's own.

        Query params:
            uid: Goal UID
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(goals, uid, user_uid, "goal")
        if ownership_error:
            return ownership_error

        return await goal_task_generator.generate_tasks_for_goal(
            goal_uid=uid,
            user_context=UserContext(user_uid=user_uid),
            auto_create=False,  # Templates only
        )


# ---------------------------------------------------------------------------
# Goal → Task Bulk Generation (extension)
# ---------------------------------------------------------------------------


def create_goal_task_bulk_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    goal_task_generator: GoalTaskGeneratorOperations,
    user_service: UserService,
) -> None:
    """Register bulk Goal→Task generation endpoints.

    Both act on the caller's own active goals, read from the caller's context.

    Routes:
        POST /goals/generate-tasks-all  — Generate tasks for all active goals
        GET  /goals/critical-tasks      — Next critical tasks across all goals
    """

    @rt("/goals/generate-tasks-all", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def generate_tasks_all(request: Request) -> Result[dict[str, list[TaskDTO]]]:
        """Generate tasks for all active goals.

        Query params:
            auto_create: If true, create tasks; otherwise return templates only
        """
        user_uid = require_authenticated_user(request)
        auto_create = parse_bool_query_param(request.query_params, "auto_create")
        ctx_result = await user_service.get_user_context(user_uid)
        if ctx_result.is_error:
            return Result.fail(ctx_result)
        return await goal_task_generator.generate_tasks_for_all_goals(ctx_result.value, auto_create)

    @rt("/goals/critical-tasks", methods=["GET"])
    @boundary_handler()
    async def critical_tasks(request: Request) -> Result[list[TaskDTO]]:
        """Next critical tasks across all active goals, prioritised by urgency.

        Query params:
            limit: Max results (default 5)
        """
        user_uid = require_authenticated_user(request)
        limit = parse_int_query_param(
            request.query_params, "limit", default=5, minimum=1, maximum=50
        )
        ctx_result = await user_service.get_user_context(user_uid)
        if ctx_result.is_error:
            return Result.fail(ctx_result)
        return await goal_task_generator.generate_next_critical_tasks(ctx_result.value, limit)


# ---------------------------------------------------------------------------
# Habit → Event Scheduling (extension)
# ---------------------------------------------------------------------------


def create_habit_event_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    habit_event_scheduler: HabitEventSchedulerOperations,
    habits: OwnershipVerifier | None,
) -> None:
    """Register Habit→Event scheduling endpoints."""
    habits = _require_verifier(habits, "Habit→Event")

    @rt("/habits/schedule-events", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def schedule_events(request: Request, uid: str) -> Result[list[EventDTO]]:
        """
        Schedule recurring events for a habit.
        Requires authentication; the habit is the caller's own.

        Query params:
            uid: Habit UID
            auto_create: If true, create events; otherwise return templates only
            days_ahead: How many days to schedule ahead (the scheduler's configured
                horizon when absent; at most 90)
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(habits, uid, user_uid, "habit")
        if ownership_error:
            return ownership_error
        auto_create = parse_bool_query_param(request.query_params, "auto_create")
        # 0 = not asked: the scheduler's configured horizon applies.
        days_ahead = parse_int_query_param(
            request.query_params,
            "days_ahead",
            default=0,
            minimum=0,
            maximum=_MAX_SCHEDULE_DAYS_AHEAD,
        )

        return await habit_event_scheduler.schedule_events_for_habit(
            habit_uid=uid,
            user_context=UserContext(user_uid=user_uid),
            auto_create=auto_create,
            days_ahead=days_ahead or None,
        )

    @rt("/habits/event-templates", methods=["GET"])
    @boundary_handler()
    async def event_templates(request: Request, uid: str) -> Result[list[EventDTO]]:
        """
        Get event templates for a habit without creating them.
        Requires authentication; the habit is the caller's own.

        Query params:
            uid: Habit UID
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(habits, uid, user_uid, "habit")
        if ownership_error:
            return ownership_error

        return await habit_event_scheduler.schedule_events_for_habit(
            habit_uid=uid,
            user_context=UserContext(user_uid=user_uid),
            auto_create=False,  # Templates only
        )


# ---------------------------------------------------------------------------
# Goals Intelligence - Predictive Analytics (extension)
# ---------------------------------------------------------------------------


def create_goals_intelligence_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    goals_intelligence: GoalsIntelligenceService,
    goals: OwnershipVerifier | None,
) -> None:
    """Register predictive goal analytics endpoints."""
    goals = _require_verifier(goals, "Goal analytics")

    @rt("/goals/predict-success", methods=["GET"])
    @boundary_handler()
    async def predict_success(request: Request, uid: str) -> Result[GoalPrediction]:
        """
        Predict goal success probability using habit data and historical patterns.
        Requires authentication; the goal is the caller's own.

        Query params:
            uid: Goal UID
            lookback_days: Days of historical data to analyze (default: 30)
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(goals, uid, user_uid, "goal")
        if ownership_error:
            return ownership_error
        lookback_days = parse_int_query_param(
            request.query_params, "lookback_days", default=30, minimum=1, maximum=365
        )
        return await goals_intelligence.predict_goal_success(
            goal_uid=uid,
            lookback_days=lookback_days,
        )

    @rt("/goals/habit-impact", methods=["GET"])
    @boundary_handler()
    async def habit_impact(request: Request, uid: str) -> Result[list[HabitImpactAnalysis]]:
        """
        Analyze which habits have the most impact on goal success.
        Requires authentication; the goal is the caller's own.

        Query params:
            uid: Goal UID
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(goals, uid, user_uid, "goal")
        if ownership_error:
            return ownership_error
        return await goals_intelligence.analyze_habit_impact(goal_uid=uid)

    @rt("/goals/risk-assessment", methods=["GET"])
    @boundary_handler()
    async def risk_assessment(request: Request, uid: str) -> Result[GoalRiskAssessment]:
        """
        Assess risk factors for goal achievement.
        Requires authentication; the goal is the caller's own.

        Query params:
            uid: Goal UID
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(goals, uid, user_uid, "goal")
        if ownership_error:
            return ownership_error
        return await goals_intelligence.assess_goal_risk(goal_uid=uid)


# ---------------------------------------------------------------------------
# Principle Alignment - Motivational Intelligence (extension)
# ---------------------------------------------------------------------------


def create_principle_alignment_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    principles: PrinciplesService,
    goals: OwnershipVerifier | None,
    habits: OwnershipVerifier | None,
) -> None:
    """Register principle alignment and motivational intelligence endpoints."""
    goals = _require_verifier(goals, "Goal alignment")
    habits = _require_verifier(habits, "Habit alignment")

    @rt("/principles/list", methods=["GET"])
    @boundary_handler()
    async def list_principles(request: Request) -> Result[list[Principle]]:
        """Get all principles for the authenticated user."""
        user_uid = require_authenticated_user(request)
        return await principles.get_user_principles(user_uid=user_uid)

    @rt("/principles/goal-alignment", methods=["GET"])
    @boundary_handler()
    async def goal_alignment(request: Request, goal_uid: str) -> Result[AlignmentAssessment]:
        """
        Assess how well one of the authenticated user's goals aligns with their principles.

        Args:
            goal_uid: Goal UID
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(goals, goal_uid, user_uid, "goal")
        if ownership_error:
            return ownership_error
        return await principles.assess_goal_alignment(goal_uid=goal_uid, user_uid=user_uid)

    @rt("/principles/habit-alignment", methods=["GET"])
    @boundary_handler()
    async def habit_alignment(request: Request, habit_uid: str) -> Result[AlignmentAssessment]:
        """
        Assess how well one of the authenticated user's habits aligns with their principles.

        Args:
            habit_uid: Habit UID
        """
        user_uid = require_authenticated_user(request)
        ownership_error = await verify_entity_ownership(habits, habit_uid, user_uid, "habit")
        if ownership_error:
            return ownership_error
        return await principles.assess_habit_alignment(habit_uid=habit_uid, user_uid=user_uid)

    @rt("/principles/motivational-profile", methods=["GET"])
    @boundary_handler()
    async def motivational_profile(request: Request) -> Result[MotivationalProfile]:
        """
        Get comprehensive motivational profile for the authenticated user.
        Includes principle hierarchy, value patterns, and alignment insights.
        """
        user_uid = require_authenticated_user(request)
        return await principles.get_motivational_profile(user_uid=user_uid)

    @rt("/principles/suggest-actions", methods=["GET"])
    @boundary_handler()
    async def suggest_actions(
        request: Request, context: str = "general"
    ) -> Result[
        dict[str, Any]
    ]:  # skuel-lint: disable=SKUEL029 -- wrapped by @boundary_handler() which awaits the handler unconditionally (boundary.py)
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


# ---------------------------------------------------------------------------
# DomainRouteConfig + Multi-Factory wiring
# ---------------------------------------------------------------------------

ORCHESTRATION_CONFIG = DomainRouteConfig(
    domain_name="orchestration",
    primary_service_attr="goal_task_generator",
    api_factory=create_goal_task_routes,
    api_related_services={"goals": "goals"},
)


def create_orchestration_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service=None
) -> None:
    """
    Wire orchestration API routes using DomainRouteConfig (Multi-Factory variant).

    Primary: goal_task_generator routes via DomainRouteConfig.
    Extensions: goal_task_bulk, habit_event, goals_intelligence, principle_alignment
    factories appended conditionally after primary registration. Each factory
    whose routes take a uid is handed the facade that owner-verifies it.

    See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
    """
    register_domain_routes(app, rt, services, ORCHESTRATION_CONFIG)

    if services and services.goal_task_generator and services.user:
        create_goal_task_bulk_routes(app, rt, services.goal_task_generator, services.user)

    if services and services.habit_event_scheduler:
        create_habit_event_routes(app, rt, services.habit_event_scheduler, services.habits)

    if services and services.goals:
        create_goals_intelligence_routes(app, rt, services.goals.intelligence, services.goals)

    if services and services.principles:
        create_principle_alignment_routes(
            app, rt, services.principles, services.goals, services.habits
        )


__all__ = ["create_orchestration_routes"]
