"""
Common Query Route Factory
===========================

Factory for generating common query patterns across all domains.

Patterns Supported:
- GET /api/{domain}/user - Get user's entities (session auth, or ADMIN for other users)
- GET /api/{domain}/goal?goal_uid=... - Get entities by goal (with ownership check)
- GET /api/{domain}/habit?habit_uid=... - Get entities by habit (with ownership check)
- GET /api/{domain}/by-status?status=... - Filter by status (auth required)

Example Usage:
    query_factory = CommonQueryRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        user_service=user_service,  # For admin queries on other users
        goals_service=goals_service,  # For goal filter ownership
        habits_service=habits_service,  # For habit filter ownership
        supports_goal_filter=True,
    )
    query_factory.register_routes(app, rt)

This generates:
- GET /api/tasks/user (auth required, returns user's own tasks)
- GET /api/tasks/user?user_uid=... (ADMIN only, returns specified user's tasks)
- GET /api/tasks/goal?goal_uid=... (auth + goal ownership check)
- GET /api/tasks/by-status?status=active (auth required)

Security Model:
- /user route without param: Derives user_uid from session (auth required)
- /user route with user_uid param: ADMIN role required
- /goal, /habit routes: Verify user owns the goal/habit before filtering
"""

from typing import Any, cast

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories.route_helpers import verify_entity_ownership
from core.models.enums import ContentScope, UserRole
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.query_factory")


class CommonQueryRouteFactory:
    """
    Factory for common query route patterns with proper security.

    Generates standardized query routes that are consistent across domains:
    - /user: User's own entities (no param) or any user's entities (with param, ADMIN only)
    - Goal/habit filter queries (auth + ownership verification)
    - Status filter queries (auth required)

    Security aligned with CRUDRouteFactory and StatusRouteFactory patterns.
    """

    def __init__(
        self,
        service: Any,
        domain_name: str,
        user_service: Any | None = None,
        goals_service: Any | None = None,
        habits_service: Any | None = None,
        supports_goal_filter: bool = False,
        supports_habit_filter: bool = False,
        scope: ContentScope = ContentScope.USER_OWNED,
        base_path: str | None = None,
    ) -> None:
        """
        Initialize query route factory.

        Args:
            service: Domain service with query methods
            domain_name: Domain name (e.g., "tasks", "goals", "habits")
            user_service: UserService for admin role verification when querying other users
            goals_service: GoalsService for goal ownership verification
            habits_service: HabitsService for habit ownership verification
            supports_goal_filter: Whether domain supports filtering by goal
            supports_habit_filter: Whether domain supports filtering by habit
            scope: Content ownership model (default: ContentScope.USER_OWNED).
                  - ContentScope.USER_OWNED: User-specific content with ownership verification
                  - ContentScope.SHARED: Public/shared content (no ownership checks)
            base_path: Custom base path (default: /api/{domain_name})
        """
        self.service = service
        self.domain = domain_name
        self.user_service = user_service
        self.goals_service = goals_service
        self.habits_service = habits_service
        self.supports_goal_filter = supports_goal_filter
        self.supports_habit_filter = supports_habit_filter
        # Convert ContentScope enum to boolean for internal use
        self.verify_ownership = scope == ContentScope.USER_OWNED
        self.base_path = base_path or f"/api/{domain_name}"

    def register_routes(self, _app, rt):
        """Register all common query routes. Returns route descriptions for diagnostics."""
        route_descriptions = []

        # Single user query route (handles both own data and admin queries)
        route_descriptions.append(self._register_user_query_route(rt))

        # Register status filter route (auth required)
        route_descriptions.append(self._register_status_filter_route(rt))

        # Conditionally register goal filter
        if self.supports_goal_filter:
            route_descriptions.append(self._register_goal_filter_route(rt))

        # Conditionally register habit filter
        if self.supports_habit_filter:
            route_descriptions.append(self._register_habit_filter_route(rt))

        logger.info(
            f"CommonQueryRouteFactory registered {len(route_descriptions)} "
            f"query routes for {self.domain}: {route_descriptions}"
        )

        return route_descriptions

    def _register_user_query_route(self, rt) -> str:
        """
        Register GET /api/{domain}/user route.

        - Without user_uid param: Returns current user's entities (auth required)
        - With user_uid param: Returns specified user's entities (ADMIN only)

        Calls: service.get_user_{domain}(user_uid)
        Example: tasks_service.get_user_tasks(user_uid)
        """
        service = self.service
        domain = self.domain
        user_service = self.user_service

        @rt(f"{self.base_path}/user")
        @boundary_handler()
        async def get_user_entities_route(
            request: Request, user_uid: str | None = None
        ) -> Result[Any]:
            # Get {domain} for a user.
            # Always require authentication
            auth_user_uid = require_authenticated_user(request)

            # Determine which user's data to fetch
            if user_uid is None:
                # No param: return current user's data
                target_user_uid = auth_user_uid
            else:
                # Param provided: require ADMIN role
                if not user_service:
                    return Result.fail(
                        Errors.system(
                            message="Admin queries require user_service configuration",
                            operation=f"get_user_{domain}",
                        )
                    )

                user_result = await user_service.get_user(auth_user_uid)
                if user_result.is_error or not user_result.value:
                    return Result.fail(
                        Errors.forbidden(
                            action=f"access {domain} for other users",
                            reason="User not found",
                        )
                    )

                if not user_result.value.has_permission(UserRole.ADMIN):
                    return Result.fail(
                        Errors.forbidden(
                            action=f"access {domain} for other users",
                            reason="Requires ADMIN role",
                        )
                    )

                target_user_uid = user_uid

            # Call service method: get_user_{domain}()
            method_name = f"get_user_{domain}"
            try:
                method = getattr(service, method_name)
            except AttributeError:
                return Result.fail(
                    Errors.system(
                        message=f"Service method {method_name} not found",
                        operation=f"get_user_{domain}",
                    )
                )

            return cast("Result[Any]", await method(target_user_uid))

        return f"GET {self.base_path}/user[?user_uid=...]"

    def _register_status_filter_route(self, rt) -> str:
        """
        Register GET /api/{domain}/by-status?status=... route.

        Requires authentication. Returns only the authenticated user's entities.

        Calls: service.find_{domain}(filters={"status": ..., "user_uid": ...})
        Example: tasks_service.find_tasks(filters={"status": "active", "user_uid": "user_mike"})
        """
        service = self.service
        domain = self.domain

        @rt(f"{self.base_path}/by-status")
        @boundary_handler()
        async def get_by_status_route(request: Request, status: str) -> Result[Any]:
            # Get {domain} filtered by status.
            # Require authentication
            user_uid = require_authenticated_user(request)

            # Call service method: find_{domain}(filters={"status": ...})
            method_name = f"find_{domain}"
            try:
                method = getattr(service, method_name)
            except AttributeError:
                return Result.fail(
                    Errors.system(
                        message=f"Service method {method_name} not found",
                        operation=f"get_{domain}_by_status",
                    )
                )

            # Include user_uid in filter to ensure ownership
            return cast(
                "Result[Any]", await method(filters={"status": status, "user_uid": user_uid})
            )

        return f"GET {self.base_path}/by-status?status=..."

    def _register_goal_filter_route(self, rt) -> str:
        """
        Register GET /api/{domain}/goal?goal_uid=... route.

        Requires authentication. If goals_service is provided and verify_ownership
        is True, verifies the user owns the goal before returning results.

        Calls: service.get_{domain}_for_goal(goal_uid)
        Example: tasks_service.get_tasks_for_goal(goal_uid)
        """
        service = self.service
        domain = self.domain
        goals_service = self.goals_service
        verify_ownership = self.verify_ownership

        @rt(f"{self.base_path}/goal")
        @boundary_handler()
        async def get_for_goal_route(request: Request, goal_uid: str) -> Result[Any]:
            # Get {domain} related to a goal.
            # Require authentication
            user_uid = require_authenticated_user(request)

            # Verify user owns the goal if goals_service is provided
            if goals_service and verify_ownership:
                ownership_error = await verify_entity_ownership(
                    goals_service, goal_uid, user_uid, domain
                )
                if ownership_error:
                    return ownership_error

            # Call service method: get_{domain}_for_goal()
            method_name = f"get_{domain}_for_goal"
            try:
                method = getattr(service, method_name)
            except AttributeError:
                return Result.fail(
                    Errors.system(
                        message=f"Service method {method_name} not found",
                        operation=f"get_{domain}_for_goal",
                    )
                )

            return cast("Result[Any]", await method(goal_uid))

        return f"GET {self.base_path}/goal?goal_uid=..."

    def _register_habit_filter_route(self, rt) -> str:
        """
        Register GET /api/{domain}/habit?habit_uid=... route.

        Requires authentication. If habits_service is provided and verify_ownership
        is True, verifies the user owns the habit before returning results.

        Calls: service.get_{domain}_for_habit(habit_uid)
        Example: events_service.get_events_for_habit(habit_uid)
        """
        service = self.service
        domain = self.domain
        habits_service = self.habits_service
        verify_ownership = self.verify_ownership

        @rt(f"{self.base_path}/habit")
        @boundary_handler()
        async def get_for_habit_route(request: Request, habit_uid: str) -> Result[Any]:
            # Get {domain} related to a habit.
            # Require authentication
            user_uid = require_authenticated_user(request)

            # Verify user owns the habit if habits_service is provided
            if habits_service and verify_ownership:
                ownership_error = await verify_entity_ownership(
                    habits_service, habit_uid, user_uid, domain
                )
                if ownership_error:
                    return ownership_error

            # Call service method: get_{domain}_for_habit()
            method_name = f"get_{domain}_for_habit"
            try:
                method = getattr(service, method_name)
            except AttributeError:
                return Result.fail(
                    Errors.system(
                        message=f"Service method {method_name} not found",
                        operation=f"get_{domain}_for_habit",
                    )
                )

            return cast("Result[Any]", await method(habit_uid))

        return f"GET {self.base_path}/habit?habit_uid=..."


__all__ = ["CommonQueryRouteFactory"]
