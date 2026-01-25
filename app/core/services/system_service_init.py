"""
System Service Initialization
==============================

Initialize SystemService with component health checkers.
Part of the phased migration to SystemService adoption.
"""

from typing import Any

from core.services.system_service import SystemService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


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
            if services.driver:
                async with services.driver.session() as session:
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
    # SERVICE HEALTH CHECKERS
    # ========================================================================

    async def check_ku_service() -> Result[bool]:
        """Check if knowledge service is healthy."""
        try:
            # Use 'ku' attribute (not ku_service)
            if services.ku:
                return Result.ok(True)
            return Result.ok(False)  # Not configured, but not an error
        except Exception as e:
            logger.error(f"Knowledge service health check failed: {e}")
            return Result.fail(
                Errors.system(
                    message="Knowledge service health check failed",
                    exception=e,
                    operation="check_ku_service",
                )
            )

    async def check_context_service() -> Result[bool]:
        """Check if context service is healthy."""
        try:
            # Use 'context_service' attribute
            if services.context_service:
                return Result.ok(True)
            return Result.ok(False)  # Not configured
        except Exception as e:
            logger.error(f"Context service health check failed: {e}")
            return Result.fail(
                Errors.system(
                    message="Context service health check failed",
                    exception=e,
                    operation="check_context_service",
                )
            )

    async def check_user_service() -> Result[bool]:
        """Check if user service is healthy."""
        try:
            if services.user_service:
                return Result.ok(True)
            return Result.ok(False)
        except Exception as e:
            logger.error(f"User service health check failed: {e}")
            return Result.fail(
                Errors.system(
                    message="User service health check failed",
                    exception=e,
                    operation="check_user_service",
                )
            )

    async def check_tasks_service() -> Result[bool]:
        """Check if tasks service is healthy."""
        try:
            if services.tasks:
                return Result.ok(True)
            return Result.ok(False)
        except Exception as e:
            logger.error(f"Tasks service health check failed: {e}")
            return Result.fail(
                Errors.system(
                    message="Tasks service health check failed",
                    exception=e,
                    operation="check_tasks_service",
                )
            )

    # ========================================================================
    # REGISTER ALL CHECKERS
    # ========================================================================

    # Core infrastructure
    system_service.register_component_checker("database", check_database)

    # Core services
    system_service.register_component_checker("user_service", check_user_service)
    system_service.register_component_checker("tasks", check_tasks_service)
    system_service.register_component_checker("knowledge", check_ku_service)
    system_service.register_component_checker("context", check_context_service)

    logger.info(f"Registered {len(system_service._component_checkers)} health checkers")

    return Result.ok(None)
