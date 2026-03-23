"""
Tasks API - Status, Analytics, and Domain-Specific Routes
=========================================================

CRUD, Query, and Intelligence factories are now registered via config in
tasks_routes.py.  This file contains only factories and routes that require
runtime closures or domain-specific handler logic:
- StatusRouteFactory (complete/uncomplete transitions)
- AnalyticsRouteFactory (custom async handlers)
- Manual domain routes (assign, dependencies, impact, etc.)
"""

from typing import Any, cast

from fasthtml.common import Request

from adapters.inbound.auth import (
    make_service_getter,
    require_authenticated_user,
    require_ownership_query,
)
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import (
    OwnershipRoute,
    OwnershipRouteFactory,
    StatusRouteFactory,
    StatusTransition,
    parse_int_query_param,
)
from adapters.inbound.route_factories.analytics_route_factory import AnalyticsRouteFactory
from core.models.enums import ContentScope
from core.services.tasks_service import TasksService
from core.utils.result_simplified import Errors, Result


def create_tasks_api_routes(
    app: Any,
    rt: Any,
    tasks_service: TasksService,
    user_service: Any = None,
    **_kwargs: Any,
) -> list[Any]:
    """
    Create task API routes that require runtime closures or domain-specific logic.

    CRUD, Query, and Intelligence routes are registered by register_domain_routes
    before this function is called (see tasks_routes.py → TASKS_CONFIG).

    Args:
        app: FastHTML application instance
        rt: Route decorator
        tasks_service: TasksService instance (primary service)
        user_service: UserService for building UserContext
        **_kwargs: Absorbs related services passed by register_domain_routes
    """

    # Service getter for manual ownership routes (SKUEL012: named function, not lambda)
    get_tasks_service = make_service_getter(tasks_service)

    # ========================================================================
    # STATUS ROUTES (Factory-Generated)
    # ========================================================================
    # BEFORE: 2 manual routes (~40 lines) with ownership verification
    # AFTER: 1 factory config (~15 lines) with AUTOMATIC ownership verification

    status_factory = StatusRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        transitions={
            "complete": StatusTransition(
                target_status="completed",
                requires_body=True,
                body_fields=["actual_minutes", "quality_score"],
                method_name="complete_task",
            ),
            "uncomplete": StatusTransition(
                target_status="in_progress",
                method_name="uncomplete_task",
            ),
        },
        scope=ContentScope.USER_OWNED,
    )
    status_factory.register_routes(app, rt)

    # ========================================================================
    # ANALYTICS ROUTES (Factory-Generated)
    # ========================================================================

    async def handle_performance_analytics(
        service: TasksService, params: dict[str, Any]
    ) -> Result[Any]:
        """Handle performance analytics request."""
        period_days = parse_int_query_param(params, "period_days", 30, minimum=1, maximum=365)
        user_uid = params.get("_user_uid", "")  # Injected by factory
        result = await service.intelligence.get_performance_analytics(user_uid, period_days)
        return cast("Result[Any]", result)

    async def handle_behavioral_insights(
        service: TasksService, params: dict[str, Any]
    ) -> Result[Any]:
        """Handle behavioral insights request."""
        period_days = parse_int_query_param(params, "period_days", 90, minimum=1, maximum=365)
        user_uid = params.get("_user_uid", "")  # Injected by factory
        result = await service.intelligence.get_behavioral_insights(user_uid, period_days)
        return cast("Result[Any]", result)

    analytics_factory = AnalyticsRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        analytics_config={
            "performance": {
                "path": "/api/tasks/analytics/performance",
                "handler": handle_performance_analytics,
                "description": "Get task performance analytics",
                "methods": ["GET"],
            },
            "behavioral": {
                "path": "/api/tasks/analytics/behavioral",
                "handler": handle_behavioral_insights,
                "description": "Get behavioral insights from tasks",
                "methods": ["GET"],
            },
        },
    )
    analytics_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================
    # SECURITY: All UID-based routes verify user owns the task before operating

    @rt("/api/tasks/assign")
    @require_ownership_query(get_tasks_service)
    @boundary_handler()
    async def assign_task_route(request: Request, user_uid: str, entity: Any) -> Result[Any]:
        """Assign task to user (requires ownership)."""
        body = await request.json()
        target_user_uid = body.get("user_uid")
        assigned_by = body.get("assigned_by")
        priority_override = body.get("priority_override")

        # Note: method is directly available on TasksService
        facade = tasks_service
        return await facade.assign_task_to_user(
            entity.uid, target_user_uid, assigned_by, priority_override
        )

    @rt("/api/tasks/dependencies", methods=["GET"])
    @require_ownership_query(get_tasks_service)
    @boundary_handler()
    async def get_task_dependencies_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Get task dependencies enriched with user context (readiness, blocking, recommendations)."""
        if not user_service:
            return Result.fail(
                Errors.system(
                    message="User service not available", operation="get_task_dependencies"
                )
            )

        context_result = await user_service.get_user_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        params = dict(request.query_params)
        include_transitive = params.get("include_transitive", "false").lower() in (
            "true",
            "1",
            "yes",
        )
        max_depth = parse_int_query_param(params, "max_depth", 2, minimum=1, maximum=10)

        return await tasks_service.get_task_dependencies_for_user(
            task_uid=entity.uid,
            context=context_result.value,
            include_transitive=include_transitive,
            max_depth=max_depth,
        )

    @rt("/api/tasks/dependencies", methods=["POST"])
    @require_ownership_query(get_tasks_service)
    @boundary_handler()
    async def create_task_dependency_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Create task dependency (requires ownership)."""
        body = await request.json()
        blocks_task_uid = body.get("blocks_task_uid")
        is_hard_dependency = body.get("is_hard_dependency", True)
        dependency_type = body.get("dependency_type", "blocks")

        return await tasks_service.create_task_dependency(
            entity.uid, blocks_task_uid, is_hard_dependency, dependency_type
        )

    # NOTE: GET /api/tasks/user?user_uid=... now generated by CommonQueryRouteFactory

    @rt("/api/tasks/user/assigned")
    @boundary_handler()
    async def get_user_assigned_tasks_route(request: Request, user_uid: str) -> Result[Any]:
        """Get tasks assigned to user."""
        params = dict(request.query_params)

        include_completed = params.get("include_completed", "false").lower() == "true"
        limit = parse_int_query_param(params, "limit", 100, minimum=1, maximum=500)

        return await tasks_service.get_user_assigned_tasks(user_uid, include_completed, limit)

    # NOTE: GET /api/tasks/goal?goal_uid=... now generated by CommonQueryRouteFactory
    # NOTE: GET /api/tasks/habit?habit_uid=... now generated by CommonQueryRouteFactory

    @rt("/api/tasks/knowledge")
    @boundary_handler()
    async def get_tasks_for_knowledge_route(request: Request, knowledge_uid: str) -> Result[Any]:
        """Get tasks that apply specific knowledge."""
        # Note: method is directly available on TasksService
        facade = tasks_service
        return await facade.get_tasks_applying_knowledge(knowledge_uid)

    # NOTE: GET /api/tasks/context now generated by IntelligenceRouteFactory

    # ========================================================================
    # OWNERSHIP ROUTES (Factory-Generated)
    # ========================================================================

    ownership_factory = OwnershipRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        routes=[
            OwnershipRoute(
                path="/api/tasks/impact",
                method_name="get_task_completion_impact",
            ),
            OwnershipRoute(
                path="/api/tasks/practice-opportunities",
                method_name="get_task_practice_opportunities",
                query_params={"depth": 2},
            ),
        ],
    )
    ownership_factory.register_routes(app, rt)

    @rt("/api/tasks/search")
    @boundary_handler()
    async def search_tasks_route(request: Request) -> Result[Any]:
        """Search tasks by query string for the authenticated user."""
        user_uid = require_authenticated_user(request)
        params = dict(request.query_params)

        query = params.get("query", "")
        limit = parse_int_query_param(params, "limit", 10, minimum=1, maximum=100)

        result: Result[Any] = await tasks_service.search.search(query, limit, user_uid=user_uid)
        return result

    # ========================================================================
    # TIME-BASED ROUTES (January 2026)
    # ========================================================================
    # These routes use BaseService.get_due_soon() and get_overdue() methods
    # that were extracted from Goals domain for all Activity Domains.

    @rt("/api/tasks/due-soon", methods=["GET"])
    @boundary_handler()
    async def get_tasks_due_soon_route(request: Request) -> Result[Any]:
        """
        Get tasks due within specified number of days.

        Query Parameters:
            days_ahead: Number of days to look ahead (default 7)
            limit: Maximum results (default 100)

        Returns:
            List of tasks due soon, sorted by due_date ASC (nearest first)
        """
        user_uid = require_authenticated_user(request)
        params = dict(request.query_params)

        days_ahead = parse_int_query_param(params, "days_ahead", 7, minimum=1, maximum=365)
        limit = parse_int_query_param(params, "limit", 100, minimum=1, maximum=500)

        result: Result[Any] = await tasks_service.search.get_due_soon(
            days_ahead=days_ahead,
            user_uid=user_uid,
            limit=limit,
        )
        return result

    @rt("/api/tasks/overdue", methods=["GET"])
    @boundary_handler()
    async def get_tasks_overdue_route(request: Request) -> Result[Any]:
        """
        Get tasks past their due date.

        Query Parameters:
            limit: Maximum results (default 100)

        Returns:
            List of overdue tasks, sorted by due_date ASC (most overdue first)
        """
        user_uid = require_authenticated_user(request)
        params = dict(request.query_params)

        limit = parse_int_query_param(params, "limit", 100, minimum=1, maximum=500)

        result: Result[Any] = await tasks_service.search.get_overdue(
            user_uid=user_uid,
            limit=limit,
        )
        return result

    # Return empty list since routes are registered directly on app
    return []
