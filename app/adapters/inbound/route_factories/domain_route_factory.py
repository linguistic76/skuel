"""
Domain Route Factory - Configuration-Driven Route Registration
==============================================================

Eliminates boilerplate in *_routes.py files by providing a single
configurable registration function.

Before: 6 files x ~80 lines = 480 lines of near-identical code
After: 6 configurations x ~15 lines = 90 lines

Sub-config fields (crud, query, intelligence) move formulaic factory
instantiation out of api_factory and into the config.  Factories that
require runtime closures or domain-specific handlers (Status, Analytics,
manual routes) remain in api_factory.

Usage:
    from adapters.inbound.route_factories import (
        create_activity_domain_route_config,
        register_domain_routes,
    )

    TASKS_CONFIG = create_activity_domain_route_config(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=create_tasks_api_routes,
        ui_factory=create_tasks_ui_routes,
        create_schema=TaskCreateRequest,
        update_schema=TaskUpdateRequest,
        uid_prefix="task",
        supports_goal_filter=True,
        supports_habit_filter=True,
        api_related_services={
            "user_service": "user",
            "goals_service": "goals",
            "habits_service": "habits",
        },
        prometheus_metrics_attr="prometheus_metrics",
    )

    def create_tasks_routes(app, rt, services, _sync_service=None):
        return register_domain_routes(app, rt, services, TASKS_CONFIG)
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from services_bootstrap import Services

# ============================================================================
# Sub-config dataclasses (frozen — static, module-level safe)
# ============================================================================


@dataclass(frozen=True)
class CRUDRouteConfig:
    """Static parameters for CRUDRouteFactory.

    Supports non-activity domains via scope/require_role/user_service_attr.
    Activity Domains use the defaults (USER_OWNED, no role requirement).

    See: /docs/patterns/ROUTE_FACTORIES.md
    """

    create_schema: type
    update_schema: type
    uid_prefix: str
    prometheus_metrics_attr: str | None = None
    # Non-activity domain support (defaults match Activity Domain behavior)
    scope: ContentScope = ContentScope.USER_OWNED
    require_role: UserRole | None = None
    role_gates_reads: bool = True  # When False, get/list skip role check (e.g., Groups)
    user_service_attr: str | None = None  # Services container attr for user_service_getter
    # Explicit converter: (schema, uid, user_uid) -> domain_model.
    # When None, CRUDRouteFactory falls back to ConversionServiceV2.CONVERTER_REGISTRY.
    entity_converter: Callable[..., Any] | None = None
    # Name of the request-door create primitive on the primary service —
    # (create_schema, user_uid) -> Result[entity]. When set, the create route calls it
    # with the VALIDATED REQUEST instead of converting to an entity, so request-only
    # link fields become edges instead of silently dropping. A string (not a callable)
    # because configs are module-level statics built before services exist; resolved
    # fail-fast at CRUDRouteFactory construction. Activity Domains: REQUIRED (see
    # create_activity_domain_route_config). Non-activity domains: None = entity path.
    request_create_method: str | None = None


@dataclass(frozen=True)
class QueryRouteConfig:
    """Static parameters for CommonQueryRouteFactory.

    See: /docs/patterns/ROUTE_FACTORIES.md
    """

    supports_goal_filter: bool = False
    supports_habit_filter: bool = False


@dataclass(frozen=True)
class IntelligenceRouteConfig:
    """Configuration for IntelligenceRouteFactory.

    Activity Domains use the default (USER_OWNED).
    Curriculum Domains (PS, LP, Exercise) use SHARED.

    See: /docs/patterns/ROUTE_FACTORIES.md
    """

    scope: ContentScope = ContentScope.USER_OWNED


# ============================================================================
# Main config
# ============================================================================


@dataclass
class DomainRouteConfig:
    """
    Configuration for domain route registration.

    Attributes:
        domain_name: Human-readable domain name for logging (e.g., "tasks", "goals")
        primary_service_attr: Attribute name on services container (e.g., "tasks", "goals")
        api_factory: Optional function to create API routes - signature:
            (app, rt, primary_service, **related_services) -> list[Any]
        ui_factory: Optional function to create UI routes - signature:
            (app, rt, primary_service, **ui_related_services) -> list[Any]
        api_related_services: Mapping of {kwarg_name: container_attr} for API factory.
            Keys must match parameter names in api_factory's signature.
            Values must be the exact attribute name on the services container.
            A warning is logged if any value resolves to None at registration time.
        ui_related_services: Same mapping convention for UI factory.
        crud: When set, CRUDRouteFactory is instantiated and registered before api_factory.
        query: When set, CommonQueryRouteFactory is instantiated and registered before api_factory.
        intelligence: When set (sentinel), IntelligenceRouteFactory is registered before api_factory.
    """

    domain_name: str
    primary_service_attr: str
    # Factory return is widened to `list[Any] | None` because ~half of the
    # ~140 factories register via decorators and return None — the runtime
    # `or []` in register_domain_routes handles both shapes.
    api_factory: Callable[..., list[Any] | None] | None = None
    ui_factory: Callable[..., list[Any] | None] | None = None
    api_related_services: dict[str, str] = field(default_factory=dict)
    ui_related_services: dict[str, str] = field(default_factory=dict)
    # Config-driven factory fields (all default None = backward compatible)
    crud: CRUDRouteConfig | None = None
    query: QueryRouteConfig | None = None
    intelligence: IntelligenceRouteConfig | None = None


def register_domain_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: "Services | None",
    config: DomainRouteConfig,
) -> list[Any]:
    """
    Register domain routes using configuration.

    Provides consistent:
    - Service extraction with None checks
    - Validation with early return
    - Config-driven factory instantiation (CRUD, Query, Intelligence)
    - Route wiring (API + optional UI)
    - Structured logging

    Config-driven factories run BEFORE api_factory so that api_factory only
    needs to handle factories with runtime closures (Status, Analytics) and
    any manual routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        services: Services container
        config: Domain route configuration

    Returns:
        List of registered routes (empty if primary service missing)
    """
    # Import factories here to avoid circular imports at module level
    from adapters.inbound.route_factories.crud_route_factory import CRUDRouteFactory
    from adapters.inbound.route_factories.intelligence_route_factory import IntelligenceRouteFactory
    from adapters.inbound.route_factories.query_route_factory import CommonQueryRouteFactory

    logger = get_logger(f"skuel.routes.{config.domain_name}")

    # 1. Extract primary service
    primary_service = getattr(services, config.primary_service_attr, None) if services else None

    if not primary_service:
        logger.warning(
            f"{config.domain_name.title()} routes registered without "
            f"{config.primary_service_attr} service"
        )
        return []

    # 2. Extract related services for API factory (kwarg_name -> value)
    _missing = object()
    api_related: dict[str, Any] = {}
    if config.api_factory:
        for kwarg_name, container_attr in config.api_related_services.items():
            value = getattr(services, container_attr, _missing) if services else None
            if value is _missing:
                logger.warning(
                    f"{config.domain_name}: api_related_services['{kwarg_name}'] "
                    f"-> '{container_attr}' not found on services container. "
                    f"Verify the attribute name."
                )
                value = None
            api_related[kwarg_name] = value

    registered: list[Any] = []

    # 3. Config-driven factory instantiation (order: CRUD → Query → Intelligence)
    if config.crud:
        prometheus_metrics = (
            getattr(services, config.crud.prometheus_metrics_attr)
            if config.crud.prometheus_metrics_attr
            else None
        )
        # Build user_service_getter closure if role-gated
        crud_user_service_getter = None
        if config.crud.require_role and config.crud.user_service_attr:
            _user_svc = getattr(services, config.crud.user_service_attr, None)

            def _make_getter(svc: Any) -> Callable:
                def getter() -> Any:
                    return svc

                return getter

            crud_user_service_getter = _make_getter(_user_svc)

        CRUDRouteFactory(
            service=primary_service,
            domain_name=config.domain_name,
            create_schema=config.crud.create_schema,
            update_schema=config.crud.update_schema,
            uid_prefix=config.crud.uid_prefix,
            scope=config.crud.scope,
            require_role=config.crud.require_role,
            role_gates_reads=config.crud.role_gates_reads,
            user_service_getter=crud_user_service_getter,
            entity_converter=config.crud.entity_converter,
            prometheus_metrics=prometheus_metrics,
            request_create_method=config.crud.request_create_method,
        ).register_routes(app, rt)

    if config.query:
        CommonQueryRouteFactory(
            service=primary_service,
            domain_name=config.domain_name,
            user_service=api_related.get("user_service"),
            goals_service=api_related.get("goals_service"),
            habits_service=api_related.get("habits_service"),
            supports_goal_filter=config.query.supports_goal_filter,
            supports_habit_filter=config.query.supports_habit_filter,
            scope=ContentScope.USER_OWNED,
        ).register_routes(app, rt)

    if config.intelligence is not None:
        IntelligenceRouteFactory(
            intelligence_service=primary_service.intelligence,
            domain_name=config.domain_name,
            ownership_service=primary_service,
            scope=config.intelligence.scope,
        ).register_routes(app, rt)

    # 4. Wire API routes (Status, Analytics, manual routes)
    if config.api_factory:
        registered.extend(config.api_factory(app, rt, primary_service, **api_related) or [])

    # 5. Wire UI routes (optional)
    if config.ui_factory:
        ui_related = {}
        for kwarg_name, container_attr in config.ui_related_services.items():
            value = getattr(services, container_attr, _missing) if services else None
            if value is _missing:
                logger.warning(
                    f"{config.domain_name}: ui_related_services['{kwarg_name}'] "
                    f"-> '{container_attr}' not found on services container. "
                    f"Verify the attribute name."
                )
                value = None
            ui_related[kwarg_name] = value

        registered.extend(config.ui_factory(app, rt, primary_service, **ui_related) or [])

    return registered


# ============================================================================
# Activity Domain convenience factory
# ============================================================================


def create_activity_domain_route_config(
    domain_name: str,
    primary_service_attr: str,
    api_factory: Callable[..., list[Any] | None],
    create_schema: type,
    update_schema: type,
    uid_prefix: str,
    request_create_method: str,
    ui_factory: Callable[..., list[Any] | None] | None = None,
    supports_goal_filter: bool = False,
    supports_habit_filter: bool = False,
    api_related_services: dict[str, str] | None = None,
    ui_related_services: dict[str, str] | None = None,
    prometheus_metrics_attr: str | None = None,
) -> DomainRouteConfig:
    """
    Pre-populate Activity Domain conventions into a DomainRouteConfig.

    All Activity Domains share:
    - scope=USER_OWNED
    - CRUD + Query + Intelligence factories
    - user_service in api_related_services (Query factory needs it)
    - a REQUIRED request_create_method: every Activity Domain's create route goes
      through its request-door primitive (``create_task``, ``create_goal``, …) —
      the entity path drops the request-only link fields these domains carry, so
      an activity config without a binding would reopen that silent-drop door.

    See: /docs/patterns/ROUTE_FACTORIES.md, /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
    """
    related = dict(api_related_services or {})
    related.setdefault("user_service", "user")

    return DomainRouteConfig(
        domain_name=domain_name,
        primary_service_attr=primary_service_attr,
        api_factory=api_factory,
        ui_factory=ui_factory,
        api_related_services=related,
        ui_related_services=ui_related_services or {},
        crud=CRUDRouteConfig(
            create_schema=create_schema,
            update_schema=update_schema,
            uid_prefix=uid_prefix,
            prometheus_metrics_attr=prometheus_metrics_attr,
            request_create_method=request_create_method,
        ),
        query=QueryRouteConfig(
            supports_goal_filter=supports_goal_filter,
            supports_habit_filter=supports_habit_filter,
        ),
        intelligence=IntelligenceRouteConfig(),
    )
