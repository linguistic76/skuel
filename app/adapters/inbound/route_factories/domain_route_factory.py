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
            "user_service": "user_service",
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

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from services_bootstrap import Services

# ============================================================================
# Sub-config dataclasses (frozen — static, module-level safe)
# ============================================================================


@dataclass(frozen=True)
class CRUDRouteConfig:
    """Static parameters for CRUDRouteFactory.

    See: /docs/patterns/ROUTE_FACTORIES.md
    """

    create_schema: type
    update_schema: type
    uid_prefix: str
    prometheus_metrics_attr: str | None = None


@dataclass(frozen=True)
class QueryRouteConfig:
    """Static parameters for CommonQueryRouteFactory.

    See: /docs/patterns/ROUTE_FACTORIES.md
    """

    supports_goal_filter: bool = False
    supports_habit_filter: bool = False


@dataclass(frozen=True)
class IntelligenceRouteConfig:
    """Sentinel — presence means "register intelligence routes".

    All Activity Domains use identical parameters:
      intelligence_service = primary_service.intelligence
      ownership_service    = primary_service
      scope                = USER_OWNED
    There is nothing to configure.

    See: /docs/patterns/ROUTE_FACTORIES.md
    """


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
        api_factory: Function to create API routes - signature:
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
    api_factory: Callable[..., list[Any]]
    ui_factory: Callable[..., list[Any]] | None = None
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
) -> RouteList:
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
    from core.models.enums import ContentScope

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
    api_related = {}
    for kwarg_name, container_attr in config.api_related_services.items():
        value = getattr(services, container_attr, None) if services else None
        if value is None and services:
            logger.warning(
                f"{config.domain_name}: api_related_services['{kwarg_name}'] "
                f"-> '{container_attr}' resolved to None. Verify the attribute name "
                f"on the services container."
            )
        api_related[kwarg_name] = value

    registered: RouteList = []

    # 3. Config-driven factory instantiation (order: CRUD → Query → Intelligence)
    if config.crud:
        prometheus_metrics = (
            getattr(services, config.crud.prometheus_metrics_attr)
            if config.crud.prometheus_metrics_attr
            else None
        )
        CRUDRouteFactory(
            service=primary_service,
            domain_name=config.domain_name,
            create_schema=config.crud.create_schema,
            update_schema=config.crud.update_schema,
            uid_prefix=config.crud.uid_prefix,
            scope=ContentScope.USER_OWNED,
            prometheus_metrics=prometheus_metrics,
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
            scope=ContentScope.USER_OWNED,
        ).register_routes(app, rt)

    # 4. Wire API routes (Status, Analytics, manual routes)
    registered.extend(config.api_factory(app, rt, primary_service, **api_related) or [])

    # 5. Wire UI routes (optional)
    if config.ui_factory:
        ui_related = {}
        for kwarg_name, container_attr in config.ui_related_services.items():
            value = getattr(services, container_attr, None) if services else None
            if value is None and services:
                logger.warning(
                    f"{config.domain_name}: ui_related_services['{kwarg_name}'] "
                    f"-> '{container_attr}' resolved to None. Verify the attribute name "
                    f"on the services container."
                )
            ui_related[kwarg_name] = value

        registered.extend(config.ui_factory(app, rt, primary_service, **ui_related) or [])

    return registered


# ============================================================================
# Activity Domain convenience factory
# ============================================================================


def create_activity_domain_route_config(
    domain_name: str,
    primary_service_attr: str,
    api_factory: Callable[..., list[Any]],
    create_schema: type,
    update_schema: type,
    uid_prefix: str,
    ui_factory: Callable[..., list[Any]] | None = None,
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

    See: /docs/patterns/ROUTE_FACTORIES.md, /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
    """
    related = dict(api_related_services or {})
    related.setdefault("user_service", "user_service")

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
        ),
        query=QueryRouteConfig(
            supports_goal_filter=supports_goal_filter,
            supports_habit_filter=supports_habit_filter,
        ),
        intelligence=IntelligenceRouteConfig(),
    )
