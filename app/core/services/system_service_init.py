"""
System Service Initialization
==============================

Initialize SystemService with component health checkers.
Part of the phased migration to SystemService adoption.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from core.services.system_service import SystemService
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)


def _make_service_checker(
    services: Any, attr: str, _name: str
) -> Callable[[], Coroutine[Any, Any, bool]]:
    """Factory for simple service-presence health checkers.

    Returns a plain ``bool`` per the ``register_component_checker`` contract;
    ``SystemService.get_health_status`` records any raised exception as an
    error component, so checkers signal failure by returning ``False``.
    """

    async def check() -> (
        bool
    ):  # skuel-lint: disable=SKUEL029 -- registered as an awaited health-checker
        return bool(getattr(services, attr, None))

    check.__name__ = f"check_{attr}"
    return check


async def initialize_system_service(  # skuel-lint: disable=SKUEL029 -- awaited in the async bootstrap lifecycle (_wire_all_routes -> startup_skuel)
    system_service: SystemService, services: Any
) -> Result[None]:
    """
    Initialize SystemService with health checkers for all components.

    Args:
        system_service: The SystemService instance to initialize,
        services: Container with all service instances

    Returns:
        Result[None] indicating success or failure of initialization
    """
    logger.info("Initializing SystemService with component health checkers")

    # ========================================================================
    # DATABASE HEALTH CHECKER
    # ========================================================================

    async def check_database() -> bool:
        """Check if database connection is healthy.

        Returns ``False`` when no driver is configured; a connection error
        propagates and is recorded as an error component by the caller.
        """
        # Use driver directly for health check
        if services.neo4j_driver:
            async with services.neo4j_driver.session() as session:
                await session.run("RETURN 1 as ping")
            return True
        return False

    # ========================================================================
    # REGISTER ALL CHECKERS
    # ========================================================================

    # Core infrastructure
    system_service.register_component_checker("database", check_database)

    # Core services
    system_service.register_component_checker(
        "user_service", _make_service_checker(services, "user", "User service")
    )
    system_service.register_component_checker(
        "tasks", _make_service_checker(services, "tasks", "Tasks service")
    )
    system_service.register_component_checker(
        "knowledge", _make_service_checker(services, "ku", "Knowledge service")
    )
    system_service.register_component_checker(
        "context", _make_service_checker(services, "context", "Context service")
    )

    logger.info(f"Registered {len(system_service._component_checkers)} health checkers")

    return Result.ok(None)
