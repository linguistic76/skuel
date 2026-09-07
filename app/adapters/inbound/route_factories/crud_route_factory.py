"""
CRUD Route Factory - Generic Route Generation (FastHTML-Aligned)
=================================================================

Eliminates 70% of API boilerplate by providing generic CRUD route factories
aligned with FastHTML best practices.

Core Principle: "One factory per domain, zero CRUD duplication"

FastHTML Conventions Applied
----------------------------
1. Routes registered with explicit paths (``base_path`` + suffix), e.g. ``rt(f"{base_path}/create")``
2. Query parameters preferred over path parameters
3. Type hints enable automatic parameter extraction
4. Minimal ceremony, maximum clarity

Entity Conversion
-----------------
Schema → domain model conversion uses a static registry
(``ConversionServiceV2.CONVERTER_REGISTRY``) keyed by Pydantic schema type.
Adding a new entity type requires:

1. Define ``{Entity}CreateRequest`` Pydantic schema
2. Add a ``{entity}_create_to_pure()`` classmethod to ``ConversionServiceV2``
3. Register the mapping in ``ConversionServiceV2.CONVERTER_REGISTRY``

Alternatively, pass an explicit ``entity_converter`` callable to the factory
(or via ``CRUDRouteConfig.entity_converter``) to bypass the registry entirely.

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
    - FastHTML conventions throughout
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypedDict, TypeVar, cast

from pydantic import BaseModel

from adapters.inbound.auth.session import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.route_factories.route_helpers import check_required_role
from core.models.enums import ContentScope, UserRole
from core.models.type_hints import UserUID
from core.models.update_contracts import RawChanges, SupportsToChanges, SupportsToIntent
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)

T = TypeVar("T")


class EntityListPayload[T](TypedDict):
    """JSON shape of the generic list route: paginated entities + total count."""

    items: list[T]
    total: int
    limit: int
    offset: int


# ============================================================================
# PROTOCOLS
# ============================================================================


class CRUDOperations(Protocol[T]):
    """
    Protocol for services implementing CRUD operations.

    Any service implementing these methods can use CRUDRouteFactory.

    UPDATE: list() method now accepts user_uid for user-specific filtering.
    DECEMBER 2025: Added ownership-verified methods for multi-tenant security.
    """

    async def create(self, entity: T) -> Result[T]:
        """Create a new entity"""
        ...

    async def get(self, uid: str) -> Result[T | None]:
        """Get entity by UID"""
        ...

    async def update(self, uid: str, updates: SupportsToChanges) -> Result[T]:
        """Update entity with a typed update value (a ``*UpdateIntent`` or ``RawChanges``)"""
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
        user_uid: UserUID | None = None,  # NEW: User filtering
    ) -> Result[tuple[list[T], int]]:
        """
        List entities with pagination and optional user filtering.

        Args:
            limit: Maximum number of results,
            offset: Pagination offset,
            order_by: Field to sort by,
            order_desc: Sort in descending order,
            user_uid: Filter entities by user (uses graph relationships)

        Returns:
            Result[tuple[list[T], int]]: (entities, total_count) for pagination
        """
        ...

    # Ownership-verified methods (December 2025)
    async def get_for_user(self, uid: str, user_uid: UserUID) -> Result[T]:
        """Get entity by UID, only if owned by user"""
        ...

    async def update_for_user(
        self, uid: str, updates: SupportsToChanges, user_uid: UserUID
    ) -> Result[T]:
        """Update entity, only if owned by user"""
        ...

    async def delete_for_user(
        self, uid: str, user_uid: UserUID, cascade: bool = False
    ) -> Result[bool]:
        """Delete entity, only if owned by user (cascade removes relationships too)"""
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
        role_gates_reads: bool = True,
        user_service_getter: Callable | None = None,
        entity_converter: Callable[[BaseModel, str, str], Any] | None = None,
        allow_dict_fallback: bool = False,
        prometheus_metrics: Any | None = None,
        request_create_method: str | None = None,
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
            search_handler: Custom search handler (default: None). Contract:
                          ``async (query, limit, offset, user_uid) -> Result`` —
                          the route authenticates USER_OWNED callers and passes
                          the requesting user (None for SHARED anonymous browse);
                          the handler owns the audience scoping (ADR-085 G7).
            scope: Content ownership model (default: ContentScope.USER_OWNED).
                  - ContentScope.USER_OWNED: User-specific content with ownership verification
                  - ContentScope.SHARED: Public/shared content (KU, PS, LP)

                  IMPORTANT: When SHARED, list() passes user_uid=None for
                  unauthenticated requests. Your service MUST handle this:
                  - user_uid=None → return shared/public content
                  - user_uid=None does NOT mean "return everything"

                  Create() ALWAYS requires authentication regardless of scope
                  (shared content can be read publicly, but only authenticated
                  users can create new content).

                  Scope and require_role are orthogonal: scope controls ownership
                  verification, require_role controls authorization.
            require_role: Required role for mutation routes (create, update, delete).
                         When role_gates_reads=True (default), also gates read routes.
            role_gates_reads: When True (default), require_role applies to ALL routes.
                            When False, require_role only applies to mutations
                            (create/update/delete) — get/list/search are open to
                            any authenticated user. Use for domains like Groups
                            where teachers mutate but students can read.
            user_service_getter: Function returning UserService (required when require_role is set)
            entity_converter: Custom converter function (schema, uid, user_uid) -> entity.
                            If not provided, looks up the converter from
                            ConversionServiceV2.CONVERTER_REGISTRY by schema type.
            allow_dict_fallback: If True, fall back to dict when no converter found (default: False).
                               When False (fail-fast), returns error if no converter exists.
                               Only set to True for rapid prototyping or entities with flexible schemas.
            prometheus_metrics: PrometheusMetrics instance for HTTP instrumentation.
                              If provided, all routes will be instrumented with request count, latency, and error metrics.
            request_create_method: Name of a request-door create primitive on the
                              service — ``(create_schema, user_uid) -> Result[T]``.
                              When set, the create route hands the VALIDATED REQUEST to
                              that method instead of converting to an entity and calling
                              ``service.create(entity)`` — so request-only link fields
                              (which no entity field can carry) become edges instead of
                              being accepted and silently dropped. All six Activity
                              Domains bind this; resolution is fail-fast at construction.
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
        self.role_gates_reads = role_gates_reads
        self.user_service_getter = user_service_getter
        self.entity_converter = entity_converter
        self.allow_dict_fallback = allow_dict_fallback
        self.prometheus_metrics = prometheus_metrics
        # Resolve the request-door primitive NOW: a config naming a method the
        # service does not expose is a wiring bug, not a per-request condition. The
        # declared signature is the binding's contract — (validated request, session
        # user) -> Result[entity] — so the handler's await and Result handling are
        # checker-validated even though getattr resolves the method dynamically.
        self.request_create: Callable[[BaseModel, UserUID], Awaitable[Result[T]]] | None = None
        if request_create_method is not None:
            method: Callable[[BaseModel, UserUID], Awaitable[Result[T]]] | None = getattr(
                service, request_create_method, None
            )
            if not callable(method):
                raise ValueError(
                    f"request_create_method '{request_create_method}' does not resolve "
                    f"to a callable on {type(service).__name__} — the {domain_name} "
                    f"create route cannot be bound to its request-door primitive"
                )
            self.request_create = method

        # Validate require_role configuration
        if require_role and not user_service_getter:
            raise ValueError("user_service_getter is required when require_role is set")

        logger.info(
            f"CRUDRouteFactory initialized for {domain_name} "
            f"(scope={scope.value}, role={require_role.value if require_role else 'None'}, "
            f"role_gates_reads={role_gates_reads}, "
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

        (January 2026): Integrated HTTP instrumentation + boundary handling
        """
        from adapters.inbound.csrf import csrf_protected

        if not self.prometheus_metrics:
            # No metrics - just apply boundary handler
            from adapters.inbound.boundary import boundary_handler

            return csrf_protected(boundary_handler(success_status=success_status)(handler))

        # Apply combined instrumentation + boundary handling
        from adapters.inbound.boundary import instrument_with_boundary_handler

        return csrf_protected(
            instrument_with_boundary_handler(
                self.prometheus_metrics, endpoint, success_status=success_status
            )(handler)
        )

    def register_routes(self, _app, rt):
        """
        Register all CRUD routes using FastHTML conventions.

        Args:
            app: FastHTML application instance
            rt: Route decorator

        Registers (explicit base_path + suffix per route):
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

        Path: explicit base_path + suffix — rt(f"{base_path}/create")
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
        request_create = self.request_create
        factory = self  # Capture self for nested function

        async def create(request: Request) -> Result[T]:
            """Create new entity"""
            # Role check (returns Result.fail on authorization failure)
            role_check = await check_required_role(
                request, factory.require_role, factory.user_service_getter, factory.domain
            )
            if role_check.is_error:
                return cast("Result[T]", role_check)

            # Parse + validate through the shared helper: a rejected body is
            # ordinary bad input, and `boundary_handler`'s catch-all would
            # otherwise turn the raw ValidationError into a 500.
            parsed = await parse_json_body(request, create_schema)
            if parsed.is_error:
                return Result.fail(parsed)
            schema = parsed.value

            # Extract user_uid from session (FAIL-FAST: raises 401 if not authenticated)
            user_uid = require_authenticated_user(request)
            logger.debug(f"Creating {domain} with user_uid={user_uid}")

            # Request-door binding: hand the validated request to the domain's create
            # primitive (validate -> persist -> edges -> events). The entity path below
            # cannot carry request-only link fields, so a bound domain never walks it.
            if request_create is not None:
                result = await request_create(schema, user_uid)
                if not result.is_error:
                    # T is unbound here; every bound domain returns an entity with a uid.
                    created_uid = getattr(result.value, "uid", "?")
                    logger.info(f"Created {domain}: {created_uid} for user {user_uid}")
                return result

            # Generate UID — underscore form per the separator grammar
            # (generated = `{prefix}_{random}`; the colon shape this factory
            # historically minted was a spelling is_valid_uid itself rejects).
            uid = f"{uid_prefix}_{uuid.uuid4().hex[:12]}"

            # Convert schema to entity using injected converter or registry
            if entity_converter:
                # Use injected converter (explicit dependency)
                entity = entity_converter(schema, uid, user_uid)
            else:
                # Look up converter from ConversionServiceV2.CONVERTER_REGISTRY
                from core.services.conversion_service import ConversionServiceV2

                converter_method = ConversionServiceV2.get_converter(type(schema))

                if converter_method:
                    entity = converter_method(schema, uid, user_uid=user_uid)
                elif allow_dict_fallback:
                    # Explicit opt-in to dict fallback (for prototyping or flexible schemas)
                    schema_type_name = type(schema).__name__
                    entity_data = schema.model_dump()
                    entity_data["uid"] = uid
                    entity_data["user_uid"] = user_uid
                    logger.warning(
                        f"No converter registered for {schema_type_name}. "
                        f"Using dict fallback (allow_dict_fallback=True)."
                    )
                    entity = entity_data
                else:
                    # Fail-fast: No converter and dict fallback not allowed
                    schema_type_name = type(schema).__name__
                    return Result.fail(
                        Errors.system(
                            message=f"No converter registered for {schema_type_name}. "
                            f"Register it in ConversionServiceV2.CONVERTER_REGISTRY, "
                            f"provide entity_converter, or set allow_dict_fallback=True.",
                            operation="entity_conversion",
                            schema_type=schema_type_name,
                        )
                    )

            # Call service
            result = await service.create(entity)

            if not result.is_error:
                logger.info(f"Created {domain}: {uid} for user {user_uid}")
            return result

        # Apply instrumentation + boundary handling, then register route
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

        async def get(request: Request, uid: str) -> Result[T | None]:
            """Get entity by UID (query param) with ownership verification"""
            # Role check — skipped when role_gates_reads=False
            if factory.role_gates_reads:
                role_check = await check_required_role(
                    request, factory.require_role, factory.user_service_getter, factory.domain
                )
                if role_check.is_error:
                    return cast("Result[T | None]", role_check)

            if verify_ownership:
                # Require authentication and verify ownership
                user_uid = require_authenticated_user(request)
                result: Result[T | None] = await service.get_for_user(uid, user_uid)  # type: ignore[assignment]  # Result invariance - T widens to T | None safely
                logger.debug(f"Retrieved {domain}: {uid} for user {user_uid}")
            else:
                # No ownership check (shared entities like KU, LP)
                result = await service.get(uid)
                logger.debug(f"Retrieved {domain}: {uid} (no ownership check)")

            return result

        # Apply instrumentation + boundary handling, then register route
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

        async def update(request: Request, uid: str) -> Result[T]:
            """Update entity with partial data and ownership verification"""
            # Role check (returns Result.fail on authorization failure)
            role_check = await check_required_role(
                request, factory.require_role, factory.user_service_getter, factory.domain
            )
            if role_check.is_error:
                return cast("Result[T]", role_check)

            # uid extracted from query params via type hint; body parsed and
            # validated through the shared helper (see the create route above).
            parsed = await parse_json_body(request, update_schema)
            if parsed.is_error:
                return Result.fail(parsed)
            schema = parsed.value

            # Build the typed update value (ADR-066). Activity Domains' `*UpdateRequest`
            # carry `.to_intent()` → a frozen `*UpdateIntent`; other domains (curriculum,
            # forms, groups, templates) fall back to a `RawChanges` patch from `model_dump`.
            updates: SupportsToChanges
            if isinstance(schema, SupportsToIntent):
                updates = schema.to_intent()
            else:
                from core.utils.type_converters import get_enum_value

                raw = schema.model_dump(exclude_unset=True)
                updates = RawChanges({k: get_enum_value(v) for k, v in raw.items()})

            # Call service with or without ownership verification
            if verify_ownership:
                user_uid = require_authenticated_user(request)
                result = await service.update_for_user(uid, updates, user_uid)
                if not result.is_error:
                    logger.info(f"Updated {domain}: {uid} for user {user_uid}")
            else:
                result = await service.update(uid, updates)
                if not result.is_error:
                    logger.info(f"Updated {domain}: {uid} (no ownership check)")

            return result

        # Apply instrumentation if metrics enabled, then register route
        instrumented = self._instrument_handler(update, f"{self.base_path}/update")
        return rt(f"{self.base_path}/update")(instrumented)

    def _register_delete_route(self, rt) -> Any:
        """
        Register delete route: POST /{domain}/delete?uid=...

        FastHTML Convention: POST for mutations (not DELETE verb)
        Response: Success boolean

        SECURITY (December 2025): When verify_ownership=True, requires authentication
        and verifies the requesting user owns the entity before deleting.

        CASCADE (July 2026, G18): ownership-verified deletes always cascade.
        Every owned entity carries at least the OWNS edge, so a non-cascade
        delete can never succeed from this route — it 422'd unconditionally.
        """
        service = self.service
        domain = self.domain
        verify_ownership = self.verify_ownership
        factory = self  # Capture self for nested function

        async def delete(request: Request, uid: str) -> Result[bool]:
            """Delete entity by UID (query param) with ownership verification"""
            # Role check (returns Result.fail on authorization failure)
            role_check = await check_required_role(
                request, factory.require_role, factory.user_service_getter, factory.domain
            )
            if role_check.is_error:
                return cast("Result[bool]", role_check)

            if verify_ownership:
                user_uid = require_authenticated_user(request)
                result = await service.delete_for_user(uid, user_uid, cascade=True)
                if not result.is_error:
                    logger.info(f"Deleted {domain}: {uid} for user {user_uid}")
            else:
                result = await service.delete(uid)
                if not result.is_error:
                    logger.info(f"Deleted {domain}: {uid} (no ownership check)")

            return result

        # Apply instrumentation if metrics enabled, then register route
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

        Response: EntityListPayload — {items, total, limit, offset}

        SECURITY (December 2025): When verify_ownership=True, requires authentication.

        SHARED DOMAIN BEHAVIOR (January 2026):
        When verify_ownership=False (shared entities like KU, LP):
        - user_uid may be None for unauthenticated requests
        - The service MUST treat user_uid=None as "return shared/public content"
        - The service MUST NOT return everything in the database when user_uid=None
        - This is the service's responsibility to enforce

        Example service implementation:
            async def list(self, ..., user_uid: UserUID | None = None):
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
        ) -> Result[EntityListPayload[T]]:
            """List entities with pagination and user filtering"""
            # Role check — skipped when role_gates_reads=False
            if factory.role_gates_reads:
                role_check = await check_required_role(
                    request, factory.require_role, factory.user_service_getter, factory.domain
                )
                if role_check.is_error:
                    return cast("Result[EntityListPayload[T]]", role_check)

            # FastHTML extracts query params via type hints

            # USER_OWNED: filter by ownership; SHARED: no user filter (OWNS-filtered query
            # would return 0 for shared entities that have no owner relationship).
            user_uid = require_authenticated_user(request) if verify_ownership else None

            # Call service with user filtering
            result = await service.list(
                limit=limit,
                offset=offset,
                order_by=order_by,
                order_desc=order_desc,
                user_uid=user_uid,
            )
            if result.is_error:
                return Result.fail(result)

            entities, total = result.value
            logger.debug(f"Listed {domain}: user={user_uid}, limit={limit}, offset={offset}")
            return Result.ok(
                EntityListPayload(items=entities, total=total, limit=limit, offset=offset)
            )

        # Apply instrumentation if metrics enabled, then register route
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

        Ownership (ADR-085 G7): USER_OWNED domains authenticate the caller and
        the handler receives ``user_uid``; SHARED domains pass ``user_uid=None``
        for anonymous browse. The ``search_handler`` contract is therefore
        ``(query, limit, offset, user_uid) -> Result`` — the handler owns the
        scoping (route through SearchRouter or a visibility-composed search).

        Response: List of matching entities
        """
        if not self.search_handler:
            logger.warning(f"Search route enabled for {self.domain} but no search_handler provided")
            return None

        search_handler = self.search_handler
        domain = self.domain
        verify_ownership = self.verify_ownership
        factory = self  # Capture self for nested function

        async def search(
            request: Request, query: str, limit: int = 50, offset: int = 0
        ) -> Result[list[T]]:
            """Search entities"""
            # Role check — skipped when role_gates_reads=False
            if factory.role_gates_reads:
                role_check = await check_required_role(
                    request, factory.require_role, factory.user_service_getter, factory.domain
                )
                if role_check.is_error:
                    return cast("Result[list[T]]", role_check)

            # FastHTML extracts query params via type hints

            # USER_OWNED: the caller must be authenticated and the handler is
            # handed the requesting user; SHARED: anonymous browse (the
            # handler's visibility declaration decides what None may see).
            user_uid = require_authenticated_user(request) if verify_ownership else None

            # Validation
            if not query.strip():
                return Result.fail(
                    Errors.validation("query parameter cannot be empty", field="query", value=query)
                )

            # Call custom search handler with the requesting user (ADR-085 G7)
            result = await search_handler(
                query=query, limit=limit, offset=offset, user_uid=user_uid
            )

            logger.debug(f"Searched {domain}: query='{query}', limit={limit}, user={user_uid}")
            return cast("Result[Any]", result)

        # Apply instrumentation if metrics enabled, then register route
        instrumented = self._instrument_handler(search, f"{self.base_path}/search")
        return rt(f"{self.base_path}/search")(instrumented)


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "CRUDOperations",
    "CRUDRouteFactory",
]
