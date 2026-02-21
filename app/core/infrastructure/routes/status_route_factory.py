"""
Status Route Factory - Consolidated Status Change Routes
========================================================

Generates status change routes for any domain with ownership verification.

PROBLEM SOLVED:
    Before: 12 nearly-identical status routes across 4 domains
    After: 1 factory, 4 configurations

DOMAINS USING THIS FACTORY:
    - Goals: activate, pause, complete, archive
    - Habits: pause, resume, archive
    - Events: start, complete, cancel
    - Assignments: publish, archive

SECURITY (December 2025):
    All routes automatically:
    1. Require authentication
    2. Verify ownership before status change
    3. Return 404 for entities user doesn't own

USAGE:
    ```python
    # In goals_api.py
    status_factory = StatusRouteFactory(
        service=goals_service,
        domain_name="goals",
        transitions={
            "activate": StatusTransition(target_status="active"),
            "pause": StatusTransition(
                target_status="paused",
                requires_body=True,
                body_fields=["reason", "until_date"],
            ),
            "complete": StatusTransition(target_status="completed"),
            "archive": StatusTransition(target_status="archived"),
        },
    )
    status_factory.register_routes(app, rt)
    ```
"""

__version__ = "1.0"

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from adapters.inbound.auth.session import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from core.infrastructure.routes.route_helpers import verify_entity_ownership
from core.models.enums import ContentScope
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


# ============================================================================
# PROTOCOLS
# ============================================================================


class StatusOperations(Protocol):
    """
    Protocol for services supporting status changes.

    Services must implement verify_ownership for security.
    Status change methods follow naming convention: {action}_{domain}(uid, **kwargs)
    """

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[Any]:
        """Verify user owns the entity."""
        ...


# ============================================================================
# CONFIGURATION
# ============================================================================


@dataclass
class StatusTransition:
    """
    Configuration for a single status transition.

    Attributes:
        target_status: The status value to set (e.g., "active", "paused")
        requires_body: Whether the route expects a JSON body
        body_fields: List of fields to extract from body (optional)
        method_name: Override service method name (default: {action}_{domain})
        success_status: HTTP status code on success (default: 200)
        validate: Optional validation function (body) -> Result[None]
        request_builder: Optional function to build a typed request object
                        Signature: (uid: str, fields: dict) -> RequestObject
                        When provided, the built object is passed as the single
                        argument to the service method instead of **kwargs.

    Examples:
        Simple (uid, **kwargs) pattern:
            StatusTransition(
                target_status="active",
                method_name="activate_goal",
            )

        Typed request object pattern:
            StatusTransition(
                target_status="paused",
                requires_body=True,
                body_fields=["reason", "until_date"],
                request_builder=lambda uid, fields: PauseHabitRequest(
                    habit_uid=uid,
                    reason=fields.get("reason", "Paused"),
                    until_date=fields.get("until_date"),
                ),
                method_name="pause_habit",
            )
    """

    target_status: str
    requires_body: bool = False
    body_fields: list[str] = field(default_factory=list)
    method_name: str | None = None
    success_status: int = 200
    validate: Callable[[dict[str, Any]], Result[None]] | None = None
    request_builder: Callable[[str, dict[str, Any]], Any] | None = None


# ============================================================================
# FACTORY
# ============================================================================


class StatusRouteFactory:
    """
    Factory for generating status change routes.

    Features:
    - Automatic authentication requirement
    - Automatic ownership verification
    - Configurable transitions per domain
    - Optional body parsing with field extraction
    - Optional validation hooks

    Example:
        ```python
        factory = StatusRouteFactory(
            service=goals_service,
            domain_name="goals",
            transitions={
                "activate": StatusTransition(target_status="active"),
                "pause": StatusTransition(
                    target_status="paused",
                    requires_body=True,
                    body_fields=["reason", "until_date"],
                ),
            },
        )
        factory.register_routes(app, rt)
        # Creates:
        #   POST /api/goals/activate?uid=...
        #   POST /api/goals/pause?uid=...
        ```
    """

    def __init__(
        self,
        service: StatusOperations,
        domain_name: str,
        transitions: dict[str, StatusTransition],
        base_path: str | None = None,
        scope: ContentScope = ContentScope.USER_OWNED,
    ) -> None:
        """
        Initialize status route factory.

        Args:
            service: Service implementing StatusOperations protocol
            domain_name: Domain name (e.g., "goals", "habits")
            transitions: Dict of action -> StatusTransition config
            base_path: Custom base path (default: /api/{domain_name})
            scope: Content ownership model (default: ContentScope.USER_OWNED).
                  - ContentScope.USER_OWNED: User-specific content with ownership verification
                  - ContentScope.SHARED: Public/shared content (no ownership checks)
        """
        self.service = service
        self.domain = domain_name
        self.domain_singular = self._singularize(domain_name)
        self.transitions = transitions
        self.base_path = base_path or f"/api/{domain_name}"
        # Convert ContentScope enum to boolean for internal use
        self.verify_ownership = scope == ContentScope.USER_OWNED

        logger.info(
            f"StatusRouteFactory initialized for {domain_name} "
            f"(scope={scope.value}): {list(transitions.keys())}"
        )

    def _singularize(self, name: str) -> str:
        """Convert plural domain name to singular for method names."""
        if name.endswith("ies"):
            return name[:-3] + "y"  # entries -> entry, categories -> category
        if name.endswith("s"):
            return name[:-1]  # goals -> goal, tasks -> task, habits -> habit
        return name

    def register_routes(self, _app, rt) -> list[Any]:
        """
        Register all status change routes.

        Args:
            _app: FastHTML app (unused but required for interface)
            rt: Route decorator

        Returns:
            List of registered route functions
        """
        routes = []

        for action, config in self.transitions.items():
            route = self._register_status_route(rt, action, config)
            routes.append(route)

        logger.info(
            f"Registered {len(routes)} status routes for {self.domain}: "
            f"{list(self.transitions.keys())}"
        )

        return routes

    def _register_status_route(self, rt, action: str, config: StatusTransition) -> Any:
        """
        Register a single status change route.

        Route pattern: POST /api/{domain}/{action}?uid=...
        """
        service = self.service
        domain_singular = self.domain_singular
        verify_ownership = self.verify_ownership

        # Determine service method name
        # Convention: {action}_{domain_singular} e.g., activate_goal, pause_habit
        method_name = config.method_name or f"{action}_{domain_singular}"

        @rt(f"{self.base_path}/{action}")
        @boundary_handler(success_status=config.success_status)
        async def status_route(request, uid: str) -> Result[Any]:
            f"""
            {action.title()} {domain_singular} (requires ownership).

            Auto-generated by StatusRouteFactory.
            Target status: {config.target_status}
            """

            # 1. Require authentication
            user_uid = require_authenticated_user(request)

            # 2. Verify ownership (if enabled)
            if verify_ownership:
                ownership_error = await verify_entity_ownership(
                    service, uid, user_uid, domain_singular
                )
                if ownership_error:
                    return ownership_error

            # 3. Parse body if required
            fields: dict[str, Any] = {}
            if config.requires_body:
                body = await request.json()

                # Run validation if provided
                if config.validate:
                    validation = config.validate(body)
                    if validation and validation.is_error:
                        return validation

                # Extract specified fields
                for field_name in config.body_fields:
                    if field_name in body:
                        fields[field_name] = body[field_name]

            # 4. Call service method
            service_method = getattr(service, method_name, None)
            if service_method is None:
                logger.error(f"Service method {method_name} not found on {type(service).__name__}")
                from core.utils.result_simplified import Errors

                return Result.fail(
                    Errors.system(
                        message=f"Status action '{action}' not implemented",
                        operation=method_name,
                    )
                )

            # Two patterns supported:
            # 1. request_builder: Build typed request object, pass as single arg
            # 2. kwargs: Pass uid + extracted fields as keyword arguments
            if config.request_builder:
                # Typed request object pattern (e.g., HabitsService)
                request_obj = config.request_builder(uid, fields)
                result = await service_method(request_obj)
            else:
                # Simple (uid, **kwargs) pattern (e.g., GoalsService)
                result = await service_method(uid, **fields)

            logger.info(f"{action.title()}d {domain_singular}: {uid} for user {user_uid}")
            return result

        # Give the function a unique name for debugging
        status_route.__name__ = f"{action}_{domain_singular}_route"
        status_route.__doc__ = (
            f"{action.title()} a {domain_singular}.\n\n"
            f"Target status: {config.target_status}\n"
            f"Requires body: {config.requires_body}\n"
            f"Auto-generated by StatusRouteFactory."
        )

        return status_route


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "StatusOperations",
    "StatusRouteFactory",
    "StatusTransition",
]
