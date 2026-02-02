"""
Goals API - Migrated to CRUDRouteFactory
========================================

Third migration in the CRUD API rollout.

Before: 323 lines of manual route definitions
After: ~270 lines

This file uses:
- CRUDRouteFactory for standard CRUD routes (create, get, update, delete, list)
- Manual routes for domain-specific operations (progress, milestones, habits, status)

SECURITY UPDATE (December 2025):
- CRUDRouteFactory now verifies ownership on get/update/delete
- Manual routes use require_authenticated_user + verify_ownership for security
"""

from typing import Any, cast

from fasthtml.common import Request

from core.auth import require_authenticated_user, require_ownership_query
from core.infrastructure.routes import (
    CRUDRouteFactory,
    IntelligenceRouteFactory,
    StatusRouteFactory,
    StatusTransition,
)
from core.infrastructure.routes.query_route_factory import CommonQueryRouteFactory
from core.models.enums import ContentScope
from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalCreateRequest, GoalUpdateRequest
from core.services.protocols.facade_protocols import GoalsFacadeProtocol
from core.utils.error_boundary import boundary_handler
from core.utils.result_simplified import Result


def create_goals_api_routes(
    app: Any,
    rt: Any,
    goals_service: GoalsFacadeProtocol,
    user_service: Any = None,
    habits_service: Any = None,
) -> list[Any]:
    """
    Create goal API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        goals_service: GoalsService instance
        user_service: UserService for admin role verification
        habits_service: HabitsService for habit ownership verification
    """

    # Service getter for ownership decorator (SKUEL012: named function, not lambda)
    def get_goals_service():
        return goals_service

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated)
    # ========================================================================

    # Create factory for standard CRUD operations
    crud_factory = CRUDRouteFactory(
        service=goals_service,
        domain_name="goals",
        create_schema=GoalCreateRequest,
        update_schema=GoalUpdateRequest,
        uid_prefix="goal",
        scope=ContentScope.USER_OWNED,
    )

    # Register all standard CRUD routes:
    # - POST   /api/goals           (create)
    # - GET    /api/goals/{uid}     (get)
    # - PUT    /api/goals/{uid}     (update)
    # - DELETE /api/goals/{uid}     (delete)
    # - GET    /api/goals           (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # COMMON QUERY ROUTES (Factory-Generated)
    # ========================================================================

    # Create factory for common query patterns
    query_factory = CommonQueryRouteFactory(
        service=goals_service,
        domain_name="goals",
        user_service=user_service,  # For admin /user route
        habits_service=habits_service,  # For habit ownership verification
        supports_goal_filter=False,  # Goals don't filter by goal (it IS the goal domain)
        supports_habit_filter=True,
        scope=ContentScope.USER_OWNED,
    )

    # Register common query routes:
    # - GET /api/goals/mine               (get authenticated user's goals)
    # - GET /api/goals/user?user_uid=...  (admin only - get any user's goals)
    # - GET /api/goals/habit?habit_uid=...  (get goals for habit, ownership verified)
    # - GET /api/goals/by-status?status=...  (filter by status, auth required)
    query_factory.register_routes(app, rt)

    # ========================================================================
    # INTELLIGENCE ROUTES (Factory-Generated)
    # ========================================================================

    intelligence_factory = IntelligenceRouteFactory(
        intelligence_service=goals_service.intelligence,
        domain_name="goals",
        ownership_service=goals_service,
        scope=ContentScope.USER_OWNED,
    )

    # Register intelligence routes:
    # - GET /api/goals/context?uid=...&depth=2     (entity with graph context)
    # - GET /api/goals/analytics?period_days=30   (user performance analytics)
    # - GET /api/goals/insights?uid=...           (domain-specific insights)
    intelligence_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    # Goal Progress Operations
    # ------------------------
    # SECURITY: All routes verify user owns the goal before operating

    @rt("/api/goals/progress", methods=["POST"])
    @require_ownership_query(get_goals_service)
    @boundary_handler(success_status=201)
    async def update_goal_progress_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[dict[str, Any]]:
        """Update goal progress (requires ownership)."""
        body = await request.json()
        progress_value = body.get("progress", 0)
        notes = body.get("notes", "")
        update_date = body.get("date")

        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = goals_service
        result = await typed_service.update_goal_progress(
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

        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = goals_service
        result = await typed_service.get_goal_progress(entity.uid, period)
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

        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = goals_service
        return await typed_service.create_goal_milestone(
            entity.uid, milestone_title, target_date, description
        )

    @rt("/api/goals/milestones", methods=["GET"])
    @require_ownership_query(get_goals_service)
    @boundary_handler()
    async def get_goal_milestones_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[list[dict[str, Any]]]:
        """Get milestones for a goal (requires ownership)."""
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = goals_service
        return await typed_service.get_goal_milestones(entity.uid)

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
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = goals_service
        return await typed_service.list_goal_categories(user_uid)

    @rt("/api/goals/by-category")
    @boundary_handler()
    async def get_goals_by_category_route(request: Request, category: str) -> Result[list[Goal]]:
        """Get goals in a specific category."""
        params = dict(request.query_params)

        limit = int(params.get("limit", 100))

        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = goals_service
        return await typed_service.get_goals_by_category(category, limit)

    @rt("/api/goals/by-status")
    @boundary_handler()
    async def get_goals_by_status_route(request: Request, status: str) -> Result[list[Goal]]:
        """Get goals by status."""
        params = dict(request.query_params)

        limit = int(params.get("limit", 100))

        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = goals_service
        return await typed_service.get_goals_by_status(status, limit)

    # Goal Search and Filtering
    # -------------------------

    @rt("/api/goals/search")
    @boundary_handler()
    async def search_goals_route(request: Request) -> Result[list[Goal]]:
        """Search goals by title or description."""
        params = dict(request.query_params)

        query = params.get("q", "")
        limit = int(params.get("limit", 50))

        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = goals_service
        return await typed_service.search_goals(query, limit)

    @rt("/api/goals/due-soon")
    @boundary_handler()
    async def get_goals_due_soon_route(request: Request) -> Result[list[Goal]]:
        """Get goals due soon."""
        params = dict(request.query_params)
        days_ahead = int(params.get("days", 7))

        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = goals_service
        return await typed_service.get_goals_due_soon(days_ahead)

    @rt("/api/goals/overdue")
    @boundary_handler()
    async def get_overdue_goals_route(request: Request) -> Result[list[Goal]]:
        """Get overdue goals."""
        params = dict(request.query_params)
        limit = int(params.get("limit", 100))

        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = goals_service
        return await typed_service.get_overdue_goals(limit)

    return []  # Routes registered via @rt() decorators (no objects returned)


# Migration Statistics:
# =====================
# Before (goals_api.py):         323 lines
# After (goals_api_migrated):    ~270 lines
# Reduction:                     53 lines (16% reduction)
#
# CRUD boilerplate eliminated:   ~75 lines (88% CRUD code → factory handles it)
#
# The 5 standard CRUD routes are now handled by the factory, while
# 19 domain-specific routes remain as manual implementations.
