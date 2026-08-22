"""
Ownership Route Factory - Ownership-Verified Domain Routes
==========================================================

Generates routes that require entity ownership verification before operating.
Eliminates the repetitive decorator+parse+call pattern found across all 6
Activity Domain API files.

PROBLEM SOLVED:
    Before: 24+ nearly-identical ownership routes across 6 domains
    After: 1 factory, 6 configurations

DOMAINS USING THIS FACTORY:
    - Habits: track, untrack, streak, progress
    - Events: conflicts, attendees GET, recurring GET
    - Goals: progress, milestones, habits
    - Tasks: assign, dependencies, completion impact
    - Principles: expressions, alignment, links
    - Choices: decision, options, evaluate, analyze

SECURITY:
    All routes automatically:
    1. Require authentication
    2. Verify ownership before operating
    3. Return 404 for entities user doesn't own

USAGE:
    ```python
    ownership_factory = OwnershipRouteFactory(
        service=habits_service,
        domain_name="habits",
        routes=[
            OwnershipRoute(
                path="/api/habits/track",
                method_name="track_habit",
                request_schema=TrackHabitRequest,
                schema_extra_uid_field="habit_uid",
            ),
            OwnershipRoute(
                path="/api/habits/streak",
                method_name="get_habit_streak",
            ),
        ],
    )
    ownership_factory.register_routes(app, rt)
    ```
"""

__version__ = "1.0"

from dataclasses import dataclass
from typing import Any, Protocol, cast

from pydantic import BaseModel

from adapters.inbound.auth.session import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.route_factories.route_helpers import verify_entity_ownership
from core.models.enums import ContentScope
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


# ============================================================================
# PROTOCOLS
# ============================================================================


class OwnershipOperations(Protocol):
    """Protocol for services supporting ownership verification.

    Services must implement verify_ownership for security.
    """

    async def verify_ownership(self, uid: str, user_uid: UserUID) -> Result[Any]:
        """Verify user owns the entity."""
        ...


# ============================================================================
# CONFIGURATION
# ============================================================================


@dataclass(frozen=True)
class OwnershipRoute:
    """Configuration for a single ownership-verified route.

    Supports three call patterns:

    1. GET passthrough: ``service.method(entity_uid)``
       Config: ``request_schema=None, query_params=None``

    2. GET with query params: ``service.method(entity_uid, period="month")``
       Config: ``request_schema=None, query_params={"period": "month"}``

    3. POST with Pydantic model: ``parse_json_body(req, Schema)`` ->
       ``service.method(model)``
       Config: ``request_schema=Schema, schema_extra_uid_field="habit_uid"``

    Attributes:
        path: Route path (e.g., "/api/habits/track")
        method_name: Service method to call (e.g., "track_habit")
        request_schema: Pydantic model for POST body validation (None for GET)
        schema_extra_uid_field: Field name to inject entity UID into when
            parsing JSON body (e.g., "habit_uid")
        methods: HTTP methods (default: ["POST"] if schema, ["GET"] otherwise)
        query_params: Query parameter defaults for GET routes.
            Dict of {param_name: default_value}. Values are extracted from
            request.query_params and passed as kwargs to the service method.
        include_user_uid: If True, pass user_uid as keyword argument to the
            service method (for methods that need the caller's identity beyond
            ownership verification)
        success_status: HTTP status code on success (default: 200)

    Examples:
        GET passthrough::

            OwnershipRoute(
                path="/api/habits/streak",
                method_name="get_habit_streak",
            )

        GET with query params::

            OwnershipRoute(
                path="/api/habits/progress",
                method_name="get_habit_progress",
                query_params={"period": "month"},
            )

        POST with Pydantic model::

            OwnershipRoute(
                path="/api/habits/track",
                method_name="track_habit",
                request_schema=TrackHabitRequest,
                schema_extra_uid_field="habit_uid",
            )
    """

    path: str
    method_name: str
    request_schema: type[BaseModel] | None = None
    schema_extra_uid_field: str | None = None
    methods: list[str] | None = None
    query_params: dict[str, Any] | None = None
    include_user_uid: bool = False
    success_status: int = 200
    uid_param: str | None = None


# ============================================================================
# FACTORY
# ============================================================================


class OwnershipRouteFactory:
    """Factory for generating ownership-verified routes.

    Features:
    - Automatic authentication requirement
    - Automatic ownership verification (returns 404 for non-owned entities)
    - Configurable call patterns (GET passthrough, GET with params, POST with model)

    Example::

        factory = OwnershipRouteFactory(
            service=habits_service,
            domain_name="habits",
            routes=[
                OwnershipRoute(
                    path="/api/habits/track",
                    method_name="track_habit",
                    request_schema=TrackHabitRequest,
                    schema_extra_uid_field="habit_uid",
                ),
                OwnershipRoute(
                    path="/api/habits/streak",
                    method_name="get_habit_streak",
                ),
            ],
        )
        factory.register_routes(app, rt)
        # Creates:
        #   POST /api/habits/track?uid=...
        #   GET  /api/habits/streak?uid=...
    """

    def __init__(
        self,
        service: OwnershipOperations,
        domain_name: str,
        routes: list[OwnershipRoute],
        scope: ContentScope = ContentScope.USER_OWNED,
        uid_param: str = "uid",
    ) -> None:
        """Initialize ownership route factory.

        Args:
            service: Service implementing OwnershipOperations protocol
            domain_name: Domain name (e.g., "habits", "goals")
            routes: List of OwnershipRoute configurations
            scope: Content ownership model (default: ContentScope.USER_OWNED).
                  - ContentScope.USER_OWNED: Ownership verification enabled
                  - ContentScope.SHARED: No ownership checks
            uid_param: Default query parameter name for entity UID (e.g., "uid",
                "principle_uid"). Individual routes can override via
                OwnershipRoute.uid_param.
        """
        self.service = service
        self.domain = domain_name
        self.domain_singular = self._singularize(domain_name)
        self.routes_config = routes
        self.verify_ownership = scope == ContentScope.USER_OWNED
        self.uid_param = uid_param

        logger.info(
            f"OwnershipRouteFactory initialized for {domain_name} "
            f"(scope={scope.value}): {[r.path for r in routes]}"
        )

    def _singularize(self, name: str) -> str:
        """Convert plural domain name to singular for error messages."""
        if name.endswith("ies"):
            return name[:-3] + "y"
        if name.endswith("s"):
            return name[:-1]
        return name

    def register_routes(self, _app: Any, rt: Any) -> list[Any]:
        """Register all ownership-verified routes.

        Args:
            _app: FastHTML app (unused but required for interface consistency)
            rt: Route decorator

        Returns:
            List of registered route functions
        """
        registered = []

        for config in self.routes_config:
            route = self._register_route(rt, config)
            registered.append(route)

        logger.info(
            f"Registered {len(registered)} ownership routes for {self.domain}: "
            f"{[r.path for r in self.routes_config]}"
        )

        return registered

    def _register_route(self, rt: Any, config: OwnershipRoute) -> Any:
        """Register a single ownership-verified route.

        Route pattern: {METHOD} {path}?uid=...
        """
        service = self.service
        domain_singular = self.domain_singular
        verify_ownership = self.verify_ownership
        method_name = config.method_name
        # Route-level uid_param overrides factory-level default
        uid_param_name = config.uid_param or self.uid_param

        # Determine HTTP methods
        if config.methods is not None:
            methods = config.methods
        elif config.request_schema is not None:
            methods = ["POST"]
        else:
            methods = ["GET"]

        @rt(config.path, methods=methods)
        @csrf_protected
        @boundary_handler(success_status=config.success_status)
        async def ownership_route(request: Request) -> Result[Any]:
            # 1. Require authentication
            user_uid = require_authenticated_user(request)

            # 2. Extract entity UID from query params
            params = dict(request.query_params)
            entity_uid = params.get(uid_param_name, "")
            if not entity_uid:
                from core.utils.result_simplified import Errors

                return Result.fail(
                    Errors.validation(
                        f"Missing required query parameter: {uid_param_name}",
                        field=uid_param_name,
                    )
                )

            # 3. Verify ownership (if enabled)
            if verify_ownership:
                ownership_error = await verify_entity_ownership(
                    service, entity_uid, user_uid, domain_singular
                )
                if ownership_error:
                    return ownership_error

            # 4. Resolve service method (supports dotted paths like "intelligence.analyze")
            obj: Any = service
            for attr in method_name.split("."):
                obj = getattr(obj, attr)
            service_method = cast("Any", obj)

            if config.request_schema is not None:
                # POST with Pydantic model
                extra = (
                    {config.schema_extra_uid_field: entity_uid}
                    if config.schema_extra_uid_field
                    else None
                )
                result = await parse_json_body(request, config.request_schema, extra=extra)
                if result.is_error:
                    return result

                if config.include_user_uid:
                    return cast(
                        "Result[Any]", await service_method(result.value, user_uid=user_uid)
                    )
                return cast("Result[Any]", await service_method(result.value))

            # GET pattern — type inferred from default value
            kwargs: dict[str, Any] = {}
            if config.query_params is not None:
                for param_name, default in config.query_params.items():
                    raw = params.get(param_name)
                    if raw is None:
                        kwargs[param_name] = default
                    elif isinstance(default, int):
                        try:
                            kwargs[param_name] = int(raw)
                        except (ValueError, TypeError):  # fmt: skip
                            kwargs[param_name] = default
                    elif isinstance(default, bool):
                        kwargs[param_name] = raw.lower() in ("true", "1", "yes", "on")
                    else:
                        kwargs[param_name] = raw

            if config.include_user_uid:
                kwargs["user_uid"] = user_uid

            return cast("Result[Any]", await service_method(entity_uid, **kwargs))

        # Give the function a unique name for debugging
        ownership_route.__name__ = f"{method_name}_route"
        ownership_route.__doc__ = (
            f"Ownership-verified route for {method_name}.\nAuto-generated by OwnershipRouteFactory."
        )

        return ownership_route


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "OwnershipOperations",
    "OwnershipRoute",
    "OwnershipRouteFactory",
]
