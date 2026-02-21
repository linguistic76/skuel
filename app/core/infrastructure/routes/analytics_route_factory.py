"""
Analytics Route Factory
=======================

Factory pattern for creating standardized analytics/insights/stats endpoints.
Eliminates ~800 lines of repetitive analytics route boilerplate across 8 APIs.

Pattern: Read-only endpoints that return analytics data structures

Design Note (Future Consideration):
    This factory is "registry-based" (accepts open config) while CRUD and Status
    factories are "convention-based" (enforce specific patterns via protocols).
    If analytics endpoints start sprawling, consider adding an AnalyticsOperations
    protocol to enforce structure, similar to CRUDOperations.

Handler Contract:
    Handlers MUST return Result[T]. This follows SKUEL's "Results internally,
    exceptions at boundaries" pattern. The @boundary_handler decorator converts
    Result[T] to HTTP responses at the boundary.

Usage:
    # Define handler functions - MUST return Result[T]
    async def get_insights_handler(service, params) -> Result[TaskInsights]:
        return await service.get_task_insights()

    async def get_analytics_handler(service, params) -> Result[CompletionStats]:
        return await service.get_completion_analytics()

    factory = AnalyticsRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        analytics_config={
            "insights": {
                "path": "/api/tasks/insights",
                "handler": get_insights_handler,
                "description": "Get AI-powered task insights"
            },
            "analytics": {
                "path": "/api/tasks/analytics/completion",
                "handler": get_analytics_handler,
                "description": "Get task completion analytics"
            }
        }
    )
    factory.register_routes(app, rt)
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from adapters.inbound.boundary import boundary_handler
from core.infrastructure.routes.route_helpers import check_required_role
from core.models.enums import UserRole
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.analytics_factory")


@dataclass
class AnalyticsEndpoint:
    """Configuration for a single analytics endpoint"""

    path: str
    handler: Callable
    description: str
    methods: list[str] = None
    require_params: list[str] = None

    def __post_init__(self) -> None:
        if self.methods is None:
            self.methods = ["GET"]
        if self.require_params is None:
            self.require_params = []


class AnalyticsRouteFactory:
    """
    Factory for creating analytics/insights/stats endpoints.

    Eliminates repetitive boilerplate by providing standardized patterns for:
    - Insights endpoints: AI-powered pattern analysis
    - Analytics endpoints: Statistical aggregations
    - Stats endpoints: Quick metrics summaries
    - Recommendations: Actionable suggestions
    """

    def __init__(
        self,
        service: Any,
        domain_name: str,
        analytics_config: dict[str, dict[str, Any]],
        base_path: str | None = None,
        require_role: UserRole | None = None,
        user_service_getter: Callable | None = None,
    ) -> None:
        """
        Initialize analytics route factory.

        Args:
            service: Domain service instance,
            domain_name: Domain identifier (e.g., "tasks", "knowledge"),
            analytics_config: Dictionary defining analytics endpoints,
            base_path: Optional base path override (defaults to /api/{domain_name})
            require_role: Required role for all routes (e.g., UserRole.ADMIN for admin-only domains)
            user_service_getter: Function returning UserService (required when require_role is set)
        """
        self.service = service
        self.domain_name = domain_name
        self.base_path = base_path or f"/api/{domain_name}"
        self.require_role = require_role
        self.user_service_getter = user_service_getter

        # Validate require_role configuration
        if require_role and not user_service_getter:
            raise ValueError("user_service_getter is required when require_role is set")

        # Convert dict config to AnalyticsEndpoint objects
        self.endpoints: list[AnalyticsEndpoint] = []
        for key, config in analytics_config.items():
            self.endpoints.append(
                AnalyticsEndpoint(
                    path=config.get("path"),
                    handler=config.get("handler"),
                    description=config.get("description", f"Get {key} for {domain_name}"),
                    methods=config.get("methods", ["GET"]),
                    require_params=config.get("require_params", []),
                )
            )

        role_mode = f", requires {require_role.value}" if require_role else ""
        logger.debug(
            f"AnalyticsRouteFactory initialized for {domain_name} with {len(self.endpoints)} endpoints{role_mode}"
        )

    def register_routes(self, _app, rt) -> list[Callable]:
        """
        Register all analytics routes on the application.

        Args:
            app: FastHTML application instance
            rt: Router instance

        Returns:
            List of registered route functions
        """
        routes = []

        for endpoint in self.endpoints:
            route_func = self._create_route_handler(endpoint)

            # Register route with FastHTML
            for method in endpoint.methods:
                rt(endpoint.path, methods=[method])(route_func)

            routes.append(route_func)
            logger.debug(f"Registered analytics route: {endpoint.methods} {endpoint.path}")

        logger.info(f"Analytics routes registered for {self.domain_name}: {len(routes)} endpoints")
        return routes

    def _create_route_handler(self, endpoint: AnalyticsEndpoint) -> Callable:
        """
        Create a route handler function for an analytics endpoint.

        Args:
            endpoint: Analytics endpoint configuration

        Returns:
            Async route handler function
        """
        factory = self  # Capture self for nested function

        @boundary_handler()
        async def route_handler(request) -> Result[Any]:
            """Auto-generated analytics endpoint handler"""
            try:
                # Role check (returns Result[None])
                role_check = await check_required_role(
                    request, factory.require_role, factory.user_service_getter, factory.domain_name
                )
                if role_check.is_error:
                    return role_check

                # Extract query parameters
                params = dict(request.query_params)

                # Validate required parameters
                for param in endpoint.require_params:
                    if param not in params:
                        return Result.fail(
                            Errors.validation(
                                message=f"Missing required parameter: {param}",
                                field=param,
                            )
                        )

                # Call the service handler (must return Result[T])
                return await endpoint.handler(self.service, params)

            except Exception as e:
                logger.error(f"Error in analytics endpoint {endpoint.path}: {e}")
                return Result.fail(
                    Errors.system(message=f"Failed to get analytics: {e!s}", exception=e)
                )

        # Set function metadata for debugging (use full path to avoid collisions)
        sanitized_path = endpoint.path.lstrip("/").replace("/", "_")
        route_handler.__name__ = f"{self.domain_name}_{sanitized_path}"
        route_handler.__doc__ = endpoint.description

        return route_handler


# Export
__all__ = ["AnalyticsEndpoint", "AnalyticsRouteFactory"]
