"""
CRUD Route Factory - Generic Route Generation (FastHTML-Aligned)
=================================================================

Eliminates 70% of API boilerplate by providing generic CRUD route factories
aligned with FastHTML best practices.

Core Principle: "One factory per domain, zero CRUD duplication"

FastHTML Conventions Applied
----------------------------
1. Function names define routes (no explicit paths)
2. Query parameters preferred over path parameters
3. Type hints enable automatic parameter extraction
4. Minimal ceremony, maximum clarity

Automatic Method Discovery
--------------------------
The factory uses reflection to automatically discover conversion methods:

    Schema Type Name → Conversion Method Name
    "TaskCreateRequest" → "task_create_to_pure"
    "EventCreateRequest" → "event_create_to_pure"

Convention: {Entity}CreateRequest → {entity}_create_to_pure(schema, uid)

This means adding a new entity type requires:
1. Define {Entity}CreateRequest schema
2. Add {entity}_create_to_pure() method to ConversionServiceV2
3. That's it! CRUDRouteFactory automatically discovers it.

Usage:
    factory = CRUDRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        create_schema=TaskCreateRequest,
        update_schema=TaskUpdateRequest
    )
    factory.register_routes(app, rt)

Routes Generated (FastHTML pattern):
    - POST /api/{domain}/create - Create entity
    - GET /api/{domain}/get?uid=... - Get entity by UID
    - POST /api/{domain}/update?uid=... - Update entity
    - POST /api/{domain}/delete?uid=... - Delete entity
    - GET /api/{domain}/list - List entities with pagination
    - GET /api/{domain}/search?query=... - Search entities (optional)

Benefits:
    - Eliminates ~200 lines of boilerplate per domain
    - 100% consistent CRUD behavior across all domains
    - Type-safe with full Pydantic validation
    - Single source of truth for CRUD patterns
    - Zero adapter wrapper code
    - Automatic discovery - no manual registration needed
    - FastHTML conventions throughout
"""

import uuid
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from core.auth.session import get_current_user, require_authenticated_user
from core.infrastructure.routes.route_helpers import check_required_role
from core.models.enums import ContentScope, UserRole
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)

T = TypeVar("T")


# ============================================================================
# PROTOCOLS
# ============================================================================


class CRUDOperations(Protocol[T]):
    """
    Protocol for services implementing CRUD operations.

    Any service implementing these methods can use CRUDRouteFactory.

    PHASE 4 UPDATE: list() method now accepts user_uid for user-specific filtering.
    DECEMBER 2025: Added ownership-verified methods for multi-tenant security.
    """

    async def create(self, entity: T) -> Result[T]:
        """Create a new entity"""
        ...

    async def get(self, uid: str) -> Result[T | None]:
        """Get entity by UID"""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]:
        """Update entity with partial data"""
        ...

    async def delete(self, uid: str) -> Result[bool]:
        """Delete entity by UID"""
        ...

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
        user_uid: str | None = None,  # NEW: User filtering
    ) -> Result[list[T]]:
        """
        List entities with pagination and optional user filtering.

        Args:
            limit: Maximum number of results,
            offset: Pagination offset,
            order_by: Field to sort by,
            order_desc: Sort in descending order,
            user_uid: Filter entities by user (uses graph relationships)

        Returns:
            Result[List[T]]: List of entities
        """
        ...

    # Ownership-verified methods (December 2025)
    async def get_for_user(self, uid: str, user_uid: str) -> Result[T]:
        """Get entity by UID, only if owned by user"""
        ...

    async def update_for_user(self, uid: str, updates: dict[str, Any], user_uid: str) -> Result[T]:
        """Update entity, only if owned by user"""
        ...

    async def delete_for_user(self, uid: str, user_uid: str) -> Result[bool]:
        """Delete entity, only if owned by user"""
        ...


# ============================================================================
# CRUD ROUTE FACTORY
# ============================================================================


class CRUDRouteFactory[T]:
    """
    Generic CRUD route factory - eliminates 70% of API boilerplate.

    Creates standardized routes for:
    - POST /api/{domain}/create - Create entity
    - GET /api/{domain}/get?uid=... - Get entity by UID
    - POST /api/{domain}/update?uid=... - Update entity
    - POST /api/{domain}/delete?uid=... - Delete entity
    - GET /api/{domain}/list - List entities with pagination
    - GET /api/{domain}/search?query=... - Search entities (optional)

    Example:
        factory = CRUDRouteFactory(
            service=tasks_service,
            domain_name="tasks",
            create_schema=TaskCreateRequest,
            update_schema=TaskUpdateRequest
        )
        factory.register_routes(app, rt)
    """

    def __init__(
        self,
        service: CRUDOperations[T],
        domain_name: str,
        create_schema: type[BaseModel],
        update_schema: type[BaseModel],
        base_path: str | None = None,
        enable_search: bool = False,
        uid_prefix: str | None = None,
        search_handler: Callable | None = None,
        scope: ContentScope = ContentScope.USER_OWNED,
        require_role: UserRole | None = None,
        user_service_getter: Callable | None = None,
        entity_converter: Callable[[BaseModel, str, str], Any] | None = None,
        allow_dict_fallback: bool = False,
        prometheus_metrics: Any | None = None,
    ) -> None:
        """
        Initialize CRUD route factory.

        Args:
            service: Service implementing CRUDOperations protocol,
            domain_name: Domain name (e.g., "tasks", "habits"),
            create_schema: Pydantic schema for creation,
            update_schema: Pydantic schema for updates,
            base_path: Custom base path (default: /api/{domain_name}),
            enable_search: Enable search route (default: False),
            uid_prefix: Custom UID prefix (default: {domain_name}),
            search_handler: Custom search handler (default: None),
            scope: Content ownership model (default: ContentScope.USER_OWNED).
                  - ContentScope.USER_OWNED: User-specific content with ownership verification
                  - ContentScope.SHARED: Public/shared content (KU, LS, LP)

                  IMPORTANT: When SHARED, list() passes user_uid=None for
                  unauthenticated requests. Your service MUST handle this:
                  - user_uid=None → return shared/public content
                  - user_uid=None does NOT mean "return everything"

                  Create() ALWAYS requires authentication regardless of scope
                  (shared content can be read publicly, but only authenticated
                  users can create new content).

                  This is orthogonal to require_role. When require_role is set,
                  scope is ignored as role-based access controls everything.
            require_role: Required role for all routes (e.g., UserRole.ADMIN for admin-only domains).
                         When set, bypasses scope - role controls all access.
            user_service_getter: Function returning UserService (required when require_role is set)
            entity_converter: Custom converter function (schema, uid, user_uid) -> entity.
                            If not provided, uses ConversionServiceV2 with dynamic method lookup.
                            ConversionServiceV2 is SKUEL's global conversion utility following
                            the naming convention: {Entity}CreateRequest -> {entity}_create_to_pure.
            allow_dict_fallback: If True, fall back to dict when no converter found (default: False).
                               When False (fail-fast), returns error if no converter exists.
                               Only set to True for rapid prototyping or entities with flexible schemas.
            prometheus_metrics: PrometheusMetrics instance for HTTP instrumentation (Phase 2 - January 2026).
                              If provided, all routes will be instrumented with request count, latency, and error metrics.
        """
        self.service = service
        self.domain = domain_name
        self.create_schema = create_schema
        self.update_schema = update_schema
        # Consistent API path pattern across all route factories
        self.base_path = base_path or f"/api/{domain_name}"
        self.enable_search = enable_search
        self.uid_prefix = uid_prefix or domain_name
        self.search_handler = search_handler
        # Convert ContentScope enum to boolean for internal use
        self.verify_ownership = scope == ContentScope.USER_OWNED
        self.require_role = require_role
        self.user_service_getter = user_service_getter
        self.entity_converter = entity_converter
        self.allow_dict_fallback = allow_dict_fallback
        self.prometheus_metrics = prometheus_metrics

        # Validate require_role configuration
        if require_role and not user_service_getter:
            raise ValueError("user_service_getter is required when require_role is set")

        # When role-restricted, ownership verification is bypassed (role overrides scope)
        if require_role:
            self.verify_ownership = False

        logger.info(
            f"CRUDRouteFactory initialized for {domain_name} "
            f"(scope={scope.value}, role={require_role.value if require_role else 'None'}, "
            f"instrumentation={'enabled' if prometheus_metrics else 'disabled'})"
        )

    def _instrument_handler(
        self, handler: Callable, endpoint: str, success_status: int = 200
    ) -> Callable:
        """
        Wrap handler with Prometheus instrumentation AND boundary handling.

        This method combines:
        - HTTP request instrumentation (request count, latency, errors)
        - Result[T] to JSONResponse conversion (boundary handler pattern)

        Args:
            handler: Original route handler function (returns Result[T])
            endpoint: Endpoint path for metrics labeling
            success_status: HTTP status code for successful results (default 200)

        Returns:
            Wrapped handler that tracks metrics and converts Result[T] to JSONResponse

        Phase 2 (January 2026): Integrated HTTP instrumentation + boundary handling
        """
        if not self.prometheus_metrics:
            # No metrics - just apply boundary handler
            from core.utils.error_boundary import boundary_handler

            return boundary_handler(success_status=success_status)(handler)

        # Apply combined instrumentation + boundary handling
        from core.infrastructure.monitoring import instrument_with_boundary_handler

        return instrument_with_boundary_handler(
            self.prometheus_metrics, endpoint, success_status=success_status
        )(handler)

    def register_routes(self, _app, rt):
        """
        Register all CRUD routes using FastHTML conventions.

        Args:
            app: FastHTML application instance
            rt: Route decorator

        Registers (FastHTML pattern - function names = routes):
            - POST /{domain}/create - Create entity
            - GET /{domain}/get?uid=... - Get by UID
            - POST /{domain}/update?uid=... - Update entity
            - POST /{domain}/delete?uid=... - Delete entity
            - GET /{domain}/list - List with pagination
            - GET /{domain}/search?query=... - Search (optional)
        """
        self._register_create_route(rt)
        self._register_get_route(rt)
        self._register_update_route(rt)
        self._register_delete_route(rt)
        self._register_list_route(rt)

        if self.enable_search:
            self._register_search_route(rt)

        logger.info(
            f"✅ CRUD routes registered for {self.domain} at {self.base_path} (FastHTML-aligned)"
        )

    def _register_create_route(self, rt) -> Any:
        """
        Register create route: POST /{domain}/create

        FastHTML Convention: Function name 'create' becomes route '/create'
        Request body: Validated by create_schema
        Response: Created entity (201 status)

        SECURITY POLICY (January 2026):
        Create ALWAYS requires authentication, even when verify_ownership=False.
        This is intentional: shared entities (KU, LP) can be READ publicly but
        can only be CREATED by authenticated users. This prevents:
        - Anonymous spam content creation
        - Untraceable content (no user_uid for audit)
        - Abuse of shared content systems

        If you need truly anonymous content creation, you must implement
        a custom route that explicitly handles that case.
        """
        service = self.service
        create_schema = self.create_schema
        uid_prefix = self.uid_prefix
        domain = self.domain
        entity_converter = self.entity_converter
        allow_dict_fallback = self.allow_dict_fallback
        factory = self  # Capture self for nested function

        async def create(request) -> Result[T]:
            """Create new entity"""
            # Role check (returns Result.fail on authorization failure)
            role_check = await check_required_role(
                request, factory.require_role, factory.user_service_getter, factory.domain
            )
            if role_check.is_error:
                return role_check

            body = await request.json()

            # Pydantic validation
            schema = create_schema.model_validate(body)

            # Generate UID
            uid = f"{uid_prefix}:{uuid.uuid4().hex[:12]}"

            # Extract user_uid from session (FAIL-FAST: raises 401 if not authenticated)
            user_uid = require_authenticated_user(request)
            logger.debug(f"Creating {domain} with user_uid={user_uid}")

            # Convert schema to entity using injected converter or ConversionServiceV2
            if entity_converter:
                # Use injected converter (explicit dependency)
                entity = entity_converter(schema, uid, user_uid)
            else:
                # Default: Use ConversionServiceV2 (SKUEL's global conversion utility)
                # This follows the naming convention: {Entity}CreateRequest -> {entity}_create_to_pure
                from core.services.conversion_service import ConversionServiceV2

                schema_type = type(schema).__name__
                entity_name = schema_type.replace("CreateRequest", "").lower()
                method_name = f"{entity_name}_create_to_pure"

                converter_method = getattr(ConversionServiceV2, method_name, None)

                if converter_method:
                    entity = converter_method(schema, uid, user_uid=user_uid)
                elif allow_dict_fallback:
                    # Explicit opt-in to dict fallback (for prototyping or flexible schemas)
                    entity_data = schema.model_dump()
                    entity_data["uid"] = uid
                    entity_data["user_uid"] = user_uid
                    domain_model_name = schema_type.replace("CreateRequest", "")
                    logger.warning(
                        f"No converter found for {domain_model_name} "
                        f"(method: {method_name}). Using dict fallback (allow_dict_fallback=True)."
                    )
                    entity = entity_data
                else:
                    # Fail-fast: No converter and dict fallback not allowed
                    domain_model_name = schema_type.replace("CreateRequest", "")
                    return Result.fail(
                        Errors.system(
                            message=f"No converter found for {domain_model_name}. "
                            f"Add '{method_name}' to ConversionServiceV2, provide entity_converter, "
                            f"or set allow_dict_fallback=True.",
                            operation="entity_conversion",
                            schema_type=schema_type,
                            expected_method=method_name,
                        )
                    )

            # Call service
            result = await service.create(entity)

            logger.info(f"Created {domain}: {uid} for user {user_uid}")
            return result

        # Apply instrumentation + boundary handling, then register route (Phase 2 - January 2026)
        instrumented = self._instrument_handler(
            create, f"{self.base_path}/create", success_status=201
        )
        return rt(f"{self.base_path}/create")(instrumented)

    def _register_get_route(self, rt) -> Any:
        """
        Register get route: GET /{domain}/get?uid=...

        FastHTML Convention: Query parameters preferred over path parameters
        Response: Entity or 404

        SECURITY (December 2025): When verify_ownership=True, requires authentication
        and verifies the requesting user owns the entity.
        """
        service = self.service
        domain = self.domain
        verify_ownership = self.verify_ownership
        factory = self  # Capture self for nested function

        async def get(request, uid: str) -> Result[T | None]:
            """Get entity by UID (query param) with ownership verification"""
            # Role check (returns Result.fail on authorization failure)
            role_check = await check_required_role(
                request, factory.require_role, factory.user_service_getter, factory.domain
            )
            if role_check.is_error:
                return role_check

            if verify_ownership:
                # Require authentication and verify ownership
                user_uid = require_authenticated_user(request)
                result: Result[T | None] = await service.get_for_user(uid, user_uid)
                logger.debug(f"Retrieved {domain}: {uid} for user {user_uid}")
            else:
                # No ownership check (shared entities like KU, LP)
                result = await service.get(uid)
                logger.debug(f"Retrieved {domain}: {uid} (no ownership check)")

            return result

        # Apply instrumentation + boundary handling, then register route (Phase 2 - January 2026)
        instrumented = self._instrument_handler(get, f"{self.base_path}/get")
        return rt(f"{self.base_path}/get")(instrumented)

    def _register_update_route(self, rt) -> Any:
        """
        Register update route: POST /{domain}/update?uid=...

        FastHTML Convention: POST for all mutations, query params for IDs
        Request body: Validated by update_schema
        Response: Updated entity

        SECURITY (December 2025): When verify_ownership=True, requires authentication
        and verifies the requesting user owns the entity before updating.
        """
        service = self.service
        update_schema = self.update_schema
        domain = self.domain
        verify_ownership = self.verify_ownership
        factory = self  # Capture self for nested function

        async def update(request, uid: str) -> Result[T]:
            """Update entity with partial data and ownership verification"""
            # Role check (returns Result.fail on authorization failure)
            role_check = await check_required_role(
                request, factory.require_role, factory.user_service_getter, factory.domain
            )
            if role_check.is_error:
                return role_check

            # uid extracted from query params via type hint
            body = await request.json()

            # Pydantic validation
            schema = update_schema.model_validate(body)

            # Use Pydantic's model_dump directly (100% dynamic pattern)
            # Only include fields that were actually set
            updates = schema.model_dump(exclude_unset=True)

            # Convert enum values to strings for storage
            from core.services.protocols import get_enum_value

            for key, value in updates.items():
                updates[key] = get_enum_value(value)

            # Call service with or without ownership verification
            if verify_ownership:
                user_uid = require_authenticated_user(request)
                result = await service.update_for_user(uid, updates, user_uid)
                logger.info(f"Updated {domain}: {uid} for user {user_uid}")
            else:
                result = await service.update(uid, updates)
                logger.info(f"Updated {domain}: {uid} (no ownership check)")

            return result

        # Apply instrumentation if metrics enabled, then register route (Phase 2 - January 2026)
        instrumented = self._instrument_handler(update, f"{self.base_path}/update")
        return rt(f"{self.base_path}/update")(instrumented)

    def _register_delete_route(self, rt) -> Any:
        """
        Register delete route: POST /{domain}/delete?uid=...

        FastHTML Convention: POST for mutations (not DELETE verb)
        Response: Success boolean

        SECURITY (December 2025): When verify_ownership=True, requires authentication
        and verifies the requesting user owns the entity before deleting.
        """
        service = self.service
        domain = self.domain
        verify_ownership = self.verify_ownership
        factory = self  # Capture self for nested function

        async def delete(request, uid: str) -> Result[bool]:
            """Delete entity by UID (query param) with ownership verification"""
            # Role check (returns Result.fail on authorization failure)
            role_check = await check_required_role(
                request, factory.require_role, factory.user_service_getter, factory.domain
            )
            if role_check.is_error:
                return role_check

            if verify_ownership:
                user_uid = require_authenticated_user(request)
                result = await service.delete_for_user(uid, user_uid)
                logger.info(f"Deleted {domain}: {uid} for user {user_uid}")
            else:
                result = await service.delete(uid)
                logger.info(f"Deleted {domain}: {uid} (no ownership check)")

            return result

        # Apply instrumentation if metrics enabled, then register route (Phase 2 - January 2026)
        instrumented = self._instrument_handler(delete, f"{self.base_path}/delete")
        return rt(f"{self.base_path}/delete")(instrumented)

    def _register_list_route(self, rt) -> Any:
        """
        Register list route: GET /{domain}/list

        FastHTML Convention: Type hints for automatic parameter extraction
        Query params:
            - limit: Max results (default: 100)
            - offset: Pagination offset (default: 0)
            - order_by: Sort field (optional)
            - order_desc: Sort descending (default: false)

        Response: List of entities with user filtering

        SECURITY (December 2025): When verify_ownership=True, requires authentication.

        SHARED DOMAIN BEHAVIOR (January 2026):
        When verify_ownership=False (shared entities like KU, LP):
        - user_uid may be None for unauthenticated requests
        - The service MUST treat user_uid=None as "return shared/public content"
        - The service MUST NOT return everything in the database when user_uid=None
        - This is the service's responsibility to enforce

        Example service implementation:
            async def list(self, ..., user_uid: str | None = None):
                if user_uid is None:
                    # Return shared/public content only
                    return await self.backend.list(limit=limit, ...)
                else:
                    # Return user's content OR shared content visible to them
                    return await self.backend.list_for_user(user_uid, limit=limit, ...)
        """
        service = self.service
        domain = self.domain
        verify_ownership = self.verify_ownership
        factory = self  # Capture self for nested function

        async def list_entities(
            request,
            limit: int = 100,
            offset: int = 0,
            order_by: str | None = None,
            order_desc: bool = False,
        ) -> Result[list[T]]:
            """List entities with pagination and user filtering"""
            # Role check (returns Result.fail on authorization failure)
            role_check = await check_required_role(
                request, factory.require_role, factory.user_service_getter, factory.domain
            )
            if role_check.is_error:
                return role_check

            # FastHTML extracts query params via type hints

            # Extract user_uid from session (for user-specific filtering)
            if verify_ownership:
                # Require authentication for user-owned entities
                user_uid = require_authenticated_user(request)
            else:
                # Shared domains: pass actual user (or None if unauthenticated)
                # Service MUST treat None as "return shared/public content"
                # (not "return everything" - that would be a security issue)
                user_uid = get_current_user(request)

            # Call service with user filtering
            result = await service.list(
                limit=limit,
                offset=offset,
                order_by=order_by,
                order_desc=order_desc,
                user_uid=user_uid,
            )

            logger.debug(f"Listed {domain}: user={user_uid}, limit={limit}, offset={offset}")
            return result

        # Apply instrumentation if metrics enabled, then register route (Phase 2 - January 2026)
        instrumented = self._instrument_handler(list_entities, f"{self.base_path}/list")
        return rt(f"{self.base_path}/list")(instrumented)

    def _register_search_route(self, rt) -> Any:
        """
        Register search route: GET /{domain}/search?query=...

        FastHTML Convention: Type hints + validation
        Query params:
            - query: Search query string (required)
            - limit: Max results (default: 50)
            - offset: Pagination offset (default: 0)

        Response: List of matching entities
        """
        if not self.search_handler:
            logger.warning(f"Search route enabled for {self.domain} but no search_handler provided")
            return None

        search_handler = self.search_handler
        domain = self.domain
        factory = self  # Capture self for nested function

        async def search(request, query: str, limit: int = 50, offset: int = 0) -> Result[list[T]]:
            """Search entities"""
            # Role check (returns Result.fail on authorization failure)
            role_check = await check_required_role(
                request, factory.require_role, factory.user_service_getter, factory.domain
            )
            if role_check.is_error:
                return role_check

            # FastHTML extracts query params via type hints

            # Validation
            if not query.strip():
                return Result.fail(
                    Errors.validation("query parameter cannot be empty", field="query", value=query)
                )

            # Call custom search handler
            result = await search_handler(query=query, limit=limit, offset=offset)

            logger.debug(f"Searched {domain}: query='{query}', limit={limit}")
            return result

        # Apply instrumentation if metrics enabled, then register route (Phase 2 - January 2026)
        instrumented = self._instrument_handler(search, f"{self.base_path}/search")
        return rt(f"{self.base_path}/search")(instrumented)


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "CRUDOperations",
    "CRUDRouteFactory",
]
