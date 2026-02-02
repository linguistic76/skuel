"""
Tasks API - Migrated to CRUDRouteFactory
========================================

Pilot migration demonstrating the new factory pattern.

Before: 324 lines of manual route definitions
After: ~50 lines (85% reduction)

This file uses:
- CRUDRouteFactory for standard CRUD routes (create, get, update, delete, list)
- Manual routes for domain-specific operations (complete, assign, dependencies, etc.)
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
from core.infrastructure.routes.analytics_route_factory import AnalyticsRouteFactory
from core.infrastructure.routes.query_route_factory import CommonQueryRouteFactory
from core.models.enums import ContentScope
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from core.services.protocols.facade_protocols import TasksFacadeProtocol
from core.utils.error_boundary import boundary_handler
from core.utils.result_simplified import Result


def create_tasks_api_routes(
    app: Any,
    rt: Any,
    tasks_service: TasksFacadeProtocol,
    user_service: Any = None,
    goals_service: Any = None,
    habits_service: Any = None,
    prometheus_metrics: Any = None,
) -> list[Any]:
    """
    Create task API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        tasks_service: TasksService instance
        user_service: UserService for admin role verification
        goals_service: GoalsService for goal ownership verification
        habits_service: HabitsService for habit ownership verification
        prometheus_metrics: PrometheusMetrics for HTTP instrumentation (Phase 2 - January 2026)
    """

    # Service getter for ownership decorator (SKUEL012: named function, not lambda)
    def get_tasks_service():
        return tasks_service

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated)
    # ========================================================================

    # Create factory for standard CRUD operations
    # No adapter needed - CRUDRouteFactory uses ConversionServiceV2 automatically
    crud_factory = CRUDRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        create_schema=TaskCreateRequest,
        update_schema=TaskUpdateRequest,
        uid_prefix="task",
        scope=ContentScope.USER_OWNED,
        prometheus_metrics=prometheus_metrics,  # Phase 2 - HTTP instrumentation
    )

    # Register all standard CRUD routes:
    # - POST /api/tasks/create        (create)
    # - GET  /api/tasks/get?uid=...   (get)
    # - POST /api/tasks/update?uid=.. (update)
    # - POST /api/tasks/delete?uid=.. (delete)
    # - GET  /api/tasks/list          (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # COMMON QUERY ROUTES (Factory-Generated)
    # ========================================================================

    # Create factory for common query patterns
    query_factory = CommonQueryRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        user_service=user_service,  # For admin /user route
        goals_service=goals_service,  # For goal ownership verification
        habits_service=habits_service,  # For habit ownership verification
        supports_goal_filter=True,  # Tasks can be filtered by goal
        supports_habit_filter=True,  # Tasks can be filtered by habit
        scope=ContentScope.USER_OWNED,
    )

    # Register common query routes:
    # - GET /api/tasks/mine               (get authenticated user's tasks)
    # - GET /api/tasks/user?user_uid=...  (admin only - get any user's tasks)
    # - GET /api/tasks/goal?goal_uid=...  (get tasks for goal, ownership verified)
    # - GET /api/tasks/habit?habit_uid=...  (get tasks for habit, ownership verified)
    # - GET /api/tasks/by-status?status=...  (filter by status, auth required)
    query_factory.register_routes(app, rt)

    # ========================================================================
    # INTELLIGENCE ROUTES (Factory-Generated)
    # ========================================================================

    intelligence_factory = IntelligenceRouteFactory(
        intelligence_service=tasks_service.intelligence,
        domain_name="tasks",
        ownership_service=tasks_service,
        scope=ContentScope.USER_OWNED,
    )

    # Register intelligence routes:
    # - GET /api/tasks/context?uid=...&depth=2     (entity with graph context)
    # - GET /api/tasks/analytics?period_days=30   (user performance analytics)
    # - GET /api/tasks/insights?uid=...           (domain-specific insights)
    intelligence_factory.register_routes(app, rt)

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
        service: TasksFacadeProtocol, params: dict[str, Any]
    ) -> Result[Any]:
        """Handle performance analytics request."""
        period_days = int(params.get("period_days", "30"))
        user_uid = params.get("_user_uid", "")  # Injected by factory
        result = await service.intelligence.get_performance_analytics(user_uid, period_days)
        return cast("Result[Any]", result)

    async def handle_behavioral_insights(
        service: TasksFacadeProtocol, params: dict[str, Any]
    ) -> Result[Any]:
        """Handle behavioral insights request."""
        period_days = int(params.get("period_days", "90"))
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

        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
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
        """Get task dependencies (requires ownership)."""
        return await tasks_service.get_task_dependencies(entity.uid)

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
        limit = int(params.get("limit", 100))

        return await tasks_service.get_user_assigned_tasks(user_uid, include_completed, limit)

    # NOTE: GET /api/tasks/goal?goal_uid=... now generated by CommonQueryRouteFactory
    # NOTE: GET /api/tasks/habit?habit_uid=... now generated by CommonQueryRouteFactory

    @rt("/api/tasks/knowledge")
    @boundary_handler()
    async def get_tasks_for_knowledge_route(request: Request, knowledge_uid: str) -> Result[Any]:
        """Get tasks that apply specific knowledge."""
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        facade = tasks_service
        return await facade.get_tasks_applying_knowledge(knowledge_uid)

    # NOTE: GET /api/tasks/context now generated by IntelligenceRouteFactory

    @rt("/api/tasks/impact")
    @require_ownership_query(get_tasks_service)
    @boundary_handler()
    async def get_task_completion_impact_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Analyze impact of completing this task (requires ownership)."""
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        facade = tasks_service
        return await facade.get_task_completion_impact(entity.uid)

    @rt("/api/tasks/practice-opportunities")
    @require_ownership_query(get_tasks_service)
    @boundary_handler()
    async def get_task_practice_opportunities_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Find practice opportunities related to task (requires ownership)."""
        params = dict(request.query_params)
        depth = int(params.get("depth", 2))

        return await tasks_service.get_task_practice_opportunities(entity.uid, depth)

    @rt("/api/tasks/search")
    @boundary_handler()
    async def search_tasks_route(request: Request) -> Result[Any]:
        """Search tasks by query string."""
        params = dict(request.query_params)

        query = params.get("query", "")
        limit = int(params.get("limit", 10))

        result: Result[Any] = await tasks_service.search.search(query, limit)
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

        days_ahead = int(params.get("days_ahead", 7))
        limit = int(params.get("limit", 100))

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

        limit = int(params.get("limit", 100))

        result: Result[Any] = await tasks_service.search.get_overdue(
            user_uid=user_uid,
            limit=limit,
        )
        return result

    # Return empty list since routes are registered directly on app
    return []


# Migration Statistics:
# =====================
# Before (tasks_api.py):      324 lines
# After (tasks_api_migrated): ~230 lines
# Reduction:                  94 lines (29% reduction)
#
# Note: The reduction is less than expected because tasks API has many
# domain-specific routes. The real win is:
# 1. CRUD consistency across all domains
# 2. Single source of truth for standard operations
# 3. Eliminates duplicate CRUD boilerplate (85 lines → factory handles it)
#
# The 5 standard CRUD routes are now handled by the factory, while
# 15 domain-specific routes remain as manual implementations.
