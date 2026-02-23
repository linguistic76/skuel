"""
Goals API - Status and Domain-Specific Routes
==============================================

CRUD, Query, and Intelligence factories are now registered via config in
goals_routes.py.  This file contains only factories and routes that require
runtime closures or domain-specific handler logic:
- StatusRouteFactory (activate/pause/complete/archive transitions)
- Manual domain routes (progress, milestones, habits, categories, search)
"""

from typing import Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user, require_ownership_query
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import (
    StatusRouteFactory,
    StatusTransition,
)
from core.models.enums import ContentScope
from core.models.goal.goal import Goal
from core.ports.facade_protocols import GoalsFacadeProtocol
from core.utils.result_simplified import Result


def create_goals_api_routes(
    app: Any,
    rt: Any,
    goals_service: GoalsFacadeProtocol,
    **_kwargs: Any,
) -> list[Any]:
    """
    Create goal API routes that require runtime closures or domain-specific logic.

    CRUD, Query, and Intelligence routes are registered by register_domain_routes
    before this function is called (see goals_routes.py → GOALS_CONFIG).

    Args:
        app: FastHTML application instance
        rt: Route decorator
        goals_service: GoalsService instance (primary service)
        **_kwargs: Absorbs related services passed by register_domain_routes
    """

    # Service getter for ownership decorator (SKUEL012: named function, not lambda)
    def get_goals_service():
        return goals_service

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    # Goal Progress Operations
    # ------------------------
    # SECURITY: All routes verify user owns the goal before operating

    @rt("/api/goals/progress", methods=["POST"])
    @require_ownership_query(get_goals_service)
    @boundary_handler()
    async def update_goal_progress_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[dict[str, Any]]:
        """Update goal progress (requires ownership)."""
        body = await request.json()
        progress_value = body.get("progress", 0)
        notes = body.get("notes", "")
        update_date = body.get("date")

        result = await goals_service.update_goal_progress(
            entity.uid, progress_value, notes, update_date
        )
        # ProgressResult is a TypedDict, convert to dict[str, Any] for type compatibility
        if result.is_error:
            return Result.fail(result)
        return Result.ok(dict(result.value))

    @rt("/api/goals/progress", methods=["GET"])
    @require_ownership_query(get_goals_service)
    @boundary_handler()
    async def get_goal_progress_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[dict[str, Any]]:
        """Get goal progress history (requires ownership)."""
        params = dict(request.query_params)
        period = params.get("period", "month")

        result = await goals_service.get_goal_progress(entity.uid, period)
        # ProgressResult is a TypedDict, convert to dict[str, Any] for type compatibility
        if result.is_error:
            return Result.fail(result)
        return Result.ok(dict(result.value))

    @rt("/api/goals/milestones", methods=["POST"])
    @require_ownership_query(get_goals_service)
    @boundary_handler(success_status=201)
    async def create_goal_milestone_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[dict[str, Any]]:
        """Create a milestone for a goal (requires ownership)."""
        body = await request.json()
        milestone_title = body.get("title")
        target_date = body.get("target_date")
        description = body.get("description", "")

        return await goals_service.create_goal_milestone(
            entity.uid, milestone_title, target_date, description
        )

    @rt("/api/goals/milestones", methods=["GET"])
    @require_ownership_query(get_goals_service)
    @boundary_handler()
    async def get_goal_milestones_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[list[dict[str, Any]]]:
        """Get milestones for a goal (requires ownership)."""
        return await goals_service.get_goal_milestones(entity.uid)

    # Goal Habits Integration
    # -----------------------
    # SECURITY: All routes verify user owns the goal before operating

    @rt("/api/goals/habits", methods=["POST"])
    @require_ownership_query(get_goals_service)
    @boundary_handler(success_status=201)
    async def link_goal_to_habit_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[bool]:
        """Link a habit to a goal (requires ownership)."""
        body = await request.json()
        habit_uid = body.get("habit_uid")
        contribution_weight = body.get("weight", 1.0)

        return await goals_service.link_goal_to_habit(entity.uid, habit_uid, contribution_weight)

    @rt("/api/goals/habits", methods=["GET"])
    @require_ownership_query(get_goals_service)
    @boundary_handler()
    async def get_goal_habits_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[list[str]]:
        """Get habits linked to a goal (requires ownership)."""
        return await goals_service.get_goal_habits(entity.uid)

    @rt("/api/goals/habits/unlink", methods=["DELETE"])
    @require_ownership_query(get_goals_service)
    @boundary_handler()
    async def unlink_goal_from_habit_route(
        request: Request, user_uid: str, entity: Any, habit_uid: str
    ) -> Result[bool]:
        """Unlink a habit from a goal (requires ownership)."""
        return await goals_service.unlink_goal_from_habit(entity.uid, habit_uid)

    # ========================================================================
    # STATUS ROUTES (Factory-Generated)
    # ========================================================================
    # BEFORE: 4 manual routes (~45 lines) with NO ownership verification
    # AFTER: 1 factory config (~15 lines) with AUTOMATIC ownership verification

    status_factory = StatusRouteFactory(
        service=goals_service,
        domain_name="goals",
        transitions={
            "activate": StatusTransition(
                target_status="active",
                method_name="activate_goal",
            ),
            "pause": StatusTransition(
                target_status="paused",
                requires_body=True,
                body_fields=["reason", "until_date"],
                method_name="pause_goal",
            ),
            "complete": StatusTransition(
                target_status="completed",
                requires_body=True,
                body_fields=["notes", "date"],
                method_name="complete_goal",
            ),
            "archive": StatusTransition(
                target_status="archived",
                requires_body=True,
                body_fields=["reason"],
                method_name="archive_goal",
            ),
        },
        scope=ContentScope.USER_OWNED,
    )
    status_factory.register_routes(app, rt)

    # Goal Categories and Organization
    # --------------------------------

    @rt("/api/goals/categories")
    @boundary_handler()
    async def list_goal_categories_route(request: Request) -> Result[list[str]]:
        """List goal categories for the authenticated user."""
        user_uid = require_authenticated_user(request)
        return await goals_service.list_goal_categories(user_uid)

    @rt("/api/goals/by-category")
    @boundary_handler()
    async def get_goals_by_category_route(request: Request, category: str) -> Result[list[Goal]]:
        """Get goals in a specific category."""
        params = dict(request.query_params)

        limit = int(params.get("limit", 100))

        return await goals_service.get_goals_by_category(category, limit)

    @rt("/api/goals/by-status")
    @boundary_handler()
    async def get_goals_by_status_route(request: Request, status: str) -> Result[list[Goal]]:
        """Get goals by status."""
        params = dict(request.query_params)

        limit = int(params.get("limit", 100))

        return await goals_service.get_goals_by_status(status, limit)

    # Goal Search and Filtering
    # -------------------------

    @rt("/api/goals/search")
    @boundary_handler()
    async def search_goals_route(request: Request) -> Result[list[Goal]]:
        """Search goals by title or description."""
        params = dict(request.query_params)

        query = params.get("q", "")
        limit = int(params.get("limit", 50))

        return await goals_service.search_goals(query, limit)

    @rt("/api/goals/due-soon")
    @boundary_handler()
    async def get_goals_due_soon_route(request: Request) -> Result[list[Goal]]:
        """Get goals due soon."""
        params = dict(request.query_params)
        days_ahead = int(params.get("days", 7))

        return await goals_service.get_goals_due_soon(days_ahead)

    @rt("/api/goals/overdue")
    @boundary_handler()
    async def get_overdue_goals_route(request: Request) -> Result[list[Goal]]:
        """Get overdue goals."""
        params = dict(request.query_params)
        limit = int(params.get("limit", 100))

        return await goals_service.get_overdue_goals(limit)

    return []  # Routes registered via @rt() decorators (no objects returned)
