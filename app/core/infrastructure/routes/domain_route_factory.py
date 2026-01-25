"""
Domain Route Factory - Configuration-Driven Route Registration
==============================================================

Eliminates boilerplate in *_routes.py files by providing a single
configurable registration function.

Before: 6 files x ~80 lines = 480 lines of near-identical code
After: 6 configurations x ~15 lines = 90 lines

Usage:
    from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

    TASKS_CONFIG = DomainRouteConfig(
        domain_name="tasks",
        primary_service_attr="tasks",
        api_factory=create_tasks_api_routes,
        ui_factory=create_tasks_ui_routes,
        api_related_services={
            "user_service": "user_service",  # kwarg_name: container_attr
            "goals_service": "goals",
            "habits_service": "habits",
        },
    )

    def create_tasks_routes(app, rt, services, _sync_service=None):
        return register_domain_routes(app, rt, services, TASKS_CONFIG)
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.utils.logging import get_logger


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
        api_related_services: Mapping of kwarg_name -> container_attr for API factory
        ui_related_services: Mapping of kwarg_name -> container_attr for UI factory
    """

    domain_name: str
    primary_service_attr: str
    api_factory: Callable[..., list[Any]]
    ui_factory: Callable[..., list[Any]] | None = None
    api_related_services: dict[str, str] = field(default_factory=dict)
    ui_related_services: dict[str, str] = field(default_factory=dict)


def register_domain_routes(
    app: Any,
    rt: Any,
    services: Any,
    config: DomainRouteConfig,
) -> list[Any]:
    """
    Register domain routes using configuration.

    Provides consistent:
    - Service extraction with None checks
    - Validation with early return
    - Route wiring (API + optional UI)
    - Structured logging

    Args:
        app: FastHTML application instance
        rt: Route decorator
        services: Services container
        config: Domain route configuration

    Returns:
        List of registered routes (empty if primary service missing)
    """
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
        api_related[kwarg_name] = getattr(services, container_attr, None) if services else None

    # 3. Wire API routes
    config.api_factory(app, rt, primary_service, **api_related)

    # 4. Wire UI routes (optional)
    if config.ui_factory:
        # Extract UI-specific related services (kwarg_name -> value)
        ui_related = {}
        for kwarg_name, container_attr in config.ui_related_services.items():
            ui_related[kwarg_name] = getattr(services, container_attr, None) if services else None

        config.ui_factory(app, rt, primary_service, **ui_related)

    # 5. Log registration
    logger.info(f"✅ Registered {config.domain_name} routes (API + UI)")

    return []
