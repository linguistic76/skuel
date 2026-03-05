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
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


def _make_service_checker(
    services: Any, attr: str, name: str
) -> Callable[[], Coroutine[Any, Any, Result[bool]]]:
    """Factory for simple service presence health checkers."""

    async def check() -> Result[bool]:
        try:
            return Result.ok(bool(getattr(services, attr, None)))
        except Exception as e:
            return Result.fail(
                Errors.system(
                    message=f"{name} health check failed",
                    exception=e,
                    operation=f"check_{attr}",
                )
            )

    check.__name__ = f"check_{attr}"
    return check  # type: ignore[return-value]


async def initialize_system_service(system_service: SystemService, services: Any) -> Result[None]:
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

    async def check_database() -> Result[bool]:
        """Check if database connection is healthy."""
        try:
            # Use driver directly for health check
            if services.neo4j_driver:
                async with services.neo4j_driver.session() as session:
                    await session.run("RETURN 1 as ping")
                return Result.ok(True)
            return Result.ok(False)
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return Result.fail(
                Errors.system(
                    message="Database health check failed", exception=e, operation="check_database"
                )
            )

    # ========================================================================
    # REGISTER ALL CHECKERS
    # ========================================================================

    # Core infrastructure
    system_service.register_component_checker("database", check_database)

    # Core services
    system_service.register_component_checker(
        "user_service", _make_service_checker(services, "user_service", "User service")
    )
    system_service.register_component_checker(
        "tasks", _make_service_checker(services, "tasks", "Tasks service")
    )
    system_service.register_component_checker(
        "knowledge", _make_service_checker(services, "ku", "Knowledge service")
    )
    system_service.register_component_checker(
        "context", _make_service_checker(services, "context_service", "Context service")
    )

    logger.info(f"Registered {len(system_service._component_checkers)} health checkers")

    return Result.ok(None)
